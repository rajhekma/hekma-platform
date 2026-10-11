"""Auth helpers for JWT-protected FastAPI routes and Swagger Authorize."""

from __future__ import annotations

import os
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import hmac

from ..redis_service import get_redis_client
from .jwt_util import JwtUtil

jwt_util = JwtUtil()

# No hardcoded fallback. Internal keys must come from the environment.

# Swagger "Authorize" button uses HTTP Bearer; clients may still send Token <jwt>.
http_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description=(
        "Paste the JWT only (no prefix). Swagger sends `Authorization: Bearer <jwt>`. "
        "Mobile/Postman may also send `Token <jwt>`."
    ),
)


def _extract_token(authorization: Optional[str]) -> str:
    """Parse Bearer/Token/raw JWT from an Authorization header value."""
    if not authorization or not str(authorization).strip():
        raise HTTPException(status_code=401, detail="Authorization header missing")

    value = str(authorization).strip()
    prefix = os.getenv("JWT_HEADER_PREFIX", "Bearer").strip() or "Bearer"

    if value.startswith(prefix + " "):
        return value[len(prefix) + 1 :].strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    if value.lower().startswith("token "):
        return value[6:].strip()
    # Swagger / manual paste of bare JWT
    if value.count(".") == 2 and " " not in value:
        return value

    raise HTTPException(
        status_code=401,
        detail="Invalid Authorization header format",
    )


def authenticate_authorization_header(authorization: Optional[str]) -> dict:
    """Validate Authorization header value and return JWT claims."""
    token = _extract_token(authorization)

    try:
        redis_client = get_redis_client()
        if redis_client.exists(f"blacklist:token:{token}"):
            raise HTTPException(
                status_code=401,
                detail="JWT Token has been logged out/invalidated",
            )
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Error checking token blacklist in Redis: {exc}")

    return jwt_util.validate(token)


def jwt_filter(
    request: Request,
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(http_bearer)
    ] = None,
    authorization: Annotated[
        Optional[str],
        Header(alias="Authorization", include_in_schema=False),
    ] = None,
):
    """
    Require a valid JWT for protected routes.

    Supports:
    - Swagger Authorize → Authorization: Bearer <jwt>
    - App/Postman → Authorization: Token <jwt>
    - Bare JWT in the Authorization header
    """
    if request.method == "OPTIONS":
        return None

    header_value = authorization
    if not header_value and credentials and credentials.credentials:
        scheme = (credentials.scheme or "Bearer").strip() or "Bearer"
        header_value = f"{scheme} {credentials.credentials}"

    return authenticate_authorization_header(header_value)


def expected_cache_reprocess_key() -> str:
    return (os.getenv("CACHE_REPROCESS_API_KEY") or "").strip()


def is_valid_cache_reprocess_credential(header_key: str | None, query_key: str | None) -> bool:
    provided = (header_key or query_key or "").strip()
    expected = expected_cache_reprocess_key()
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided, expected)


def cache_reprocess_auth(
    request: Request,
    authorization: str | None = Header(None),
    x_hekma_cache_key: str | None = Header(None, alias="X-Hekma-Cache-Key"),
    apiKey: str | None = Query(None, alias="apiKey"),
):
    """
    Server-to-server calls from hekma_api use X-Hekma-Cache-Key and/or apiKey query param
    (must match CACHE_REPROCESS_API_KEY on this service).
    Manual / UI calls may use a normal JWT Authorization header when no server key is configured.
    """
    if is_valid_cache_reprocess_credential(x_hekma_cache_key, apiKey):
        return {"auth": "internal"}

    expected = expected_cache_reprocess_key()
    if expected:
        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid or missing cache reprocess credentials. "
                "Provide X-Hekma-Cache-Key header or apiKey query param matching CACHE_REPROCESS_API_KEY."
            ),
        )

    return authenticate_authorization_header(authorization)
