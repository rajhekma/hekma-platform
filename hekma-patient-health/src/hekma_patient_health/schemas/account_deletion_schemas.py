"""Pydantic request/response models for account deletion APIs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from ..services.account_deletion.constants import CONFIRM_PHRASE

__all__ = [
    "CONFIRM_PHRASE",
    "RequestDeletionOtpInput",
    "ConfirmDeletionInput",
    "DeletionOtpResponse",
    "DeletionConfirmResponse",
    "RetentionPolicyResponse",
    "PhiPurgeResponse",
]


class RequestDeletionOtpInput(BaseModel):
    """Start deletion OTP. JWT path uses auth; external page uses email+password."""

    email: Optional[str] = Field(
        default=None,
        description="Required for external deletion when Authorization is absent.",
    )
    password: Optional[str] = Field(
        default=None,
        description="Required with email for external deletion identity proof.",
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        if value is None:
            return None
        text = str(value).strip().lower()
        return text or None


class ConfirmDeletionInput(BaseModel):
    """Complete deletion after OTP verification and explicit confirmation."""

    challengeId: str = Field(..., min_length=8, max_length=128)
    otp: str = Field(..., min_length=4, max_length=12)
    confirmation: str = Field(
        ...,
        description=f'Must be exactly "{CONFIRM_PHRASE}" to proceed.',
    )
    reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("challengeId", "otp", "confirmation", mode="before")
    @classmethod
    def strip_text(cls, value):
        return str(value).strip() if value is not None else value

    @field_validator("reason", mode="before")
    @classmethod
    def strip_reason(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class DeletionOtpResponse(BaseModel):
    code: str = "OTP_SENT"
    message: str
    challengeId: str
    maskedEmail: str
    expiresInSeconds: int
    retryAfterSeconds: Optional[int] = None
    # Only present when ACCOUNT_DELETION_OTP_DEV_RETURN=true (local/dev).
    devOtp: Optional[str] = None


class DeletionConfirmResponse(BaseModel):
    code: str = "ACCOUNT_DELETED"
    message: str
    patientId: str
    deletedAt: str
    phiPurgeEligibleAt: str
    phiRetentionYears: int
    flow: List[str] = Field(default_factory=list)
    retainedCategories: List[str] = Field(default_factory=list)
    archivedCategories: List[str] = Field(default_factory=list)


class RetentionPolicyResponse(BaseModel):
    """Public documentation of immediate purge vs PHI archive vs retention."""

    summary: str
    flow: List[str] = Field(default_factory=list)
    deletedCategories: List[str]
    archivedCategories: List[Dict[str, Any]] = Field(default_factory=list)
    retainedCategories: List[Dict[str, Any]]
    phiRetentionYears: int
    phiRetentionDays: int
    confirmationPhrase: str = CONFIRM_PHRASE
    keyRule: str


class PhiPurgeResponse(BaseModel):
    checked: int
    purgedPatientIds: List[str]
    errors: List[Dict[str, str]] = Field(default_factory=list)
    retentionYears: int
