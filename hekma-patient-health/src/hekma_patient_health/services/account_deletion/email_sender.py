"""Outbound email for account-deletion OTP (SendGrid, SMTP fallback, or local log)."""

from __future__ import annotations

import logging
import os
import re
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional, Protocol

logger = logging.getLogger(__name__)

_OTP_DIGIT_RE = re.compile(r"\b\d{6}\b")
_LIVE_ENVS = frozenset(
    {"prod", "production", "live", "staging", "qa", "uat", "test"}
)


class EmailSender(Protocol):
    """Narrow interface so OTP service can swap SendGrid / SMTP / stub."""

    def send(self, to_email: str, subject: str, html_body: str, text_body: str) -> None:
        ...


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    from_email: str
    from_name: str


def resolve_sendgrid_api_key() -> str:
    """Same secret as hekma_api `spring.sendgrid.api-key` when that env is mapped."""
    for name in ("SENDGRID_API_KEY", "SPRING_SENDGRID_API_KEY"):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def resolve_mail_from() -> tuple[str, str]:
    """From address/name; matches hekma_api `otp.mail.from` default."""
    from_email = (
        os.getenv("ACCOUNT_DELETION_MAIL_FROM")
        or os.getenv("OTP_MAIL_FROM")
        or os.getenv("MAIL_FROM")
        or "noreply@hekma.ai"
    ).strip()
    from_name = (
        os.getenv("ACCOUNT_DELETION_MAIL_FROM_NAME")
        or os.getenv("OTP_MAIL_FROM_NAME")
        or "Hekma"
    ).strip()
    return from_email, from_name


def resolve_smtp_settings() -> Optional[SmtpSettings]:
    """SMTP settings from FastAPI or Spring Mail env names."""
    host = (os.getenv("SMTP_HOST") or os.getenv("SPRING_MAIL_HOST") or "").strip()
    if not host:
        return None
    port_raw = (os.getenv("SMTP_PORT") or os.getenv("SPRING_MAIL_PORT") or "587").strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 587
    username = (
        os.getenv("SMTP_USERNAME") or os.getenv("SPRING_MAIL_USERNAME") or ""
    ).strip()
    password = os.getenv("SMTP_PASSWORD") or os.getenv("SPRING_MAIL_PASSWORD") or ""
    tls_raw = (
        os.getenv("SMTP_USE_TLS")
        or os.getenv("SPRING_MAIL_PROPERTIES_MAIL_SMTP_STARTTLS_ENABLE")
        or "true"
    ).strip().lower()
    from_email, from_name = resolve_mail_from()
    return SmtpSettings(
        host=host,
        port=port,
        username=username,
        password=password,
        use_tls=tls_raw in ("1", "true", "yes"),
        from_email=from_email,
        from_name=from_name,
    )


def environment_name() -> str:
    return (
        os.getenv("ACCOUNT_DELETION_ENV")
        or os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("ENV")
        or ""
    ).strip().lower()


def is_live_environment() -> bool:
    """True for deployed review/prod stacks that must email the patient."""
    return environment_name() in _LIVE_ENVS


def require_email_delivery() -> bool:
    """Fail closed when live users cannot receive mail."""
    flag = (os.getenv("ACCOUNT_DELETION_REQUIRE_EMAIL_DELIVERY") or "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    return is_live_environment()


def redact_otp(text: str) -> str:
    """Strip 6-digit codes so logs never carry the OTP."""
    return _OTP_DIGIT_RE.sub("******", text or "")


class SendGridEmailSender:
    """Send one HTML email via SendGrid v3 mail/send API."""

    def __init__(
        self,
        api_key: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
    ):
        resolved_from, resolved_name = resolve_mail_from()
        self.api_key = (api_key if api_key is not None else resolve_sendgrid_api_key()).strip()
        self.from_email = (from_email or resolved_from).strip()
        self.from_name = (from_name or resolved_name).strip()

    def send(self, to_email: str, subject: str, html_body: str, text_body: str) -> None:
        if not self.api_key:
            raise RuntimeError("SENDGRID_API_KEY is not configured")
        if not (to_email or "").strip():
            raise RuntimeError("Recipient email is required")

        import requests

        payload = {
            "personalizations": [{"to": [{"email": to_email.strip()}]}],
            "from": {"email": self.from_email, "name": self.from_name},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text_body},
                {"type": "text/html", "value": html_body},
            ],
        }
        # Keep OTP API snappy: (connect, read). Slow mail should fail fast, not hang Postman.
        response = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(3.05, 10),
        )
        if response.status_code >= 400:
            logger.error(
                "SendGrid OTP email failed status=%s body=%s",
                response.status_code,
                redact_otp((response.text or "")[:200]),
            )
            raise RuntimeError("Failed to send verification email")
        logger.info("SendGrid accepted account deletion OTP email status=%s", response.status_code)


