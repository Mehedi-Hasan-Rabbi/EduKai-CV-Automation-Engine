import logging
import mimetypes
import os
import base64
from pathlib import Path
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
    from django.utils import timezone
    from candidate.models import Candidate
    from organization.models import OrganizationContact
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import (
        Mail, From, To, Subject, HtmlContent, PlainTextContent, ReplyTo
    )

    summary = {"total": len(contact_ids), "sent": 0, "failed": 0, "errors": []}

    if not settings.SENDGRID_API_KEY:
        logger.error("[send_contacts] SENDGRID_API_KEY not set.")
        summary["errors"].append("SendGrid API key not configured.")
        return summary

    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        summary["errors"].append("Candidate not found.")
        return summary

    if not candidate.email_subject or not candidate.email_body:
        summary["errors"].append("Candidate has no email subject or body. Process the CV through AI first.")
        return summary

    contacts = OrganizationContact.objects.select_related("organization").filter(id__in=contact_ids)
    if not contacts.exists():
        summary["errors"].append("No valid contacts found.")
        return summary

    sg = SendGridAPIClient(settings.SENDGRID_API_KEY)

    # Attachments: profile + CV + footer logo
    profile_attachment = _build_attachment_from_field(candidate.profile_photo, "candidate_photo")
    cv_attachment = _build_attachment_from_field(candidate.ai_enhanced_cv_file, "enhanced_cv")
    footer_logo_attachment = _build_attachment_from_local_path(
        getattr(settings, "EMAIL_FOOTER_LOGO_PATH", ""),
        fallback_name="edukai_footer_logo.png",
    )

    for contact in contacts:
        try:
            plain_body = _build_personalized_plain_body(candidate.email_body, contact.contact_person)
            html_body = _build_html_body(
                plain_text=plain_body,
                candidate=candidate,
            )

            message = Mail(
                from_email=From(settings.SENDGRID_FROM_EMAIL, settings.SENDGRID_FROM_NAME),
                to_emails=To(contact.work_email),
                subject=Subject(candidate.email_subject),
                plain_text_content=PlainTextContent(plain_body),
                html_content=HtmlContent(html_body),
            )

            if settings.SENDGRID_REPLY_TO_EMAIL:
                message.reply_to = ReplyTo(
                    email=settings.SENDGRID_REPLY_TO_EMAIL,
                    name=settings.SENDGRID_REPLY_TO_NAME or None,
                )

            # Attach files
            if profile_attachment:
                message.add_attachment(profile_attachment)
            if cv_attachment:
                message.add_attachment(cv_attachment)
            if footer_logo_attachment:
                message.add_attachment(footer_logo_attachment)

            response = sg.send(message)
            if response.status_code in (200, 202):
                summary["sent"] += 1
                logger.info(f"[send_contacts] ✅ Sent to {contact.work_email}")
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

    return summary


def _build_personalized_plain_body(original_body: str, contact_person: str | None) -> str:
    person = (contact_person or "").strip()
    greeting = f"Dear {person}," if person else "Dear Sir/Madam,"
    nb = (
        "\n\nNB. If you have another vacancy for another role, simply drop me an email with your requirement(s) "
        "and I will send you our best matched candidates.\n"
        "(this is a generic email so journey times to your school for your chosen candidate(s) would have to be explored "
        "before an interview/trial is arranged)"
    )
    return f"{greeting}\n\n{original_body}{nb}"


def _build_data_uri_from_local_path(path: str) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    raw = p.read_bytes()
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _read_file_bytes(file_field) -> bytes | None:
    from django.conf import settings as s

    if not file_field or not file_field.name:
        return None

    try:
        if getattr(s, "USE_S3", False):
            from candidate.utils.minio_utils import _get_s3_client
            import io
            s3 = _get_s3_client()
            buffer = io.BytesIO()
            s3.download_fileobj(
                Bucket=s.AWS_STORAGE_BUCKET_NAME,
                Key=file_field.name,
                Fileobj=buffer,
            )
            buffer.seek(0)
            return buffer.read()
        else:
            with file_field.open("rb") as f:
                return f.read()
    except Exception as exc:
        logger.warning(f"[send_contacts] _read_file_bytes failed for '{getattr(file_field, 'name', '')}': {exc}")
        return None


