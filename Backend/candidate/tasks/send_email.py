import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)

AVAILABILITY_EMAIL_SUBJECT = "Quick check-in about your availability for new roles"


def _get_display_name(candidate) -> str:
    """
    Prefer surname-less name, then full name, then fallback.
    """
    return (
        (candidate.name_without_surname or "").strip()
        or (candidate.name or "").strip()
        or "there"
    )


def _build_availability_plain(name: str) -> str:
    return f"""Hi {name},

I hope you're doing well.

I'm reaching out to check your current availability for new opportunities in education.

We are currently working with several schools looking for educators and support staff. If you are open to new roles, I would be happy to discuss suitable options with you.

If you're interested, could you please reply with:
- Your availability (start date)
- Preferred working pattern (full-time / part-time)
- Your location
- Roles you are interested in

Best regards,  
Kai Smith  
Education Specialists Agency  
kai.smith@edukai.co.uk
"""


def _build_availability_html(name: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<body style="margin:0; padding:0; background-color:#f4f6f8; font-family:Arial, sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0" style="padding: 30px 0;">
    <tr>
      <td align="center">

        <table width="600" cellpadding="0" cellspacing="0" 
               style="background:#ffffff; border-radius:8px; padding:30px; box-shadow:0 2px 6px rgba(0,0,0,0.05);">

          <tr>
            <td style="font-size:16px; color:#333;">
              
              <p>Hi <strong>{name}</strong>,</p>

              <p>I hope you're doing well.</p>

              <p>
                I wanted to check your availability for potential opportunities 
                within education. We are currently working with a number of schools 
                seeking educators and support staff.
              </p>

              <p>
                If you are open to new roles, I would be happy to discuss options 
                that match your experience and preferences.
              </p>

              <p><strong>Please let me know:</strong></p>
              <ul>
                <li>Your availability (start date)</li>
                <li>Preferred working pattern (full-time / part-time)</li>
                <li>Your location</li>
                <li>Roles you are interested in</li>
              </ul>

              <div style="text-align:center; margin: 30px 0;">
                <a href="mailto:kai.smith@edukai.co.uk"
                   style="background:#2563eb; color:#ffffff; padding:12px 20px; 
                          text-decoration:none; border-radius:5px; font-weight:bold;">
                  Reply to this email
                </a>
              </div>

              <p>Best regards,<br>
              <strong>Kai Smith</strong><br>
              Education Specialists Agency</p>

              <hr style="border:none; border-top:1px solid #eee; margin:30px 0;">

              <p style="font-size:12px; color:#777;">
                Education Specialists Agency<br>
                Email: kai.smith@edukai.co.uk<br>
                (This is a professional outreach regarding job opportunities)
              </p>

            </td>
          </tr>

        </table>

      </td>
    </tr>
  </table>

</body>
</html>
"""


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="candidate.tasks.send_availability_email",
)
def send_availability_email_task(self, candidate_id: str):
    from candidate.models import Candidate

    if not settings.SENDGRID_API_KEY:
        logger.warning(
            f"[send_email] SENDGRID_API_KEY not set. "
            f"Skipping email for candidate {candidate_id}."
        )
        return

    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        logger.error(f"[send_email] Candidate {candidate_id} not found.")
        return

    if not candidate.email:
        logger.info(f"[send_email] Candidate {candidate_id} has no email. Skipping.")
        return

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import (
            Mail, From, To, Subject,
            HtmlContent, PlainTextContent, ReplyTo,
        )

        display_name = _get_display_name(candidate)
        plain_body = _build_availability_plain(display_name)
        html_body = _build_availability_html(display_name)

        message = Mail(
            from_email=From(settings.SENDGRID_FROM_EMAIL, settings.SENDGRID_FROM_NAME),
            to_emails=To(candidate.email),
            subject=Subject(AVAILABILITY_EMAIL_SUBJECT),
            plain_text_content=PlainTextContent(plain_body),
            html_content=HtmlContent(html_body),
        )

        if settings.SENDGRID_REPLY_TO_EMAIL:
            message.reply_to = ReplyTo(
                email=settings.SENDGRID_REPLY_TO_EMAIL,
                name=settings.SENDGRID_REPLY_TO_NAME or None,
            )

        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)

        if response.status_code in (200, 202):
            logger.info(
                f"[send_email] ✅ Email sent to {candidate.email} "
                f"for candidate {candidate_id}. "
                f"SendGrid status: {response.status_code}"
            )
        else:
            logger.warning(
                f"[send_email] Unexpected SendGrid status {response.status_code} "
                f"for candidate {candidate_id}."
            )
            raise self.retry(exc=Exception(f"SendGrid status: {response.status_code}"))

    except Exception as exc:
        logger.error(f"[send_email] Failed to send email for candidate {candidate_id}: {exc}")
        raise self.retry(exc=exc)