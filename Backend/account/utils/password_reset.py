import secrets
import hashlib

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.utils.crypto import constant_time_compare


# ---------------------------------------------------------------------------
# Cache Key Helpers
# ---------------------------------------------------------------------------
def _otp_key(email: str) -> str:
    return f"pwd-reset:otp:{email.lower()}"

def _otp_attempts_key(email: str) -> str:
    return f"pwd-reset:attempts:{email.lower()}"

def _otp_reqcount_key(email: str) -> str:
    return f"pwd-reset:reqcount:{email.lower()}"

def _otp_cooldown_key(email: str) -> str:
    return f"pwd-reset:cooldown:{email.lower()}"

def _otp_verified_key(email: str) -> str:
    return f"pwd-reset:verified:{email.lower()}"


# ---------------------------------------------------------------------------
# OTP Generation & Hashing
# ---------------------------------------------------------------------------
def generate_numeric_otp(length: int = None) -> str:
    """Generate a cryptographically secure numeric OTP."""
    length = length or getattr(settings, "PASSWORD_RESET_OTP_LENGTH", 6)
    max_val = 10 ** length
    return str(secrets.randbelow(max_val)).zfill(length)

def _hash_otp(otp: str) -> str:
    """Hash the OTP with a pepper before storing."""
    pepper = getattr(settings, "PASSWORD_RESET_OTP_PEPPER", "")
    h = hashlib.sha256()
    h.update((otp + pepper).encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# OTP Storage & Retrieval
# ---------------------------------------------------------------------------
def store_otp_for_email(email: str, otp: str) -> None:
    """Hash and store the OTP in Redis. Reset attempt counter."""
    otp_ttl = getattr(settings, "PASSWORD_RESET_OTP_TTL", 600)
    cooldown_ttl = getattr(settings, "PASSWORD_RESET_RESEND_COOLDOWN", 60)
    req_window = 3600  # 1 hour window for rate limiting

    cache.set(_otp_key(email), _hash_otp(otp), otp_ttl)
    cache.set(_otp_attempts_key(email), 0, otp_ttl)
    cache.set(_otp_cooldown_key(email), 1, cooldown_ttl)

    # Increment hourly request counter
    req_key = _otp_reqcount_key(email)
    count = cache.get(req_key) or 0
    cache.set(req_key, count + 1, req_window)

def get_stored_hashed_otp(email: str):
    return cache.get(_otp_key(email))

def verify_otp(email: str, otp: str) -> bool:
    """Constant-time compare the provided OTP against the stored hash."""
    stored = get_stored_hashed_otp(email)
    if not stored:
        return False
    return constant_time_compare(_hash_otp(otp), stored)

def clear_otp_for_email(email: str) -> None:
    """Remove OTP + attempt keys. Keep request count for rate limiting."""
    cache.delete(_otp_key(email))
    cache.delete(_otp_attempts_key(email))
    cache.delete(_otp_cooldown_key(email))

def increment_verify_attempts(email: str) -> int:
    """Increment and return the current number of failed OTP attempts."""
    otp_ttl = getattr(settings, "PASSWORD_RESET_OTP_TTL", 600)
    key = _otp_attempts_key(email)
    attempts = (cache.get(key) or 0) + 1
    cache.set(key, attempts, otp_ttl)
    return attempts


# ---------------------------------------------------------------------------
# Verified Flag (set after OTP confirmed, consumed on password reset)
# ---------------------------------------------------------------------------
def set_verified_for_email(email: str) -> None:
    """Mark this email as OTP-verified. Valid for a short TTL window."""
    ttl = getattr(settings, "PASSWORD_RESET_VERIFIED_TTL", 600)
    cache.set(_otp_verified_key(email), 1, ttl)

def is_verified_for_email(email: str) -> bool:
    return bool(cache.get(_otp_verified_key(email)))

def clear_verified_for_email(email: str) -> None:
    cache.delete(_otp_verified_key(email))


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------
def can_request_otp(email: str) -> tuple[bool, str, int, int]:
    """
    Returns (allowed, reason, retry_after_seconds, remaining_requests).
    Checks both hourly request cap and per-request cooldown.
    """
    max_per_hour = getattr(settings, "PASSWORD_RESET_MAX_REQUESTS_PER_HOUR", 5)
    count = cache.get(_otp_reqcount_key(email)) or 0

    if count >= max_per_hour:
        return False, "Too many OTP requests. Please try again later.", 3600, 0

    # Check resend cooldown
    cooldown_key = _otp_cooldown_key(email)
    if cache.get(cooldown_key):
        try:
            retry_after = cache.ttl(cooldown_key) or 0
            retry_after = max(0, retry_after)
        except Exception:
            retry_after = getattr(settings, "PASSWORD_RESET_RESEND_COOLDOWN", 60)

        remaining = max(0, max_per_hour - count)
        return False, "Please wait before requesting another OTP.", retry_after, remaining

    remaining = max(0, max_per_hour - count)
    return True, "", 0, remaining


# ---------------------------------------------------------------------------
# Email Sending
# ---------------------------------------------------------------------------
def send_otp_email(email: str, otp: str) -> None:
    """Send the OTP via SendGrid instead of Django SMTP."""
    from django.conf import settings as django_settings

    otp_ttl_minutes = getattr(django_settings, "PASSWORD_RESET_OTP_TTL", 600) // 60
    app_name        = getattr(django_settings, "APP_NAME", "EduKai")

    subject    = f"Your Password Reset OTP - {app_name}"
    plain_text = (
        f"Your OTP for password reset is: {otp}\n"
        f"It expires in {otp_ttl_minutes} minutes.\n\n"
        f"If you did not request this, please ignore this email."
    )
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
        <div style="max-width: 480px; margin: auto; background: #fff; padding: 32px;
                    border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
            <h2 style="color: #1a1a2e; margin-bottom: 8px;">Password Reset Request</h2>
            <p style="color: #555; font-size: 15px;">
                We received a request to reset your password for
                <strong>{app_name}</strong>. Use the OTP below to proceed:
            </p>
            <div style="text-align: center; margin: 28px 0;">
                <span style="display: inline-block; background: #f0f4ff;
                             border: 1px solid #c7d2fe; color: #1a1a2e;
                             font-size: 32px; font-weight: bold;
                             letter-spacing: 8px; padding: 12px 28px;
                             border-radius: 6px;">
                    {otp}
                </span>
            </div>
            <p style="color: #555; font-size: 14px;">
                This OTP expires in <strong>{otp_ttl_minutes} minutes</strong>.
                If you did not request this, you can safely ignore this email.
            </p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
            <p style="color: #aaa; font-size: 12px; text-align: center;">
                &copy; {app_name}. All rights reserved.
            </p>
        </div>
    </body>
    </html>
    """

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import (
            Mail, From, To, Subject,
            HtmlContent, PlainTextContent,
        )

        message = Mail(
            from_email=From(
                django_settings.SENDGRID_FROM_EMAIL,
                django_settings.SENDGRID_FROM_NAME,
            ),
            to_emails=To(email),
            subject=Subject(subject),
            plain_text_content=PlainTextContent(plain_text),
            html_content=HtmlContent(html_body),
        )

        sg       = SendGridAPIClient(django_settings.SENDGRID_API_KEY)
        response = sg.send(message)

        if response.status_code not in (200, 202):
            raise Exception(f"SendGrid returned status {response.status_code}")

    except Exception as exc:
        # Re-raise so the caller can handle it
        raise Exception(f"Failed to send OTP email via SendGrid: {exc}")