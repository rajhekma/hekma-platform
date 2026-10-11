"""Shared helpers for mapping OpenAI HTTP failures to user-facing domain errors."""

from __future__ import annotations

import json
from typing import Any, Optional, Tuple

import requests


def openai_error_details(response: Optional[requests.Response]) -> Tuple[Optional[str], Optional[str], str]:
    """
    Parse OpenAI error payload.

    Returns: (error_code, error_type, message_fragment)
    """
    if response is None:
        return None, None, ""

    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):
        text = (response.text or "")[:300]
        return None, None, text

    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict):
        return None, None, str(body)[:300]

    code = err.get("code")
    err_type = err.get("type")
    message = (err.get("message") or "").strip()
    return (
        str(code) if code is not None else None,
        str(err_type) if err_type is not None else None,
        message,
    )


def is_openai_auth_failure(status: Optional[int], response: Optional[requests.Response] = None) -> bool:
    """True when OpenAI rejects the API key (missing, invalid, revoked, or expired)."""
    if status in (401, 403):
        return True

    code, err_type, message = openai_error_details(response)
    blob = " ".join(filter(None, [code, err_type, message])).lower()
    auth_markers = (
        "invalid_api_key",
        "authentication",
        "unauthorized",
        "expired",
        "revoked",
        "incorrect api key",
        "invalid api key",
        "api key",
        "permission",
    )
    return any(marker in blob for marker in auth_markers) and status in (400, 401, 403)


def scan_auth_user_message(feature: str = "Document scanning") -> str:
    return (
        f"{feature} is temporarily unavailable due to a service authentication issue. "
        "Please try again later or contact support if the problem continues."
    )


def classify_openai_http_error(
    exc: requests.HTTPError,
    *,
    feature: str = "Document scanning",
) -> dict[str, Any]:
    """
    Classify an OpenAI HTTPError into a stable shape for domain exception mapping.

    Returns dict with keys: kind ('auth'|'rate_limit'|'service'), status, message, reason_code
    """
    response = exc.response
    status = response.status_code if response is not None else None
    provider_code, provider_type, provider_message = openai_error_details(response)

    if status == 429:
        return {
            "kind": "rate_limit",
            "status": status,
            "message": f"{feature} is temporarily busy. Please try again in a few minutes.",
            "reason_code": "rate_limited",
        }

    if is_openai_auth_failure(status, response):
        return {
            "kind": "auth",
            "status": status,
            "message": scan_auth_user_message(feature),
            "reason_code": "auth_failed",
        }

    return {
        "kind": "service",
        "status": status,
        "message": f"{feature} failed right now. Please try again.",
        "reason_code": provider_code or provider_type or "service_error",
    }
