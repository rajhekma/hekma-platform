"""Shared-secret auth for service-to-service calls (lambda → gpt-api)."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException


def expected_internal_api_key() -> str:
    """Return configured internal key; empty when unset (endpoint disabled)."""
    return os.getenv("TRIALGPT_EHR_INGEST_API_KEY", "").strip()


def internal_service_auth(
    x_hekma_internal_key: str | None = Header(default=None, alias="X-Hekma-Internal-Key"),
) -> dict:
    """Validate X-Hekma-Internal-Key for internal ingest endpoints."""
    expected = expected_internal_api_key()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="TRIALGPT_EHR_INGEST_API_KEY is not configured on this service",
        )
    provided = (x_hekma_internal_key or "").strip()
    if provided != expected:
        raise HTTPException(status_code=403, detail="Invalid internal API key")
    return {"auth": "internal"}
