"""Patient-local calendar day for medication schedules."""

from __future__ import annotations

from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from ..config.medication_dose_config import get_medication_dose_config
from ..repositories.patient_timezone_repo import get_patient_timezone_name


@lru_cache(maxsize=1)
def _config_default_timezone_name() -> str:
    """Return the fallback timezone from medication_dose_config.json."""
    return get_medication_dose_config().default_timezone


def resolve_patient_tz(timezone_name: Optional[str]) -> ZoneInfo:
    name = (timezone_name or _config_default_timezone_name()).strip()
    try:
        return ZoneInfo(name)
    except Exception as exc:
        raise ValueError(
            f"Invalid timezone '{timezone_name}'. Use an IANA name such as "
            "Asia/Kolkata, America/New_York, or UTC."
        ) from exc


def resolve_timezone_for_patient(
    patient_id: Optional[str],
    timezone_override: Optional[str] = None,
) -> ZoneInfo:
    """
    Resolve timezone for medication APIs.

    Priority: explicit query/body override → patient.timezone in DB →
    medication_dose_config.json defaultTimezone.
    """
    if timezone_override and str(timezone_override).strip():
        return resolve_patient_tz(timezone_override)

    if patient_id:
        stored = get_patient_timezone_name(patient_id)
        if stored:
            return resolve_patient_tz(stored)

    return resolve_patient_tz(_config_default_timezone_name())


def today_context(
    *,
    patient_id: Optional[str] = None,
    target_date: Optional[date] = None,
    timezone_name: Optional[str] = None,
) -> Tuple[date, int, ZoneInfo]:
    """
    Return (calendar_day, now_epoch_ms, tz) for today's medication schedule.
    Calendar day uses the patient timezone; now_ms is always real-time UTC.
    """
    tz = resolve_timezone_for_patient(patient_id, timezone_name)
    if target_date:
        day = target_date
    else:
        day = datetime.now(tz).date()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return day, now_ms, tz
