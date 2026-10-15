"""
Build trial_gpt_ehr ingest progress payloads for UI polling.

Stages: awaiting_ehr → queued → building_profile → ready (or retrying after failed).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from services.trial_gpt_ehr_ingest_service import (
    STALE_INGESTING_ROW_SECONDS,
    is_stale_ingesting_row,
)

# Typical LLM ingest duration; used for ETA in progress responses.
ESTIMATED_INGEST_SECONDS = 120
DEFAULT_RETRY_AFTER_SECONDS = 15
AUTO_RETRY_COOLDOWN_SECONDS = 90


def _as_utc_naive(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    return None


def _elapsed_seconds(updated_at: Any) -> Optional[float]:
    normalized = _as_utc_naive(updated_at)
    if normalized is None:
        return None
    return max(0.0, (datetime.utcnow() - normalized).total_seconds())


def normalize_stored_error(error: Optional[str]) -> Optional[str]:
    """Map legacy terse DB errors (e.g. IndexError arg '3') to readable text."""
    if not error:
        return None
    text = str(error).strip()
    if not text:
        return None
    if text.isdigit():
        return (
            "IndexError: Hekma summary module path missing in Docker "
            "(deploy gpt-api with bundled Fasten summary)"
        )
    return text[:500]


def _progress_percent(
    *,
    stage: str,
    elapsed: Optional[float],
    in_flight: bool = False,
    retry_cooldown_seconds_remaining: Optional[int] = None,
) -> int:
    """Rough 0–100 progress for UI bars."""
    if stage == "ready":
        return 100
    if stage == "awaiting_ehr":
        return 5
    if stage == "queued":
        return 20
    if stage == "retrying":
        if in_flight:
            return 45
        if retry_cooldown_seconds_remaining is not None and retry_cooldown_seconds_remaining > 0:
            done = AUTO_RETRY_COOLDOWN_SECONDS - retry_cooldown_seconds_remaining
            pct = 30 + int(min(done / AUTO_RETRY_COOLDOWN_SECONDS, 1.0) * 14)
            return min(max(pct, 30), 44)
        if elapsed is not None:
            pct = 30 + int(min(elapsed / AUTO_RETRY_COOLDOWN_SECONDS, 1.0) * 14)
            return min(max(pct, 30), 44)
        return 30
    if stage == "building_profile":
        if elapsed is None:
            return 50
        pct = 40 + int(min(elapsed / ESTIMATED_INGEST_SECONDS, 1.0) * 55)
        return min(pct, 95)
    return 15


def _stage_message(
    stage: str,
    *,
    error_display: Optional[str] = None,
    retry_cooldown_seconds_remaining: Optional[int] = None,
    in_flight: bool = False,
    retry_scheduled: bool = False,
) -> str:
    if stage == "retrying":
        if in_flight or retry_scheduled:
            return "Retrying health profile build now."
        if retry_cooldown_seconds_remaining is not None and retry_cooldown_seconds_remaining > 0:
            return (
                f"Previous build failed. Next automatic retry in "
                f"{retry_cooldown_seconds_remaining} seconds."
            )
        if error_display:
            return f"Previous build failed: {error_display}. Retrying shortly."
        return "Retrying health profile build after a temporary error."

    messages = {
        "awaiting_ehr": "Waiting for your medical records from Fasten Health.",
        "queued": "Your EHR data is ready. Starting health profile build.",
        "building_profile": "Building your health profile from EHR data. This usually takes 1–2 minutes.",
        "ready": "Your health profile is ready.",
    }
    return messages.get(stage, messages["building_profile"])


def build_ingest_progress(
    *,
    mysql_patient_id: int,
    llm: bool,
    in_flight: bool,
    has_ready: bool,
    summary_row: Optional[Dict[str, Any]],
    fasten_present: bool,
    fasten_rows: int,
    retry_cooldown_seconds_remaining: Optional[int] = None,
    retry_scheduled: bool = False,
) -> Dict[str, Any]:
    """Compose progress fields from current Fasten + trial_gpt_ehr state."""
    if has_ready:
        return {
            "ehr_status": "ready",
            "stage": "ready",
            "progress_percent": 100,
            "message": _stage_message("ready"),
            "summary_status": "ready",
            "in_flight": False,
            "retry_scheduled": False,
            "fasten_ready": fasten_present,
            "fasten_clinical_rows": fasten_rows,
            "elapsed_seconds": None,
            "estimated_seconds_remaining": 0,
            "retry_after_seconds": None,
            "retry_cooldown_seconds_remaining": None,
            "error": None,
            "error_display": None,
        }

    summary_status = (summary_row or {}).get("summary_status")
    updated_at = (summary_row or {}).get("updated_at")
    elapsed = _elapsed_seconds(updated_at)
    raw_error = None
    if summary_row and summary_status == "failed":
        structured = summary_row.get("structured_json") or {}
        if isinstance(structured, dict):
            raw_error = structured.get("error")
    error_display = normalize_stored_error(raw_error)

    if not fasten_present:
        stage = "awaiting_ehr"
        ehr_status = "preparing"
    elif summary_status == "failed":
        stage = "retrying"
        ehr_status = "preparing"
    elif summary_status == "ingesting" or in_flight:
        stage = "building_profile"
        ehr_status = "preparing"
    elif is_stale_ingesting_row(mysql_patient_id, llm=llm):
        stage = "retrying"
        ehr_status = "preparing"
    elif not summary_row:
        stage = "queued"
        ehr_status = "preparing"
    else:
        stage = "building_profile"
        ehr_status = "preparing"

    eta = None
    if stage == "building_profile" and elapsed is not None:
        eta = max(0, int(ESTIMATED_INGEST_SECONDS - elapsed))

    retry_after = DEFAULT_RETRY_AFTER_SECONDS if ehr_status == "preparing" else None
    if stage == "retrying" and retry_cooldown_seconds_remaining:
        retry_after = min(retry_after or DEFAULT_RETRY_AFTER_SECONDS, retry_cooldown_seconds_remaining)

    return {
        "ehr_status": ehr_status,
        "stage": stage,
        "progress_percent": _progress_percent(
            stage=stage,
            elapsed=elapsed,
            in_flight=in_flight,
            retry_cooldown_seconds_remaining=retry_cooldown_seconds_remaining,
        ),
        "message": _stage_message(
            stage,
            error_display=error_display,
            retry_cooldown_seconds_remaining=retry_cooldown_seconds_remaining,
            in_flight=in_flight,
            retry_scheduled=retry_scheduled,
        ),
        "summary_status": summary_status,
        "updated_at": updated_at,
        "in_flight": in_flight,
        "retry_scheduled": retry_scheduled,
        "fasten_ready": fasten_present,
        "fasten_clinical_rows": fasten_rows,
        "elapsed_seconds": round(elapsed, 1) if elapsed is not None else None,
        "estimated_seconds_remaining": eta,
        "retry_after_seconds": retry_after,
        "retry_cooldown_seconds_remaining": retry_cooldown_seconds_remaining,
        "error": raw_error,
        "error_display": error_display,
        "stale_threshold_seconds": STALE_INGESTING_ROW_SECONDS,
    }
