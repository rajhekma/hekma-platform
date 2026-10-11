"""REST endpoints for staged account deletion + scheduled PHI purge."""

from __future__ import annotations

import logging
import os
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials

from ..auth.security import (
    authenticate_authorization_header,
    http_bearer,
    is_valid_cache_reprocess_credential,
)
from ..schemas.account_deletion_schemas import (
    ConfirmDeletionInput,
    DeletionConfirmResponse,
    DeletionOtpResponse,
    PhiPurgeResponse,
    RequestDeletionOtpInput,
    RetentionPolicyResponse,
)
from ..services.account_deletion.account_deletion_service import AccountDeletionService
from ..services.account_deletion.dependencies import get_account_deletion_service
from ..services.account_deletion.exceptions import AccountDeletionError, OtpError

router = APIRouter(prefix="/api/account", tags=["Account Deletion"])
logger = logging.getLogger(__name__)


def optional_jwt(
    request: Request,
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(http_bearer)
    ] = None,
    authorization: Annotated[
        Optional[str],
        Header(alias="Authorization", include_in_schema=False),
    ] = None,
) -> Optional[dict]:
    """Return JWT claims when Authorization is present; otherwise None."""
    if request.method == "OPTIONS":
        return None

    header_value = authorization
    if not header_value and credentials and credentials.credentials:
        scheme = (credentials.scheme or "Bearer").strip() or "Bearer"
        header_value = f"{scheme} {credentials.credentials}"
    if not header_value or not str(header_value).strip():
        return None
    return authenticate_authorization_header(header_value)


def _extract_raw_token(
    authorization: Optional[str],
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[str]:
    header_value = authorization
    if not header_value and credentials and credentials.credentials:
        scheme = (credentials.scheme or "Bearer").strip() or "Bearer"
        header_value = f"{scheme} {credentials.credentials}"
    if not header_value:
        return None
    try:
        from ..auth.security import _extract_token

        return _extract_token(header_value)
    except HTTPException:
        return None


def _map_error(exc: AccountDeletionError) -> HTTPException:
    status = 400
    if isinstance(exc, OtpError) and exc.code == "OTP_LOCKED":
        status = 429
    elif exc.code in ("ACCOUNT_NOT_FOUND",):
        status = 404
    elif exc.code in ("INVALID_CREDENTIALS",):
        status = 401
    elif exc.code in ("ACCOUNT_ALREADY_DELETED",):
        status = 409
    detail = {"code": exc.code, "message": exc.message}
    if isinstance(exc, OtpError) and exc.retry_after is not None:
        detail["retryAfterSeconds"] = exc.retry_after
    return HTTPException(status_code=status, detail=detail)


def _internal_purge_auth(
    x_hekma_cache_key: str | None = Header(None, alias="X-Hekma-Cache-Key"),
    apiKey: str | None = Query(None, alias="apiKey"),
    x_account_deletion_key: str | None = Header(
        None, alias="X-Hekma-Account-Deletion-Key"
    ),
):
    """Allow cache reprocess key or dedicated account-deletion worker key."""
    dedicated = (os.getenv("ACCOUNT_DELETION_PURGE_API_KEY") or "").strip()
    if dedicated and (x_account_deletion_key or "").strip() == dedicated:
        return {"auth": "account_deletion"}
    if is_valid_cache_reprocess_credential(x_hekma_cache_key, apiKey):
        return {"auth": "internal"}
    raise HTTPException(
        status_code=401,
        detail={
            "code": "UNAUTHORIZED",
            "message": (
                "Provide X-Hekma-Account-Deletion-Key or cache reprocess credentials "
                "to run scheduled PHI purge."
            ),
        },
    )


@router.get(
    "/deletion/retention-policy",
    response_model=RetentionPolicyResponse,
    summary="Document immediate purge vs PHI archive retention",
)
def get_retention_policy(
    service: AccountDeletionService = Depends(get_account_deletion_service),
):
    """Public retention documentation for Privacy Policy / Play Data Safety."""
    return RetentionPolicyResponse(**service.retention_policy())


@router.post(
    "/deletion/request-otp",
    response_model=DeletionOtpResponse,
    summary="Send OTP to confirm permanent account deletion",
)
def request_deletion_otp(
    body: RequestDeletionOtpInput,
    claims: Optional[dict] = Depends(optional_jwt),
    service: AccountDeletionService = Depends(get_account_deletion_service),
):
    """
    In-app: send Authorization JWT (email/password ignored).
    External web page: omit JWT and pass email + password.
    """
    try:
        result = service.request_otp(
            jwt_claims=claims,
            email=body.email,
            password=body.password,
        )
        return DeletionOtpResponse(
            message=result["message"],
            challengeId=result["challengeId"],
            maskedEmail=result["maskedEmail"],
            expiresInSeconds=result["expiresInSeconds"],
            devOtp=result.get("devOtp"),
        )
    except AccountDeletionError as exc:
        raise _map_error(exc) from exc


@router.post(
    "/deletion/confirm",
    response_model=DeletionConfirmResponse,
    summary="Confirm OTP; revoke access and archive PHI",
)
def confirm_account_deletion(
    body: ConfirmDeletionInput,
    claims: Optional[dict] = Depends(optional_jwt),
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(http_bearer)
    ] = None,
    authorization: Annotated[
        Optional[str],
        Header(alias="Authorization", include_in_schema=False),
    ] = None,
    service: AccountDeletionService = Depends(get_account_deletion_service),
):
    """Steps 1–5 immediate. PHI hard purge happens later via scheduled job."""
    try:
        raw_jwt = _extract_raw_token(authorization, credentials)
        result = service.confirm_deletion(
            challenge_id=body.challengeId,
            otp=body.otp,
            confirmation=body.confirmation,
            reason=body.reason,
            raw_jwt=raw_jwt,
            jwt_claims=claims,
        )
        return DeletionConfirmResponse(**result)
    except AccountDeletionError as exc:
        raise _map_error(exc) from exc


@router.post(
    "/deletion/purge-due",
    response_model=PhiPurgeResponse,
    summary="Run step-6 PHI hard purge for retention-elapsed archives",
)
def purge_due_phi(
    limit: int = Query(100, ge=1, le=1000),
    _auth=Depends(_internal_purge_auth),
    service: AccountDeletionService = Depends(get_account_deletion_service),
):
    """Worker/cron endpoint: hard-delete PHI past purge_eligible_at."""
    result = service.run_scheduled_phi_purge(limit=limit)
    return PhiPurgeResponse(**result)