def _build_attachment_from_field(file_field, fallback_name: str):
    from sendgrid.helpers.mail import Attachment, FileContent, FileName, FileType, Disposition

    if not file_field or not file_field.name:
        return None

    try:
        raw = _read_file_bytes(file_field)
        if not raw:
            return None

        filename = os.path.basename(file_field.name) or fallback_name
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        encoded = base64.b64encode(raw).decode("utf-8")

        return Attachment(
            file_content=FileContent(encoded),
            file_name=FileName(filename),
            file_type=FileType(mime_type),
            disposition=Disposition("attachment"),
        )
    except Exception as exc:
        logger.warning(f"[send_contacts] _build_attachment_from_field failed: {exc}")
        return None


def _build_attachment_from_local_path(path: str, fallback_name: str = "attachment"):
    from sendgrid.helpers.mail import Attachment, FileContent, FileName, FileType, Disposition

    if not path:
        return None

    p = Path(path)
    if not p.exists() or not p.is_file():
        logger.warning(f"[send_contacts] Local file attachment not found: {path}")
        return None

    try:
        raw = p.read_bytes()
        mime_type = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(raw).decode("utf-8")

        return Attachment(
            file_content=FileContent(encoded),
            file_name=FileName(p.name or fallback_name),
            file_type=FileType(mime_type),
            disposition=Disposition("attachment"),
        )
    except Exception as exc:
        logger.warning(f"[send_contacts] _build_attachment_from_local_path failed: {exc}")
        return None


def _build_html_body(plain_text: str, candidate) -> str:
    import re
    from datetime import datetime

    text = (
        plain_text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    text = text.replace("\n", "<br>")

    reply_to = getattr(settings, "SENDGRID_REPLY_TO_EMAIL", "info@edukai.co.uk")
    sent_at = datetime.now().strftime("%d %B %Y %H:%M")

    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;color:#111827;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f4f6;padding:24px 0;">
      <tr><td align="center">
        <table role="presentation" width="700" cellspacing="0" cellpadding="0"
               style="max-width:700px;width:100%;background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;">
          <tr>
            <td style="background:#0b3a75;padding:14px 24px;color:#fff;font-size:18px;font-weight:bold;">
              Edukai Recruitment
            </td>
          </tr>
          <tr>
            <td style="padding:20px 24px 8px 24px;font-size:13px;color:#374151;">
              <strong>From:</strong> Edukai Recruitment<br>
              <strong>Sent:</strong> {sent_at}<br>
              <strong>Subject:</strong> {candidate.email_subject}
            </td>
          </tr>
          <tr>
            <td style="padding:8px 24px 16px 24px;font-size:16px;line-height:1.7;color:#111827;">
              {text}
            </td>
          </tr>

          <tr><td style="padding:0 24px 16px 24px;"><hr style="border:none;border-top:1px solid #e5e7eb;"></td></tr>

          <tr>
            <td style="padding:0 24px 10px 24px;font-size:14px;line-height:1.7;">
              <strong>Kind regards,</strong><br>
              Kai Smith<br>
              Director, Edukai Recruitment<br>
              T: 0203 987 9981<br>
              M: 07542 870 343<br>
              E: <a href="mailto:{reply_to}">{reply_to}</a><br>
              W: <a href="https://www.edukai.co.uk">www.edukai.co.uk</a><br>
              A: Unit A3, Broomsleigh Business Park, Worsley Bridge Rd, London, SE26 5BN
            </td>
          </tr>

          <tr>
            <td style="padding:12px 24px 22px 24px;font-size:11px;line-height:1.6;color:#6b7280;">
              Company registration number: 14337517 – Grove Resourcing Group Ltd t/a Edukai<br><br>
              This message is for the designated recipient only and may contain privileged, proprietary or otherwise private information.
              If you have received it in error, please notify the sender immediately and delete the original. Any other use of the email
              by you is prohibited. This email (including attachments, if any) may contain confidential and/or legally privileged information.
              If you receive this email in error, please inform sender immediately and be aware that any unauthorised use or disclosure of this
              email or any of its contents is strictly prohibited. If you have received this in error, please notify us by forwarding this
              email to <a href="mailto:info@edukai.co.uk">info@edukai.co.uk</a> and then delete the email completely from your system.
              This email and any attachments have been scanned for computer viruses. However, it is the responsibility of the recipient to conduct
              its own security measures. No responsibility is accepted by Edukai for loss or damage arising from the receipt or use of this email
              and any attachments. No responsibility is accepted by Edukai for personal emails.
            </td>
          </tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""