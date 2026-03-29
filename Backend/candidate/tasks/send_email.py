import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)

AVAILABILITY_EMAIL_SUBJECT = "New Opportunity — Are You Available?"

AVAILABILITY_EMAIL_PLAIN = """
Are you looking for a new challenge?

Schools need passionate, reliable, and inspiring Educators and Support Staff
now more than ever. If you're ready for your next opportunity, we are ready
for you!

WE ARE THE EDUCATION SPECIALISTS AGENCY

Whether you're looking for flexibility, progression, or your next temp role,
let's get you placed where you can truly shine.

Interested? Reply to this email with:
- Your availability (what date can you start?)
- Full-time or part-time preference?
- Your location?
- Job title(s) you're looking for?

Up to 250 pounds refer-a-friend bonus! (T&Cs apply)

Share with friends, family and colleagues.
Your next role could be one message away.

Education Specialists Agency
kai.smith@edukai.co.uk
"""

AVAILABILITY_EMAIL_BODY = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
</head>
<body style="font-family: Arial, sans-serif; font-size: 14px; color: #222; max-width: 600px; margin: 0 auto; padding: 20px;">

  <p>Are you looking for a new challenge?</p>

  <p>
    Schools need passionate, reliable, and inspiring
    <strong>Educators &amp; Support Staff</strong> now more than ever.
    If you are ready for your next opportunity, we are ready for you!
  </p>

  <p><strong>WE ARE THE EDUCATION SPECIALISTS AGENCY</strong></p>

  <p>
    Whether you are looking for flexibility, progression, or your next temp role,
    let us get you placed where you can truly shine.
  </p>

  <p><strong>Interested? Reply to this email with:</strong></p>
  <ul>
    <li>Your availability — what date can you start?</li>
    <li>Full-time or part-time preference?</li>
    <li>Your location?</li>
    <li>Job title(s) you are looking for?</li>
  </ul>

  <p>
    <strong>Up to &pound;250 refer-a-friend bonus!</strong> (T&amp;Cs apply)
  </p>

  <p>Share with friends, family &amp; colleagues.</p>
  <p>Your next role could be one message away.</p>

  <br>
  <p style="color: #555; font-size: 12px;">
    Education Specialists Agency<br>
    <a href="mailto:kai.smith@edukai.co.uk">kai.smith@edukai.co.uk</a>
  </p>

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
    """
    Sends availability email to candidate via SendGrid.
    From:     job@edukai.co.uk  (domain-authenticated sender)
    Reply-To: kai.smith@edukai.co.uk  (replies go to system owner)
    """
    from candidate.models import Candidate

    # ── Guard: skip if SendGrid not configured ────────────────────────────
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
        logger.info(
            f"[send_email] Candidate {candidate_id} has no email. Skipping."
        )
        return

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import (
            Mail, From, To, Subject,
            HtmlContent, PlainTextContent, ReplyTo,
        )

        message = Mail(
            from_email=From(settings.SENDGRID_FROM_EMAIL, settings.SENDGRID_FROM_NAME),
            to_emails=To(candidate.email),
            subject=Subject(AVAILABILITY_EMAIL_SUBJECT),
            plain_text_content=PlainTextContent(AVAILABILITY_EMAIL_PLAIN),
            html_content=HtmlContent(AVAILABILITY_EMAIL_BODY),
        )

        # ✅ Replies go to kai.smith@edukai.co.uk not job@edukai.co.uk
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
            raise self.retry(
                exc=Exception(f"SendGrid status: {response.status_code}")
            )

    except Exception as exc:
        logger.error(
            f"[send_email] Failed to send email for candidate {candidate_id}: {exc}"
        )
        raise self.retry(exc=exc)