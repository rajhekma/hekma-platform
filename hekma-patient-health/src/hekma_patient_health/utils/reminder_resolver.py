from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Union
from zoneinfo import ZoneInfo

from ..config.medication_dose_config import get_medication_dose_config


_DOSE_CONFIG = get_medication_dose_config()

# Backward-compatible maps, generated from the config file at process startup.
# LABEL_TIMES maps each accepted label to its slot start; CANONICAL_LABELS keeps
# the configured display label (e.g. "Early Morning"), not the slot bucket name.
LABEL_TIMES: Dict[str, tuple] = {
    label.lower(): divmod(slot.start_minute, 60)
    for slot in _DOSE_CONFIG.slots
    for label in slot.labels
}
CANONICAL_LABELS: Dict[str, str] = {
    label.lower(): label
    for slot in _DOSE_CONFIG.slots
    for label in slot.labels
}


def normalize_label(label: Union[str, Any]) -> str:
    if label is None:
        return ""
    if hasattr(label, "value"):
        label = label.value
    return str(label).strip().lower()


def canonical_label(label: Union[str, Any]) -> Optional[str]:
    key = normalize_label(label)
    return CANONICAL_LABELS.get(key) if key else None


def coerce_reminder_entries(raw: Any) -> List[Dict[str, Any]]:
    """Accept UI formats: ['Morning', 'Night'] or [{label:'Morning'}, ...]."""
    if raw is None:
        return []

    if isinstance(raw, list):
        entries: List[Dict[str, Any]] = []
        for item in raw:
            if isinstance(item, str):
                entries.append({"label": item})
            elif isinstance(item, dict):
                entries.append(dict(item))
        return entries

    return []


def resolve_reminder(reminder: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve hour/minute/label for a reminder slot.
    Configured labels always use their configured slot start so scheduledTime stays
    aligned even if stored DB hour/minute values are stale.
    """
    label = reminder.get("label")
    key = normalize_label(label)

    if key and key in LABEL_TIMES:
        hour, minute = LABEL_TIMES[key]
        return {
            "hour": hour,
            "minute": minute,
            "label": CANONICAL_LABELS[key],
        }

    hour = reminder.get("hour")
    minute = reminder.get("minute")
    if hour is not None and minute is not None:
        return {
            "hour": int(hour),
            "minute": int(minute),
            "label": canonical_label(label) or (str(label).strip() if label else None),
        }

    if not key:
        raise ValueError("Each reminder needs a label (e.g. Morning) or hour and minute")

    allowed = ", ".join(CANONICAL_LABELS.values())
    raise ValueError(f"Unknown reminder label '{label}'. Allowed: {allowed}")


def scheduled_time_ms(
    day: date, reminder: Dict[str, Any], tz: Optional[ZoneInfo] = None
) -> int:
    """Epoch ms for a dose on `day` at this reminder's resolved time in `tz` (default UTC)."""
    resolved = resolve_reminder(reminder)
    tzinfo = tz or timezone.utc
    dt = datetime(
        day.year,
        day.month,
        day.day,
        resolved["hour"],
        resolved["minute"],
        tzinfo=tzinfo,
    )
    return int(dt.timestamp() * 1000)


def scheduled_time_ms_from_epoch(
    scheduled_time_ms_value: int,
    reminder: Dict[str, Any],
    tz: Optional[ZoneInfo] = None,
) -> int:
    """Recompute canonical scheduledTime for the calendar day in the given timezone."""
    tzinfo = tz or timezone.utc
    day = datetime.fromtimestamp(scheduled_time_ms_value / 1000, tz=tzinfo).date()
    return scheduled_time_ms(day, reminder, tzinfo)


def dose_slot_name(
    label: Union[str, Any],
    scheduled_time: Optional[int] = None,
    tz: Optional[ZoneInfo] = None,
) -> str:
    """Return the configured slot name for a label or scheduled local time."""
    configured_slot = _DOSE_CONFIG.slot_for_label(label)
    if configured_slot:
        return configured_slot.name
    if scheduled_time is None:
        return _DOSE_CONFIG.slots[0].name

    tzinfo = tz or ZoneInfo(_DOSE_CONFIG.default_timezone)
    local_dt = datetime.fromtimestamp(scheduled_time / 1000, tz=tzinfo)
    minute = local_dt.hour * 60 + local_dt.minute
    return _DOSE_CONFIG.slot_for_minute(minute).name


def _datetime_for_minute(day: date, minute: int, tz: ZoneInfo) -> datetime:
    """Build a timezone-aware datetime for minutes after local midnight."""
    if minute == 24 * 60:
        return datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    hour, minute_part = divmod(minute, 60)
    return datetime.combine(day, time(hour, minute_part), tzinfo=tz)


def dose_slot_bounds_ms(
    scheduled_time: int, tz: Optional[ZoneInfo] = None
) -> tuple[int, int]:
    """Return configured local-clock slot bounds for a scheduled dose."""
    tzinfo = tz or ZoneInfo(_DOSE_CONFIG.default_timezone)
    local_dt = datetime.fromtimestamp(scheduled_time / 1000, tz=tzinfo)
    local_minute = local_dt.hour * 60 + local_dt.minute
    slot = _DOSE_CONFIG.slot_for_minute(local_minute)
    is_inside_slot = slot.start_minute <= local_minute < slot.end_minute
    start_minute = slot.start_minute if is_inside_slot else local_minute
    end_minute = _DOSE_CONFIG.next_boundary_minute(local_minute)
    start_dt = _datetime_for_minute(local_dt.date(), start_minute, tzinfo)
    end_dt = _datetime_for_minute(local_dt.date(), end_minute, tzinfo)
    return int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000)


def resolve_reminders(raw: Any) -> List[Dict[str, Any]]:
    return [resolve_reminder(entry) for entry in coerce_reminder_entries(raw)]
