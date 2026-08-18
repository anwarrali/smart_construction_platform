"""Email delivery through optional production SMTP configuration."""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def _deliver(*, to_email: str, subject: str, body: str) -> bool:
    if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
        logger.warning("Email delivery is disabled because SMTP_HOST/SMTP_FROM_EMAIL are not configured")
        return False
    email = EmailMessage()
    email["From"] = settings.SMTP_FROM_EMAIL
    email["To"] = to_email
    email["Subject"] = subject
    email.set_content(body)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as client:
            if settings.SMTP_USE_TLS:
                client.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            client.send_message(email)
        return True
    except (OSError, smtplib.SMTPException):
        logger.exception("Email delivery failed for recipient %s", to_email)
        return False


def send_invitation_email(
    *,
    to_email: str,
    full_name: str,
    temporary_password: str,
    role_label: str,
    invited_by: str,
    login_url: str | None = None,
) -> bool:
    """Send account invitation with temporary credentials."""
    subject = "Your Construction Platform account invitation"
    body = (
        f"Hello {full_name},\n\n"
        f"You have been invited to the Construction Platform as {role_label} by {invited_by}.\n\n"
        f"Login URL: {login_url or settings.FRONTEND_URL + '/auth/login'}\n"
        f"Email: {to_email}\n"
        f"Temporary password: {temporary_password}\n\n"
        f"You must change your password on first login.\n"
    )
    return _deliver(to_email=to_email, subject=subject, body=body)


def send_step_up_code_email(
    *,
    to_email: str,
    full_name: str,
    action_label: str,
    code: str,
    expires_minutes: int,
) -> bool:
    """Send a step-up verification code.

    The code is passed straight to SMTP and never returned, stored or logged
    by this function — `_deliver` logs only the recipient on failure, never
    the body.
    """
    subject = "Your Struct IQ verification code"
    body = (
        f"Hello {full_name},\n\n"
        f"A verification code was requested to confirm this action: {action_label}.\n\n"
        f"Your code is: {code}\n\n"
        f"It expires in {expires_minutes} minutes and can be used once.\n\n"
        f"If you did not request this, do not share the code — someone may have "
        f"access to your session. Change your password and contact your administrator.\n"
    )
    return _deliver(to_email=to_email, subject=subject, body=body)


def send_password_reset_email(
    *,
    to_email: str,
    full_name: str,
    reset_url: str,
    expires_minutes: int = 60,
) -> bool:
    """Send password reset link."""
    subject = "Reset your Construction Platform password"
    body = (
        f"Hello {full_name},\n\n"
        f"Use the link below to reset your password. This link expires in {expires_minutes} minutes.\n\n"
        f"{reset_url}\n\n"
        f"If you did not request this, ignore this email.\n"
    )
    return _deliver(to_email=to_email, subject=subject, body=body)
