import logging
import requests

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)

PENDING_STATUSES = {"PENDING", "STARTED", "RETRY"}
FAILED_STATUSES  = {"failed", "FAILURE"}


@shared_task(
    bind=True,
    max_retries=None,
    name="candidate.tasks.poll_rewrite_result",
)
def poll_rewrite_result_task(self, candidate_id: str, rewrite_task_id: str):
    """
    Polls AI for rewrite task completion.
    When done — updates data_extracted in ai_enhanced_cv_content
    and regenerates the PDF.
    """
    from candidate.models import Candidate, AIProcessingStatus

    max_retries  = settings.AI_POLL_MAX_RETRIES
    poll_interval = settings.AI_POLL_INTERVAL_SECONDS
    current_attempt = self.request.retries

    # ── Timeout check ─────────────────────────────────────────────────────
    if current_attempt >= max_retries:
        logger.error(
            f"[rewrite] Candidate {candidate_id} rewrite timed out "
            f"after {max_retries} attempts."
        )
        Candidate.objects.filter(id=candidate_id).update(
            rewrite_status="failed",
            rewrite_failure_reason=f"Rewrite polling timed out after {max_retries} attempts.",
        )
        return

    # ── Poll AI ───────────────────────────────────────────────────────────
    try:
        response = requests.get(
            f"{settings.AI_BASE_URL}/api/v1/tasks/{rewrite_task_id}/",
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.warning(f"[rewrite] Poll request failed for task {rewrite_task_id}: {exc}")
        raise self.retry(countdown=poll_interval)

    ai_status = data.get("status", "")

    if ai_status in PENDING_STATUSES:
        logger.info(
            f"[rewrite] Task {rewrite_task_id} status='{ai_status}' — "
            f"still in progress. Attempt {current_attempt + 1}/{max_retries}."
        )
        raise self.retry(countdown=poll_interval)

    if ai_status in FAILED_STATUSES:
        logger.error(f"[rewrite] Task {rewrite_task_id} failed. Status: {ai_status}")
        Candidate.objects.filter(id=candidate_id).update(
            rewrite_status="failed",
            rewrite_failure_reason=f"AI rewrite returned failed status: {ai_status}",
        )
        return

    if ai_status != "completed":
        logger.warning(
            f"[rewrite] Task {rewrite_task_id} unknown status: '{ai_status}'. "
            f"Continuing to poll."
        )
        raise self.retry(countdown=poll_interval)

    # ── Completed — extract new data_extracted ────────────────────────────
    result = data.get("result", {})
    new_data_extracted = result.get("data_extracted", {})

    if not new_data_extracted:
        logger.error(f"[rewrite] Task {rewrite_task_id} returned empty data_extracted.")
        Candidate.objects.filter(id=candidate_id).update(
            rewrite_status="failed",
            rewrite_failure_reason="AI rewrite returned empty data_extracted.",
        )
        return

    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        logger.error(f"[rewrite] Candidate {candidate_id} not found.")
        return

    # ── Update ONLY data_extracted inside ai_enhanced_cv_content ─────────
    # Keep quality_check, extracted_photo_url, personal_info untouched
    existing_content = candidate.ai_enhanced_cv_content or {}
    existing_content["data_extracted"] = new_data_extracted

    # ── Also update job_titles from new data_extracted.role ──────────────
    new_job_titles = new_data_extracted.get("role", [])
    if isinstance(new_job_titles, list) and new_job_titles:
        candidate.job_titles = new_job_titles

    candidate.ai_enhanced_cv_content = existing_content
    candidate.rewrite_status         = "completed"
    candidate.rewrite_task_id        = rewrite_task_id
    candidate.rewrite_failure_reason = None

    candidate.save(update_fields=[
        "ai_enhanced_cv_content",
        "job_titles",
        "rewrite_status",
        "rewrite_task_id",
        "rewrite_failure_reason",
        "updated_at",
    ])

    logger.info(
        f"[rewrite] ✅ Candidate {candidate_id} rewrite saved. "
        f"Triggering PDF regeneration."
    )

    # ── Regenerate PDF with new data_extracted ────────────────────────────
    from candidate.tasks.generate_pdf import generate_enhanced_cv_pdf_task
    generate_enhanced_cv_pdf_task.apply_async(
        args=[candidate_id],
        kwargs={"is_regeneration": True},
        queue="pdf",
    )