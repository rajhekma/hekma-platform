"""Orchestrates staged account deletion: immediate archive + delayed PHI purge."""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any, Dict, Optional

import bcrypt

from ...repositories.account_deletion_repo import AccountDeletionRepository
from .constants import CONFIRM_PHRASE, phi_retention_days, phi_retention_years
from .exceptions import (
    AccountAlreadyDeletedError,
    AccountNotFoundError,
    ConfirmationRequiredError,
    DeletionFailedError,
    InvalidCredentialsError,
)
from .otp_service import AccountDeletionOtpService

logger = logging.getLogger(__name__)


class AccountDeletionService:
    """Google Play deletion with healthcare PHI archive + configurable retention."""

    def __init__(
        self,
        repository: Optional[AccountDeletionRepository] = None,
        otp_service: Optional[AccountDeletionOtpService] = None,
        redis_client=None,
    ):
        self.repo = repository or AccountDeletionRepository()
        if redis_client is None:
            try:
                from ...redis_service import get_redis_client

                redis_client = get_redis_client()
            except Exception:
                redis_client = None
        self.redis = redis_client
        self.otp_service = otp_service or AccountDeletionOtpService(
            redis_client=redis_client
        )

    def retention_policy(self) -> Dict[str, Any]:
        """Public copy for Privacy Policy / Data Safety documentation."""
        years = phi_retention_years()
        return {
            "summary": (
                "On deletion request: sessions are revoked, non-PHI (tokens, preferences, "
                "analytics caches) is purged immediately, and PHI is locked in an "
                f"inaccessible archive. PHI is hard-deleted only after {years} year(s) "
                "(configurable via ACCOUNT_DELETION_PHI_RETENTION_YEARS)."
            ),
            "flow": [
                "DELETE_REQUEST",
                "REVOKE_AND_DEACTIVATE",
                "PURGE_NON_PHI",
                "ARCHIVE_PHI",
                "AUDIT_LOG",
                "SCHEDULED_PURGE",
            ],
            "deletedCategories": [
                "Authentication credentials and login identifiers",
                "Profile contact fields used for app access",
                "Device tokens, notification prefs, and analytics/cache keys",
                "EHR sync linkage (Fasten controller / summary cache)",
                "Active sessions and JWT tokens for the current device",
            ],
            "archivedCategories": [
                {
                    "category": "Clinical / PHI records",
                    "reason": "Healthcare regulatory retention; no app access after deletion",
                    "retention": f"{years} year(s), then scheduled hard purge",
                },
                {
                    "category": "Uploaded clinical scans and HealthKit payloads",
                    "reason": "Treated as PHI; locked until retention elapses",
                    "retention": f"{years} year(s), then scheduled hard purge",
                },
                {
                    "category": "Medications and related clinical history",
                    "reason": "Clinical data retained under archive lock",
                    "retention": f"{years} year(s), then scheduled hard purge",
                },
            ],
            "retainedCategories": [
                {
                    "category": "Study participation identifiers",
                    "reason": "Clinical trial / regulatory retention",
                    "retention": "Per study protocol (may outlive PHI archive purge)",
                },
                {
                    "category": "Audit and compliance logs",
                    "reason": "Immutable record of deletion request and later PHI purge",
                    "retention": "Per organizational retention policy",
                },
            ],
            "phiRetentionYears": years,
            "phiRetentionDays": phi_retention_days(),
            "confirmationPhrase": CONFIRM_PHRASE,
            "keyRule": (
                "PHI is never hard-deleted on request. Steps 1–3 are immediate; "
                "PHI moves to a locked archive (step 4) and is only permanently purged "
                "once the configured retention period lapses (step 6)."
            ),
        }

    def request_otp(
        self,
        *,
        jwt_claims: Optional[Dict[str, Any]] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve the target account and send a deletion OTP."""
        patient = self._resolve_patient_for_otp(
            jwt_claims=jwt_claims, email=email, password=password
        )
        patient_id = str(patient["patientId"])

        # Priority 1: AUTH_USER_DETAILS (emailId / userLoginId) where sponsorAccountUserId = patient_id
        auth = self.repo.get_auth_user(patient_id=patient_id)
        target_email = ""
        if auth:
            target_email = (auth.get("emailId") or auth.get("userLoginId") or "").strip()

        # Priority 2: Patient.email
        if not target_email:
            target_email = (patient.get("email") or "").strip()

        # Priority 3: Request payload email
        if not target_email and email:
            target_email = email.strip()

        if not target_email:
            raise AccountNotFoundError("Account email is missing; contact support.")

        return self.otp_service.send_otp(patient_id=patient_id, email=target_email)

    def confirm_deletion(
        self,
        *,
        challenge_id: str,
        otp: str,
        confirmation: str,
        reason: Optional[str] = None,
        raw_jwt: Optional[str] = None,
        jwt_claims: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Verify OTP, then run immediate archive flow (steps 1–5)."""
        if (confirmation or "").strip() != CONFIRM_PHRASE:
            raise ConfirmationRequiredError()

        verified = self.otp_service.verify_otp(challenge_id=challenge_id, otp=otp)
        patient_id = verified["patientId"]
        if not patient_id:
            raise DeletionFailedError("Deletion challenge is missing patient identity.")

        if jwt_claims and jwt_claims.get("userId"):
            if str(jwt_claims["userId"]) != str(patient_id):
                raise InvalidCredentialsError(
                    "Authenticated user does not match the deletion challenge."
                )

        try:
            result = self.repo.archive_account_on_deletion_request(
                patient_id=patient_id,
                email=verified.get("email"),
                reason=reason,
                retention_years=phi_retention_years(),
                retention_days=phi_retention_days(),
            )
        except LookupError as exc:
            if str(exc) == "already_deleted":
                raise AccountAlreadyDeletedError() from exc
            if str(exc) == "patient_not_found":
                raise AccountNotFoundError() from exc
            raise DeletionFailedError() from exc
        except Exception as exc:
            logger.exception("Account deletion archive failed patient_id=%s", patient_id)
            raise DeletionFailedError() from exc

        # Step 2: revoke sessions + stop EHR sync surfaces.
        self._invalidate_session(raw_jwt)
        self._best_effort_clear_cache(result)
        self._best_effort_deactivate_stream_user(patient_id)
        self._best_effort_revoke_fasten(result.get("email"))

        years = result["phiRetentionYears"]
        return {
            "code": "ACCOUNT_DELETED",
            "patientId": result["patientId"],
            "deletedAt": result["deletedAt"],
            "phiPurgeEligibleAt": result["phiPurgeEligibleAt"],
            "phiRetentionYears": years,
            "flow": result["flow"],
            "message": (
                "Your account has been deleted. Access is revoked immediately. "
                f"Clinical data is retained in a locked archive for {years} year(s), "
                "then permanently purged."
            ),
            "retainedCategories": [
                item["category"] for item in self.retention_policy()["retainedCategories"]
            ],
            "archivedCategories": [
                item["category"] for item in self.retention_policy()["archivedCategories"]
            ],
        }

    def run_scheduled_phi_purge(self, *, limit: int = 100) -> Dict[str, Any]:
        """Step 6 worker: hard-delete PHI rows past purge_eligible_at."""
        return self.repo.purge_due_archived_phi(
            limit=limit, retention_years=phi_retention_years()
        )

    def _resolve_patient_for_otp(
        self,
        *,
        jwt_claims: Optional[Dict[str, Any]],
        email: Optional[str],
        password: Optional[str],
    ) -> Dict[str, Any]:
        if jwt_claims and jwt_claims.get("userId"):
            patient = self.repo.get_patient_by_id(str(jwt_claims["userId"]))
            if not patient:
                raise AccountNotFoundError()
            if str(patient.get("status") or "").upper() in ("DELETED", "ARCHIVED"):
                raise AccountAlreadyDeletedError()
            return patient

        if not email or not password:
            raise InvalidCredentialsError(
                "Provide Authorization JWT, or email and password."
            )

        auth = self.repo.get_auth_user(email=email)
        if not auth or not auth.get("passwordHash"):
            raise InvalidCredentialsError()
        if not self._password_matches(password, auth["passwordHash"]):
            raise InvalidCredentialsError()

        patient_id = str(auth.get("sponsorAccountUserId") or "")
        patient = self.repo.get_patient_by_id(patient_id) if patient_id else None
        if not patient:
            patient = self.repo.get_patient_by_email(email)
        if not patient:
            raise AccountNotFoundError()
        if str(patient.get("status") or "").upper() in ("DELETED", "ARCHIVED"):
            raise AccountAlreadyDeletedError()
        return patient

    @staticmethod
    def _password_matches(plain: str, password_hash: str) -> bool:
        """Match bcrypt hashes, or plaintext (legacy AUTH_USER_DETAILS / Java login)."""
        stored = (password_hash or "").strip()
        if not plain or not stored:
            return False
        # Spring Security 4 login historically used NoOp; most rows store plaintext.
        if stored.startswith(("$2a$", "$2b$", "$2y$")):
            try:
                return bcrypt.checkpw(
                    plain.encode("utf-8"),
                    stored.encode("utf-8"),
                )
            except (ValueError, TypeError):
                return False
        return secrets.compare_digest(plain, stored)

    def _invalidate_session(self, raw_jwt: Optional[str]) -> None:
        """Blacklist the caller's JWT until natural expiry (matches /logout)."""
        if not raw_jwt or self.redis is None:
            return
        try:
            ttl_seconds = self._token_ttl_seconds(raw_jwt)
            if ttl_seconds <= 0:
                return
            self.redis.set(f"blacklist:token:{raw_jwt}", "true", ex=ttl_seconds)
        except Exception:
            logger.warning("Failed to blacklist JWT after account deletion", exc_info=True)

    @staticmethod
    def _token_ttl_seconds(raw_jwt: str) -> int:
        try:
            import jwt as pyjwt

            payload = pyjwt.decode(
                raw_jwt,
                options={"verify_signature": False, "verify_exp": False},
            )
            exp = int(payload.get("exp") or 0)
            if not exp:
                return int(os.getenv("ACCOUNT_DELETION_TOKEN_BLACKLIST_TTL", "7200"))
            import time

            return max(int(exp - time.time()), 0)
        except Exception:
            return int(os.getenv("ACCOUNT_DELETION_TOKEN_BLACKLIST_TTL", "7200"))

    def _best_effort_clear_cache(self, result: Dict[str, Any]) -> None:
        try:
            from ...redis_service import del_key_list

            patient_id = result.get("patientId")
            subject_id = result.get("subjectId") or patient_id
            email = result.get("email") or ""
            del_key_list(["details", patient_id, subject_id, email], 2)
            del_key_list(["header", subject_id, patient_id, email], 2)
            if email:
                # Email-only 360 keys: header__{email}_ / details_*_{email}_
                del_key_list(["header", email], 2)
                del_key_list(["details", email], 2)
        except Exception:
            logger.warning("Cache cleanup after deletion failed", exc_info=True)

    def _best_effort_deactivate_stream_user(self, patient_id: str) -> None:
        try:
            from ...getstream.get_stream_util import get_getstream_secrets

            _, client = get_getstream_secrets()
            if hasattr(client, "deactivate_user"):
                client.deactivate_user(str(patient_id))
            elif hasattr(client, "delete_user"):
                client.delete_user(str(patient_id), mark_messages_deleted=False)
        except Exception:
            logger.warning(
                "GetStream user deactivate failed patient_id=%s",
                patient_id,
                exc_info=True,
            )

    def _best_effort_revoke_fasten(self, email: Optional[str]) -> None:
        if not email:
            return
        try:
            from ...fasten_health.fasten_handler import revoke_vault_connections

            revoke_vault_connections(email)
        except Exception:
            logger.info(
                "Fasten vault revoke skipped or failed for deleted account",
                exc_info=True,
            )
