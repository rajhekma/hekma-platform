"""Patient-facing dose status rules for configurable local medication windows."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..config.medication_dose_config import get_medication_dose_config
from .reminder_resolver import dose_slot_bounds_ms

PATIENT_DOSE_STATUSES = frozenset({"taken", "skipped", "pending"})
_LOGGABLE_STATUSES = frozenset({"taken", "skipped"})
_MS_PER_HOUR = 60 * 60 * 1000


def dose_slot_end_ms(scheduled_time: int, tz: Any = None) -> int:
    """Return the exclusive configured display-slot end for a scheduled dose."""
    return dose_slot_bounds_ms(scheduled_time, tz)[1]


def dose_edit_deadline_ms(scheduled_time: int, tz: Any = None) -> int:
    """
    Exclusive deadline for marking or changing a dose (taken / skipped / pending).

    Defaults to scheduled_time + editWindowHours (24h) so an Afternoon dose can
    still be logged in the evening/night of the same cycle.
    """
    del tz  # window is relative to scheduled epoch, timezone-independent
    hours = int(get_medication_dose_config().edit_window_hours)
    return int(scheduled_time) + (hours * _MS_PER_HOUR)


# Backward-compatible name used by older call sites / docs.
def dose_log_deadline_ms(scheduled_time: int, tz: Any = None) -> int:
    """Alias for dose_edit_deadline_ms (24h edit window, not slot end)."""
    return dose_edit_deadline_ms(scheduled_time, tz)


def can_log_dose(scheduled_time: int, now_ms: int, tz: Any = None) -> bool:
    """True while a dose can still be marked taken/skipped within the edit window."""
    return int(scheduled_time) <= int(now_ms) < dose_edit_deadline_ms(scheduled_time, tz)


def can_change_dose_status(scheduled_time: int, now_ms: int, tz: Any = None) -> bool:
    """True while taken/skipped/pending may still be changed within the edit window."""
    return can_log_dose(scheduled_time, now_ms, tz)


def is_overdue_pending(
    status: str, scheduled_time: int, now_ms: int, tz: Any = None
) -> bool:
    """True for pending doses past schedule but before the display slot ends."""
    return (
        status == "pending"
        and int(scheduled_time) < int(now_ms) < dose_slot_end_ms(scheduled_time, tz)
    )


def compliance_status_for_slot(
    entry: Optional[Dict[str, Any]],
    scheduled_time: int,
    cutoff_ms: int,
    tz: Any = None,
) -> str:
    """
    Return missed when an unlogged dose reaches the display-slot end.

    Logging may still be allowed for editWindowHours after scheduledTime; missed
    is a display/count signal after the slot closes, not a write lock.
    Stored `pending` is treated as unlogged so auto-missed still applies.
    """
    if entry:
        status = str(entry.get("status", "")).strip().lower()
        if status in ("taken", "skipped", "missed"):
            return status

    if cutoff_ms < scheduled_time:
        return "pending"
    if cutoff_ms < dose_slot_end_ms(scheduled_time, tz):
        return "pending"
    return "missed"


def validate_patient_dose_entry(
    entry: Dict[str, Any], now_ms: int, tz: Any = None
) -> Dict[str, Any]:
    """
    Normalize and validate a dose progress / dose-log entry.
    Raises ValueError with a clear message when invalid.
    """
    status = str(entry.get("status", "")).strip().lower()
    if status == "missed":
        raise ValueError(
            "Dose status 'missed' is calculated automatically. Mark as 'taken', "
            "'skipped', or 'pending' within the editable window."
        )
    if status not in PATIENT_DOSE_STATUSES:
        raise ValueError(
            f"Invalid dose status '{status}'. Allowed: taken, skipped, pending."
        )

    scheduled_time = int(entry["scheduledTime"])
    edit_deadline = dose_edit_deadline_ms(scheduled_time, tz)

    if status in _LOGGABLE_STATUSES:
        if now_ms < scheduled_time:
            raise ValueError(
                "Cannot log dose before its scheduled time."
            )
        if now_ms >= edit_deadline:
            raise ValueError(
                "Dose can only be logged or changed within "
                f"{get_medication_dose_config().edit_window_hours} hours of its "
                "scheduled time."
            )
        if status == "taken" and not entry.get("takenTime"):
            entry = {**entry, "takenTime": now_ms}
    elif status == "pending":
        if now_ms >= edit_deadline:
            raise ValueError(
                "Cannot set dose status to 'pending' after the editable window ends."
            )
        # Undo taken/skipped → not taken: clear takenTime so counts drop.
        entry = {**entry, "takenTime": None}

    entry = {**entry, "status": status}
    return entry
