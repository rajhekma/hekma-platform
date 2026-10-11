"""Redis-backed OTP challenges for account deletion confirmation."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import uuid
from typing import Any, Dict, Optional, Protocol, Tuple

from .email_sender import EmailSender, build_email_sender
from .exceptions import OtpError

logger = logging.getLogger(__name__)

CHALLENGE_KEY_PREFIX = "account:deletion:otp:"
RESEND_KEY_PREFIX = "account:deletion:resend:"
LOCK_KEY_PREFIX = "account:deletion:lock:"


class RedisClient(Protocol):
    def get(self, name: str) -> Any: ...
    def set(self, name: str, value: Any, ex: Optional[int] = None) -> Any: ...
    def delete(self, *names: str) -> Any: ...
    def exists(self, *names: str) -> int: ...
    def incr(self, name: str) -> int: ...
    def expire(self, name: str, time: int) -> Any: ...
    def ttl(self, name: str) -> int: ...


class AccountDeletionOtpService:
    """Issue and verify hashed OTPs for permanent account deletion."""

    def __init__(
        self,
        redis_client: RedisClient,
        email_sender: Optional[EmailSender] = None,
        pepper: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        max_attempts: Optional[int] = None,
        lock_ttl_seconds: Optional[int] = None,
        resend_cooldown_seconds: Optional[int] = None,
    ):
        self.redis = redis_client
        self.email_sender = email_sender or build_email_sender()
        self.pepper = (
            pepper
            or os.getenv("ACCOUNT_DELETION_OTP_PEPPER")
            or os.getenv("OTP_PEPPER")
            or "hekma-account-deletion-pepper"
        )
        self.ttl_seconds = int(
            ttl_seconds
            if ttl_seconds is not None
            else os.getenv("ACCOUNT_DELETION_OTP_TTL_SECONDS", "600")
        )
        self.max_attempts = int(
            max_attempts
            if max_attempts is not None
            else os.getenv("ACCOUNT_DELETION_OTP_MAX_ATTEMPTS", "5")
        )
        self.lock_ttl_seconds = int(
            lock_ttl_seconds
            if lock_ttl_seconds is not None
            else os.getenv("ACCOUNT_DELETION_OTP_LOCK_TTL_SECONDS", "1800")
        )
        self.resend_cooldown_seconds = int(
            resend_cooldown_seconds
            if resend_cooldown_seconds is not None
            else os.getenv("ACCOUNT_DELETION_OTP_RESEND_COOLDOWN_SECONDS", "60")
        )

    def send_otp(self, *, patient_id: str, email: str) -> Dict[str, Any]:
        """Create a challenge, email the code, return challenge metadata (never the OTP)."""
        normalized_email = self._normalize_email(email)
        if not normalized_email:
            raise OtpError("INVALID_EMAIL", "A valid email address is required.")

        if self.redis.exists(LOCK_KEY_PREFIX + normalized_email):
            ttl = max(self.redis.ttl(LOCK_KEY_PREFIX + normalized_email), 0)
            raise OtpError(
                "OTP_LOCKED",
                "Too many attempts. Please try again later.",
                retry_after=ttl or self.lock_ttl_seconds,
            )

        resend_key = RESEND_KEY_PREFIX + normalized_email
        if self.redis.exists(resend_key):
            ttl = max(self.redis.ttl(resend_key), 0)
            raise OtpError(
                "OTP_RESEND_COOLDOWN",
                "Please wait before requesting another code.",
                retry_after=ttl or self.resend_cooldown_seconds,
            )

        challenge_id = str(uuid.uuid4())
        otp = f"{secrets.randbelow(1_000_000):06d}"
        payload = {
            "patientId": str(patient_id),
            "email": normalized_email,
            "otpHash": self._hash_otp(challenge_id, otp),
            "attempts": 0,
        }
        self.redis.set(
            CHALLENGE_KEY_PREFIX + challenge_id,
            json.dumps(payload),
            ex=self.ttl_seconds,
        )
        self.redis.set(resend_key, "1", ex=self.resend_cooldown_seconds)

        subject, text_body, html_body = self._otp_email_content(otp)
        try:
            self.email_sender.send(normalized_email, subject, html_body, text_body)
        except Exception:
            self.redis.delete(CHALLENGE_KEY_PREFIX + challenge_id, resend_key)
            logger.exception(
                "Failed to send account deletion OTP email=%s",
                self.mask_email(normalized_email),
            )
            raise OtpError(
                "OTP_SEND_FAILED",
                "We could not send the verification code. Please try again.",
            )
        logger.info(
            "Account deletion OTP emailed to %s",
            self.mask_email(normalized_email),
        )

        # Dev-only: surface OTP when explicitly enabled (never in production config).
        include_dev_otp = (
            os.getenv("ACCOUNT_DELETION_OTP_DEV_RETURN", "false").lower() == "true"
        )
        result: Dict[str, Any] = {
            "challengeId": challenge_id,
            "maskedEmail": self.mask_email(normalized_email),
            "expiresInSeconds": self.ttl_seconds,
            "message": "Verification code sent.",
        }
        if include_dev_otp:
            result["devOtp"] = otp
        return result

    def verify_otp(self, *, challenge_id: str, otp: str) -> Dict[str, str]:
        """Validate OTP; returns patientId/email and consumes the challenge on success."""
        challenge_id = (challenge_id or "").strip()
        otp = (otp or "").strip()
        if not challenge_id or not otp:
            raise OtpError("OTP_REQUIRED", "Challenge ID and OTP code are required.")

        key = CHALLENGE_KEY_PREFIX + challenge_id
        raw = self.redis.get(key)
        if not raw:
            raise OtpError("OTP_EXPIRED", "Verification code expired or not found.")

        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            self.redis.delete(key)
            raise OtpError("OTP_EXPIRED", "Verification code expired or not found.")

        email = payload.get("email") or ""
        if email and self.redis.exists(LOCK_KEY_PREFIX + email):
            raise OtpError(
                "OTP_LOCKED",
                "Too many failed attempts. Please try again later.",
            )

        expected = payload.get("otpHash")
        actual = self._hash_otp(challenge_id, otp)
        if not expected or not hmac.compare_digest(str(expected), actual):
            attempts = int(payload.get("attempts") or 0) + 1
            payload["attempts"] = attempts
            ttl = max(self.redis.ttl(key), 1)
            self.redis.set(key, json.dumps(payload), ex=ttl)
            if attempts >= self.max_attempts and email:
                self.redis.set(LOCK_KEY_PREFIX + email, "1", ex=self.lock_ttl_seconds)
                self.redis.delete(key)
            raise OtpError("OTP_INVALID", "Invalid verification code.")

        self.redis.delete(key)
        return {
            "patientId": str(payload.get("patientId") or ""),
            "email": email,
        }

    def mask_email(self, email: str) -> str:
        """Mask local-part for API responses without leaking full address."""
        normalized = self._normalize_email(email) or ""
        if "@" not in normalized:
            return "***"
        local, _, domain = normalized.partition("@")
        if len(local) <= 2:
            masked_local = "*" * len(local)
        else:
            masked_local = local[0] + ("*" * (len(local) - 2)) + local[-1]
        return f"{masked_local}@{domain}"

    def _hash_otp(self, challenge_id: str, otp: str) -> str:
        material = f"{challenge_id}:{otp}:{self.pepper}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def _otp_email_content(self, otp: str) -> Tuple[str, str, str]:
        """Subject + plain/HTML bodies; matches live login-OTP email layout."""
        expires_minutes = max(self.ttl_seconds // 60, 1)
        subject = "Confirm permanent deletion of your Hekma account"
        text_body = (
            f"Your Hekma account deletion code is {otp}. "
            f"It expires in {expires_minutes} minutes. "
            "If you did not request this, ignore this email and your account will stay active."
        )
        safe_otp = html.escape(otp)
        html_body = (
            "<!DOCTYPE html><html><head><meta charset=\"UTF-8\">"
            "<title>Account deletion verification code</title></head>"
            "<body style=\"font-family: Arial, sans-serif; background-color: #f8f9fa; "
            "padding: 20px; color: #333;\">"
            "<div style=\"max-width: 600px; background-color: #ffffff; padding: 30px; "
            "margin: 0 auto; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1);\">"
            "<h2>Confirm deletion of your HEKMA account</h2>"
            "<p>Use this verification code to permanently delete your account:</p>"
            f"<p style=\"font-size: 28px; font-weight: bold; letter-spacing: 4px; "
            f"color: #0d6efd;\">{safe_otp}</p>"
            f"<p style=\"font-size: 0.9em; color: #666;\">This code expires in "
            f"{expires_minutes} minutes. If you did not request this, ignore this email "
            "and your account will stay active.</p>"
            "</div></body></html>"
        )
        return subject, text_body, html_body

    @staticmethod
    def _normalize_email(email: Optional[str]) -> Optional[str]:
        if email is None:
            return None
        text = str(email).strip().lower()
        if not text or "@" not in text or text.startswith("@") or text.endswith("@"):
            return None
        local, _, domain = text.partition("@")
        if not local or "." not in domain:
            return None
        return text
