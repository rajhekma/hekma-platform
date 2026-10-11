"""Ownership check: a patient token may only touch that patient's records.

Staff roles (SITE, SPONSOR, ADMIN, SYSTEM_ADMIN) may act on a path patient_id.
Everyone else must have JWT userId == patient_id.

Out-of-scope access is 404, not 403, so the record's existence is not leaked.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, HTTPException

from .security import jwt_filter

STAFF_ROLES = frozenset(
    {
        "SITE",
        "SPONSOR",
        "ADMIN",
        "SYSTEM_ADMIN",
        "ADMINISTRATOR",
        "CRC",
        "PI",
        "INVESTIGATOR",
    }
)


def _role(user: Optional[dict]) -> str:
    raw = (user or {}).get("role") or ""
    return str(raw).split(",")[0].strip().upper()


def _user_id(user: Optional[dict]) -> str:
    return str((user or {}).get("userId") or "").strip()


def assert_patient_access(user: Optional[dict], patient_id: str) -> dict:
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHENTICATED", "message": "Sign in required."},
        )
    if _role(user) in STAFF_ROLES:
        return user
    caller = _user_id(user)
    if not caller or caller != str(patient_id).strip():
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Patient not found."},
        )
    return user


def require_patient_access(
    patient_id: str,
    user: Any = Depends(jwt_filter),
) -> dict:
    """FastAPI dependency. Bind `patient_id` from the path."""
    return assert_patient_access(user, patient_id)