class SmtpEmailSender:
    """Send one multipart email via SMTP (hekma_api JavaMail fallback)."""

    def __init__(self, settings: Optional[SmtpSettings] = None):
        self.settings = settings or resolve_smtp_settings()
        if not self.settings:
            raise RuntimeError("SMTP is not configured")

    def send(self, to_email: str, subject: str, html_body: str, text_body: str) -> None:
        if not (to_email or "").strip():
            raise RuntimeError("Recipient email is required")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((self.settings.from_name, self.settings.from_email))
        msg["To"] = to_email.strip()
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(self.settings.host, self.settings.port, timeout=8) as smtp:
            if self.settings.use_tls:
                smtp.starttls()
            if self.settings.username:
                smtp.login(self.settings.username, self.settings.password)
            smtp.sendmail(self.settings.from_email, [to_email.strip()], msg.as_string())
        logger.info("SMTP accepted account deletion OTP email")


def is_sendgrid_smtp_host(host: str | None) -> bool:
    """True when SMTP is just another path into SendGrid (redundant with API key)."""
    return (host or "").strip().lower() in {
        "smtp.sendgrid.net",
        "smtp.sendgrid.com",
    }


class CompositeEmailSender:
    """Try SendGrid first, then a non-SendGrid SMTP fallback."""

    def __init__(self, primary: EmailSender, fallback: EmailSender):
        self.primary = primary
        self.fallback = fallback

    def send(self, to_email: str, subject: str, html_body: str, text_body: str) -> None:
        try:
            self.primary.send(to_email, subject, html_body, text_body)
        except Exception as exc:
            logger.warning(
                "Primary OTP mailer failed (%s); trying SMTP fallback",
                type(exc).__name__,
            )
            self.fallback.send(to_email, subject, html_body, text_body)


class LoggingEmailSender:
    """Local/dev only: log that an email would be sent; never print the OTP."""

    def send(self, to_email: str, subject: str, html_body: str, text_body: str) -> None:
        logger.info(
            "Account deletion OTP email (log-only) to=%s subject=%s text=%s",
            to_email,
            subject,
            redact_otp(text_body),
        )


class UnconfiguredEmailSender:
    """Live fail-closed sender when no mail provider is configured."""

    def send(self, to_email: str, subject: str, html_body: str, text_body: str) -> None:
        raise RuntimeError(
            "OTP email is not configured. Set SENDGRID_API_KEY (or SMTP_HOST) "
            "so live users receive the code by email."
        )


def build_email_sender() -> EmailSender:
    """SendGrid when keyed; SMTP fallback; log-only locally; fail closed on live.

    When SENDGRID_API_KEY is set and SMTP points at smtp.sendgrid.net, use the
    HTTP API only. Dual SendGrid paths doubled latency and often hung Postman
    ("no output") when the API call was slow and SMTP then failed with a bad user.
    """
    api_key = resolve_sendgrid_api_key()
    smtp = resolve_smtp_settings()
    force_smtp_fallback = (
        os.getenv("ACCOUNT_DELETION_SMTP_FALLBACK", "").strip().lower()
        in ("1", "true", "yes")
    )
    if api_key and smtp and (force_smtp_fallback or not is_sendgrid_smtp_host(smtp.host)):
        return CompositeEmailSender(SendGridEmailSender(api_key=api_key), SmtpEmailSender(smtp))
    if api_key:
        if smtp and is_sendgrid_smtp_host(smtp.host):
            logger.info(
                "Using SendGrid HTTP API only (skipping redundant smtp.sendgrid.net fallback)"
            )
        return SendGridEmailSender(api_key=api_key)
    if smtp:
        return SmtpEmailSender(smtp)
    if require_email_delivery():
        logger.error(
            "Account deletion OTP requires email delivery but no SendGrid/SMTP is configured"
        )
        return UnconfiguredEmailSender()
    return LoggingEmailSender()
