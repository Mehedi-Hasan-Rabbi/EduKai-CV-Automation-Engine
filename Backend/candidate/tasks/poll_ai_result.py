import logging

from celery import shared_task
from django.conf import settings
from django.db import models

import requests

logger = logging.getLogger(__name__)

# Quality check mapping from AI response to model choices
QUALITY_MAP = {
    "pass": "passed",
    "fail": "failed",
}

@shared_task(
    bind=True,
    max_retries=None,
    name="candidate.tasks.poll_ai_result",
)
def poll_ai_result_task(self, candidate_id: str, ai_task_id: str):
    from candidate.models import Candidate, AIProcessingStatus

    max_retries = settings.AI_POLL_MAX_RETRIES
    poll_interval = settings.AI_POLL_INTERVAL_SECONDS
    current_attempt = self.request.retries

    if current_attempt >= max_retries:
        logger.error(
            f"[poll_ai] Candidate {candidate_id} exceeded max poll retries ({max_retries})."
        )
        Candidate.objects.filter(id=candidate_id).update(
            ai_processing_status=AIProcessingStatus.FAILED,
            ai_failure_reason=f"AI task polling timed out after {max_retries} attempts.",
        )
        _update_batch_failed(candidate_id)
        return

    try:
        response = requests.get(
            f"{settings.AI_BASE_URL}/api/v1/tasks/{ai_task_id}/",
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

    except requests.RequestException as exc:
        logger.warning(f"[poll_ai] Poll request failed for task {ai_task_id}: {exc}")
        raise self.retry(countdown=poll_interval)

    ai_status = data.get("status", "")

    # ── Status sets based on actual AI route.py response ──────────────────
    PENDING_STATUSES = {"PENDING", "STARTED", "RETRY"}
    FAILED_STATUSES  = {"failed", "FAILURE"}

    if ai_status in PENDING_STATUSES:
        logger.info(
            f"[poll_ai] Task {ai_task_id} status='{ai_status}' — still in progress. "
            f"Attempt {current_attempt + 1}/{max_retries}."
        )
        raise self.retry(countdown=poll_interval)

    if ai_status in FAILED_STATUSES:
        logger.error(f"[poll_ai] Task {ai_task_id} failed on AI side. Status: {ai_status}")
        Candidate.objects.filter(id=candidate_id).update(
            ai_processing_status=AIProcessingStatus.FAILED,
            ai_failure_reason=f"AI returned failed status: {ai_status}",
        )
        _update_batch_failed(candidate_id)
        return

    if ai_status != "completed":
        logger.warning(
            f"[poll_ai] Task {ai_task_id} unknown status: '{ai_status}'. "
            f"Continuing to poll. Attempt {current_attempt + 1}/{max_retries}."
        )
        raise self.retry(countdown=poll_interval)

    # -------------------------------------------------------------------------
    # Completed — extract and save data
    # -------------------------------------------------------------------------
    result = data.get("result", {})
    personal_info = result.get("personal_info", {})
    data_extracted = result.get("data_extracted", {})
    quality_check = result.get("quality_check", "").lower()

    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        logger.error(f"[poll_ai] Candidate {candidate_id} not found during save.")
        return

    quality_status = QUALITY_MAP.get(quality_check, "manual")
    raw_experience = personal_info.get("experience", "")
    years_of_experience = _parse_experience(raw_experience)

    # Email — normalize to lowercase
    raw_email = personal_info.get("email")
    normalized_email = raw_email.strip().lower() if raw_email else None

    # Job titles — from data_extracted.role
    raw_job_titles = data_extracted.get("role", [])
    job_titles = raw_job_titles if isinstance(raw_job_titles, list) else []

    # Update candidate from AI data
    candidate.name            = personal_info.get("full_name") or candidate.name
    candidate.email           = normalized_email or candidate.email
    candidate.whatsapp_number = personal_info.get("whatsapp") or candidate.whatsapp_number
    candidate.location        = personal_info.get("location") or candidate.location
    candidate.skills          = personal_info.get("skill") or []
    candidate.job_titles      = job_titles
    candidate.years_of_experience = years_of_experience
    candidate.quality_status  = quality_status
    candidate.email_subject   = data_extracted.get("email_subject", "")
    candidate.email_body      = data_extracted.get("email_body", "")
    candidate.ai_enhanced_cv_content = result
    candidate.ai_processing_status = AIProcessingStatus.IN_PROGRESS

    # ── Download profile photo from AI URL and save to MinIO ──────────────
    ai_photo_url = result.get("extracted_photo_url") or None
    photo_file = _download_profile_photo(candidate_id, ai_photo_url)
    if photo_file:
        candidate.profile_photo.save(
            photo_file["filename"],
            photo_file["content"],
            save=False,     # ✅ don't trigger a separate DB save yet
        )

    logger.info(
        f"[poll_ai] Saving candidate {candidate_id} — "
        f"email={normalized_email!r} "
        f"job_titles={job_titles} "
        f"photo={'saved' if photo_file else 'not found'}"
    )

    try:
        candidate.save(update_fields=[
            "name",
            "email",
            "whatsapp_number",
            "location",
            "skills",
            "job_titles",
            "profile_photo",        # ✅ ImageField, not URLField
            "years_of_experience",
            "quality_status",
            "email_subject",
            "email_body",
            "ai_enhanced_cv_content",
            "ai_processing_status",
            "updated_at",
        ])
        logger.info(f"[poll_ai] ✅ Candidate {candidate_id} saved successfully.")
    except Exception as exc:
        logger.error(
            f"[poll_ai] ❌ Failed to save candidate {candidate_id}: {exc}",
            exc_info=True,
        )
        raise

    # Trigger PDF generation task
    from candidate.tasks.generate_pdf import generate_enhanced_cv_pdf_task
    generate_enhanced_cv_pdf_task.apply_async(
        args=[candidate_id],
        queue="pdf",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _download_profile_photo(candidate_id: str, photo_url: str):
    """
    Downloads profile photo from AI URL and returns ContentFile ready
    to save to MinIO. Returns None if URL is empty or download fails.
    """
    import requests as req
    from django.core.files.base import ContentFile

    if not photo_url:
        logger.info(f"[poll_ai] No profile photo URL for candidate {candidate_id}.")
        return None

    try:
        response = req.get(photo_url, timeout=15)
        response.raise_for_status()

        # Detect extension from Content-Type header
        content_type = response.headers.get("Content-Type", "image/png")
        ext_map = {
            "image/jpeg": "jpg",
            "image/jpg":  "jpg",
            "image/png":  "png",
            "image/webp": "webp",
            "image/gif":  "gif",
        }
        ext = ext_map.get(content_type.split(";")[0].strip(), "png")
        filename = f"profile_{candidate_id}.{ext}"

        logger.info(
            f"[poll_ai] ✅ Profile photo downloaded for candidate {candidate_id} "
            f"— {len(response.content)} bytes, type={content_type}"
        )
        return {
            "filename": filename,
            "content":  ContentFile(response.content),
        }

    except Exception as exc:
        logger.warning(
            f"[poll_ai] ⚠️ Could not download profile photo for candidate "
            f"{candidate_id} from {photo_url}: {exc}"
        )
        return None


def _parse_experience(raw: str):
    import re
    if not raw:
        return None
    raw = raw.lower().strip()
    match = re.search(r"(\d+\.?\d*)\s*year", raw)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+)\s*month", raw)
    if match:
        return round(int(match.group(1)) / 12, 1)
    try:
        return float(raw)
    except ValueError:
        return None


def _update_batch_failed(candidate_id: str):
    from candidate.models import Candidate
    try:
        candidate = Candidate.objects.select_related("batch").get(id=candidate_id)
        if candidate.batch:
            candidate.batch.failed_count = models.F("failed_count") + 1
            candidate.batch.save(update_fields=["failed_count"])

        # ── Log activity ──────────────────────────────────────────────────
        from account.utils.activity import log_activity
        log_activity(
            event_type   = "cv_failed",
            severity     = "error",
            title        = f"CV failed: {candidate.name or candidate_id}",
            message      = candidate.ai_failure_reason or "AI processing failed.",
            candidate_id = candidate.id,
            batch_id     = candidate.batch_id,
        )
    except Exception:
        pass