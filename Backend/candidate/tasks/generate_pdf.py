import logging
import os
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=15,
    name="candidate.tasks.generate_pdf",
)
def generate_enhanced_cv_pdf_task(self, candidate_id: str, is_regeneration: bool = False):
    from candidate.models import Candidate, AIProcessingStatus

    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        logger.error(f"[generate_pdf] Candidate {candidate_id} not found.")
        return

    result = candidate.ai_enhanced_cv_content
    if not result:
        candidate.ai_processing_status = AIProcessingStatus.FAILED
        candidate.ai_failure_reason = "No AI content found to generate PDF."
        candidate.save(update_fields=["ai_processing_status", "ai_failure_reason", "updated_at"])
        return

    data_extracted = result.get("data_extracted", {})

    # -------------------------------------------------------------------------
    # Build template context
    # ✅ Editable fields → read from Candidate model (reflects latest edits)
    # ✅ AI-only fields  → read from ai_enhanced_cv_content (never edited)
    # -------------------------------------------------------------------------
    cv_context = {
        # ── Editable fields — always use latest from Candidate model ──────
        "name":     candidate.name or data_extracted.get("name", ""),
        "role":     " | ".join(candidate.job_titles) if candidate.job_titles else (
                        " | ".join(data_extracted.get("role", []))
                        if isinstance(data_extracted.get("role"), list)
                        else data_extracted.get("role", "")
                    ),
        "location": candidate.location or data_extracted.get("location", ""),

        # ── AI-only fields — read from raw AI output ──────────────────────
        "professional_profile": data_extracted.get("professional_profile", ""),
        "employment_history":   data_extracted.get("employment_history", []),
        "qualifications":       data_extracted.get("qualifications", []),
        "interests":            data_extracted.get("interests", ""),
    }

    logo_url = _resolve_logo_url()
    logger.info(f"[generate_pdf] Logo URL resolved: '{logo_url or 'NOT FOUND — skipping logo'}'")

    context = {
        "cv":        cv_context,
        "logo_path": logo_url,
    }

    # -------------------------------------------------------------------------
    # Render HTML template
    # -------------------------------------------------------------------------
    try:
        html_string = render_to_string("candidate/enhanced_cv.html", context)
    except Exception as exc:
        logger.error(f"[generate_pdf] Template rendering failed for {candidate_id}: {exc}")
        candidate.ai_processing_status = AIProcessingStatus.FAILED
        candidate.ai_failure_reason = f"Template rendering failed: {exc}"
        candidate.save(update_fields=["ai_processing_status", "ai_failure_reason", "updated_at"])
        raise self.retry(exc=exc)

    # -------------------------------------------------------------------------
    # Generate PDF
    # -------------------------------------------------------------------------
    try:
        pdf_bytes = _render_pdf(html_string)
    except Exception as exc:
        logger.error(f"[generate_pdf] PDF generation failed for {candidate_id}: {exc}")
        candidate.ai_processing_status = AIProcessingStatus.FAILED
        candidate.ai_failure_reason = f"PDF generation failed: {exc}"
        candidate.save(update_fields=["ai_processing_status", "ai_failure_reason", "updated_at"])
        raise self.retry(exc=exc)

    # -------------------------------------------------------------------------
    # Upload PDF to MinIO
    # -------------------------------------------------------------------------
    safe_name = (
        candidate.name.replace(" ", "_").lower()
        if candidate.name
        else str(candidate_id)
    )
    file_name = f"{safe_name}_enhanced_cv.pdf"

    try:
        candidate.ai_enhanced_cv_file.save(
            file_name,
            ContentFile(pdf_bytes),
            save=False,
        )
    except Exception as exc:
        logger.error(f"[generate_pdf] MinIO upload failed for {candidate_id}: {exc}")
        candidate.ai_processing_status = AIProcessingStatus.FAILED
        candidate.ai_failure_reason = f"MinIO upload failed: {exc}"
        candidate.save(update_fields=["ai_processing_status", "ai_failure_reason", "updated_at"])
        raise self.retry(exc=exc)

    # -------------------------------------------------------------------------
    # Final DB save — mark completed
    # -------------------------------------------------------------------------
    candidate.ai_processing_status = AIProcessingStatus.COMPLETED
    candidate.save(update_fields=[
        "ai_enhanced_cv_file",
        "ai_processing_status",
        "updated_at",
    ])

# ── Only increment batch count and send email on FIRST generation ─────
    if not is_regeneration:
        if candidate.batch:
            from django.db.models import F
            candidate.batch.processed_count = F("processed_count") + 1
            candidate.batch.save(update_fields=["processed_count", "updated_at"])
        
        # ── Log activity ──────────────────────────────────────────────────
        from account.utils.activity import log_activity
        log_activity(
            event_type   = "cv_processed",
            severity     = "success",
            title        = f"CV processed: {candidate.name or 'Unknown'}",
            message      = f"AI processing completed. Quality: {candidate.quality_status}.",
            candidate_id = candidate.id,
            batch_id     = candidate.batch_id,
        )

        if candidate.email:
            from candidate.tasks.send_email import send_availability_email_task
            send_availability_email_task.apply_async(
                args=[candidate_id],
                queue="default",
                countdown=5,
            )
            logger.info(
                f"[generate_pdf] Availability email queued for candidate {candidate_id}."
            )
        else:
            logger.info(
                f"[generate_pdf] No email found for candidate {candidate_id}. "
                f"Skipping availability email."
            )
    else:
        logger.info(
            f"[generate_pdf] ♻️ PDF regenerated for candidate {candidate_id} "
            f"(batch count and email skipped — regeneration only)."
        )

    logger.info(f"[generate_pdf] ✅ PDF generated and saved for candidate {candidate_id}.")


def _resolve_logo_url() -> str:
    """
    Resolves the logo file path to a file:// URI for WeasyPrint.

    Priority:
      1. CV_LOGO_PATH from settings/.env  (explicit override)
      2. <BASE_DIR>/media/images/CV_logo.png  (convention default)
      3. <BASE_DIR>/media/images/logo.png     (fallback name)

    Returns "" if no logo file is found anywhere.
    """
    candidates = []

    # 1. Explicit setting from .env
    explicit = getattr(settings, "CV_LOGO_PATH", "")
    if explicit:
        candidates.append(str(explicit))

    # 2. Convention-based paths relative to BASE_DIR
    base = Path(settings.BASE_DIR)
    candidates.append(str(base / "media" / "images" / "CV_logo.png"))
    candidates.append(str(base / "media" / "images" / "logo.png"))

    for path_str in candidates:
        path = Path(path_str)
        if path.exists() and path.is_file():
            # ✅ Path.as_uri() always produces correct file:///... format
            uri = path.as_uri()
            logger.debug(f"[generate_pdf] Logo found at: {path_str} → {uri}")
            return uri

    logger.warning(
        f"[generate_pdf] Logo not found. Tried:\n" +
        "\n".join(f"  - {p}" for p in candidates)
    )
    return ""


# ---------------------------------------------------------------------------
# PDF rendering — Windows uses xhtml2pdf, Linux/Mac uses WeasyPrint
# ---------------------------------------------------------------------------
def _render_pdf(html_string: str) -> bytes:
        from weasyprint import HTML
        return HTML(string=html_string).write_pdf()