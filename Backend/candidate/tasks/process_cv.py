import logging

from celery import shared_task
from django.conf import settings

import requests

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    name="candidate.tasks.process_cv",
)
def process_cv_task(self, candidate_id: str, additional_info: dict):
    """
    Task 1 — Called once per CV after upload.

    Responsibilities:
    1. POST the CV's MinIO pre-signed URL to the AI endpoint
    2. Receive the AI task_id
    3. Save task_id to DB
    4. Trigger the polling task
    """
    from candidate.models import Candidate, AIProcessingStatus

    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        logger.error(f"[process_cv] Candidate {candidate_id} not found.")
        return

    # -------------------------------------------------------------------------
    # Build CV URL
    # ✅ USE_S3=True  → generate pre-signed URL (MinIO requires auth)
    # ✅ USE_S3=False → use plain local URL (Django dev server serves it)
    # -------------------------------------------------------------------------
    if not candidate.original_cv_file:
        candidate.ai_processing_status = AIProcessingStatus.FAILED
        candidate.ai_failure_reason = "No CV file found to send to AI."
        candidate.save(update_fields=["ai_processing_status", "ai_failure_reason"])
        logger.error(f"[process_cv] Candidate {candidate_id} has no CV file.")
        return

    if getattr(settings, "USE_S3", False):
        # ✅ Use INTERNAL presigned URL — AI worker fetches from minio:9000
        from candidate.utils.minio_utils import get_presigned_url_for_ai
        cv_url = get_presigned_url_for_ai(
            candidate.original_cv_file,
            expires_in=settings.PRESIGNED_URL_EXPIRE_SECONDS
        )
        logger.info(f"[process_cv] Using internal pre-signed URL for AI: {cv_url}")
    else:
        cv_url = candidate.original_cv_file.url

    payload = {
        "cv_url":          cv_url,
        "additional_info": additional_info,
    }

    try:
        response = requests.post(
            f"{settings.AI_BASE_URL}/api/v1/regeneration/",
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

    except requests.RequestException as exc:
        logger.warning(f"[process_cv] AI request failed for {candidate_id}: {exc}")
        candidate.ai_retry_count += 1
        candidate.save(update_fields=["ai_retry_count"])
        raise self.retry(exc=exc)

    ai_task_id = data.get("task_id")
    if not ai_task_id:
        candidate.ai_processing_status = AIProcessingStatus.FAILED
        candidate.ai_failure_reason = f"AI response missing task_id. Response: {data}"
        candidate.save(update_fields=["ai_processing_status", "ai_failure_reason"])
        logger.error(f"[process_cv] No task_id in AI response for candidate {candidate_id}.")
        return

    # Save task_id and update status
    candidate.ai_task_id = ai_task_id
    candidate.ai_processing_status = AIProcessingStatus.IN_PROGRESS
    candidate.save(update_fields=["ai_task_id", "ai_processing_status"])

    logger.info(f"[process_cv] Candidate {candidate_id} → AI task_id={ai_task_id}")

    # Trigger the polling task after a short delay
    from candidate.tasks.poll_ai_result import poll_ai_result_task
    poll_ai_result_task.apply_async(
        args=[candidate_id, ai_task_id],
        countdown=settings.AI_POLL_INTERVAL_SECONDS,
        queue="polling",
    )