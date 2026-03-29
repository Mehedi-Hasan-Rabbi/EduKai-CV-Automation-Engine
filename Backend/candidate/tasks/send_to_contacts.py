import base64
import logging
import mimetypes
import os
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="candidate.tasks.send_to_contacts",
)
def send_to_contacts_task(self, candidate_id: str, contact_ids: list):
    """
    Sends candidate's email_subject + email_body to a list of
    organization contacts via SendGrid.
    Attaches the candidate's profile photo if available.
    Returns a summary dict.
    """
    from django.utils import timezone
    from candidate.models import Candidate
    from organization.models import OrganizationContact

    summary = {
        "total": len(contact_ids),
        "sent": 0,
        "failed": 0,
        "errors": [],
    }

    if not settings.SENDGRID_API_KEY:
        logger.error("[send_contacts] SENDGRID_API_KEY not set.")
        summary["errors"].append("SendGrid API key not configured.")
        return summary

    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        logger.error(f"[send_contacts] Candidate {candidate_id} not found.")
        summary["errors"].append("Candidate not found.")
        return summary

    if not candidate.email_subject or not candidate.email_body:
        summary["errors"].append(
            "Candidate has no email subject or body. Process the CV through AI first."
        )
        return summary

    # Prepare optional profile photo attachment once
    attachment = None
    if candidate.profile_photo:
        try:
            candidate.profile_photo.open("rb")
            photo_bytes = candidate.profile_photo.read()
            candidate.profile_photo.close()
            if photo_bytes:
                mime_type, _ = mimetypes.guess_type(candidate.profile_photo.name)
                mime_type = mime_type or "application/octet-stream"
                encoded = base64.b64encode(photo_bytes).decode("ascii")
                from sendgrid.helpers.mail import Attachment, FileContent, FileName, FileType, Disposition
                attachment = Attachment(
                    FileContent(encoded),
                    FileName(os.path.basename(candidate.profile_photo.name)),
                    FileType(mime_type),
                    Disposition("attachment"),
                )
        except Exception as exc:
            logger.warning(
                f"[send_contacts] Could not read profile photo for candidate {candidate_id}: {exc}"
            )

    contacts = OrganizationContact.objects.select_related("organization").filter(
        id__in=contact_ids
    )
    if not contacts.exists():
        summary["errors"].append("No valid contacts found.")
        return summary

    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import (
        Mail,
        From,
        To,
        Subject,
        HtmlContent,
        PlainTextContent,
        ReplyTo,
    )

    sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
    html_body = _build_html_body(candidate.email_body)

    for contact in contacts:
        try:
            message = Mail(
                from_email=From(settings.SENDGRID_FROM_EMAIL, settings.SENDGRID_FROM_NAME),
                to_emails=To(contact.work_email),
                subject=Subject(candidate.email_subject),
                plain_text_content=PlainTextContent(candidate.email_body),
                html_content=HtmlContent(html_body),
            )
            if settings.SENDGRID_REPLY_TO_EMAIL:
                message.reply_to = ReplyTo(
                    email=settings.SENDGRID_REPLY_TO_EMAIL,
                    name=settings.SENDGRID_REPLY_TO_NAME or None,
                )
            if attachment:
                message.add_attachment(attachment)

            response = sg.send(message)
            if response.status_code in (200, 202):
                summary["sent"] += 1
                logger.info(
                    f"[send_contacts] ✅ Sent to {contact.work_email} ({contact.organization.name})"
                )
            else:
                raise Exception(f"Unexpected SendGrid status: {response.status_code}")

        except Exception as exc:
            summary["failed"] += 1
            summary["errors"].append(f"{contact.work_email}: {exc}")
            logger.error(f"[send_contacts] ❌ Failed to send to {contact.work_email}: {exc}")

    if summary["sent"] > 0:
        from django.db.models import F
        candidate.last_contacted_at = timezone.now()
        candidate.contacts_emailed_count = F("contacts_emailed_count") + summary["sent"]
        candidate.save(update_fields=["last_contacted_at", "contacts_emailed_count", "updated_at"])
        from account.utils.activity import log_activity
        log_activity(
            event_type="emails_sent",
            severity="success",
            title=f"Emails sent for {candidate.name}",
            message=f"Sent to {summary['sent']} contacts. Failed: {summary['failed']}.",
            candidate_id=candidate.id,
        )

    logger.info(
        f"[send_contacts] ✅ Done for candidate '{candidate.name}' — sent={summary['sent']}, failed={summary['failed']}"
    )
    return summary


def _build_html_body(plain_text: str) -> str:
    """
    Converts AI-generated plain text email body to clean HTML.
    Handles **bold** markdown and newlines.
    """
    import re

    text = (
        plain_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    text = text.replace("\n", "<br>")

    reply_to = getattr(settings, "SENDGRID_REPLY_TO_EMAIL", "")
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; font-size: 14px;
             color: #222; max-width: 600px;
             margin: 0 auto; padding: 20px;">
  <div>{text}</div>
  <br>
  <p style="color: #555; font-size: 12px;">
    Education Specialists Agency<br>
    <a href="mailto:{reply_to}">{reply_to}</a>
  </p>
</body>
</html>"""