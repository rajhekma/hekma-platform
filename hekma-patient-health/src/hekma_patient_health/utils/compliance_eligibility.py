"""Determine which dose slots count toward compliance analytics."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo


def _epoch_ms(day: date, hour: int, minute: int, tz: ZoneInfo) -> int:
    dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
    return int(dt.timestamp() * 1000)


def _day_end_ms(day: date, tz: ZoneInfo) -> int:
    dt = datetime(day.year, day.month, day.day, 23, 59, 59, 999999, tzinfo=tz)
    return int(dt.timestamp() * 1000)


def _coerce_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    return date.fromisoformat(text[:10])


def _coerce_created_at_ms(value: Any, tz: ZoneInfo) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(tz).timestamp() * 1000)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.astimezone(tz).timestamp() * 1000)


def medication_effective_bounds(
    med: Dict[str, Any], tz: ZoneInfo
) -> Tuple[Optional[int], Optional[int]]:
    """
    Return (effective_start_ms, effective_end_ms) for slot-level bounds.

    Uses prescription start/end dates only. ``created_at`` is handled at the
    day level in ``compliance_day_bounds`` so same-day schedules match
    ``GET /patients/{id}/medications/today/metrics``.
    """
    start_day = _coerce_date(med.get("start_date"))
    effective_start_ms = _epoch_ms(start_day, 0, 0, tz) if start_day is not None else None

    end_day = _coerce_date(med.get("end_date"))
    effective_end_ms = _day_end_ms(end_day, tz) if end_day is not None else None

    return effective_start_ms, effective_end_ms


def compliance_first_day(med: Dict[str, Any], tz: ZoneInfo) -> Optional[date]:
    """
    First calendar day this medication can appear on the schedule.

    The later of ``start_date`` and the local ``created_at`` date — days before
    this are excluded from period analytics, but every slot on that first day
    counts (including slots before the creation timestamp), matching /today.
    """
    candidates: list[date] = []

    created_ms = _coerce_created_at_ms(med.get("created_at"), tz)
    if created_ms is not None:
        candidates.append(datetime.fromtimestamp(created_ms / 1000, tz=tz).date())

    start_day = _coerce_date(med.get("start_date"))
    if start_day is not None:
        candidates.append(start_day)

    return max(candidates) if candidates else None


def slot_counts_for_compliance(
    scheduled_ms: int,
    effective_start_ms: Optional[int],
    effective_end_ms: Optional[int],
) -> bool:
    """True when this scheduled slot should be included in due/missed/taken totals."""
    if effective_start_ms is not None and scheduled_ms < effective_start_ms:
        return False
    if effective_end_ms is not None and scheduled_ms > effective_end_ms:
        return False
    return True


def compliance_day_bounds(
    med: Dict[str, Any],
    range_start: date,
    range_end: date,
    tz: ZoneInfo,
) -> Tuple[date, date]:
    """Narrow the day loop to days when the medication could have due slots."""
    _, effective_end_ms = medication_effective_bounds(med, tz)

    day_start = range_start
    first_day = compliance_first_day(med, tz)
    if first_day is not None:
        day_start = max(day_start, first_day)

    day_end = range_end
    if effective_end_ms is not None:
        last_day = datetime.fromtimestamp(effective_end_ms / 1000, tz=tz).date()
        day_end = min(day_end, last_day)

    return day_start, day_end
