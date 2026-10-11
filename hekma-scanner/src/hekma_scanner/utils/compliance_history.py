"""History indexing and lookup helpers for the compliance dashboard."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Covers TZ offset mismatches between dashboard slot times and stored scheduled_time.
HISTORY_MATCH_TOLERANCE_MS = 18 * 60 * 60 * 1000
# When reminder_id differs (re-schedule / TZ), only match within this window (e.g. IST vs UTC ~5.5h).
REMINDER_MISMATCH_MAX_DELTA_MS = 2 * 60 * 60 * 1000


def index_history(rows: List[Dict[str, Any]]) -> Tuple[Dict[Tuple[int, int], Dict], Dict[int, List[Dict]]]:
    exact: Dict[Tuple[int, int], Dict] = {}
    by_med: Dict[int, List[Dict]] = {}
    for row in rows:
        med_id = row["medication_id"]
        scheduled = row["scheduled_time"]
        exact[(med_id, scheduled)] = row
        by_med.setdefault(med_id, []).append(row)
    for med_id in by_med:
        by_med[med_id].sort(key=lambda r: r["scheduled_time"])
    return exact, by_med


def find_history_entry(
    medication_id: int,
    scheduled: int,
    reminder_id: Optional[int],
    exact: Dict[Tuple[int, int], Dict],
    by_med: Dict[int, List[Dict]],
) -> Optional[Dict[str, Any]]:
    entry = exact.get((medication_id, scheduled))
    if entry:
        return entry

    best_row: Optional[Dict[str, Any]] = None
    best_delta: Optional[int] = None

    for row in by_med.get(medication_id, []):
        row_reminder = row.get("reminder_id")
        if reminder_id is not None and row_reminder is not None and row_reminder != reminder_id:
            continue
        delta = abs(row["scheduled_time"] - scheduled)
        if delta > HISTORY_MATCH_TOLERANCE_MS:
            continue
        if best_delta is None or delta < best_delta:
            best_row = row
            best_delta = delta

    return best_row


def find_history_entry_for_today_slot(
    medication_id: int,
    scheduled: int,
    reminder_id: Optional[int],
    exact: Dict[Tuple[int, int], Dict],
    by_med: Dict[int, List[Dict]],
    used_entry_keys: Optional[set] = None,
) -> Optional[Dict[str, Any]]:
    """
    Match dose history to a today-schedule slot without double-counting one log
    across Morning/Afternoon/Evening/Night. Prefers reminder id match, then
    closest scheduled_time within tolerance (covers TZ + re-scheduled reminders).
    """
    used = used_entry_keys or set()

    def _row_key(row: Dict[str, Any]) -> Tuple[int, int]:
        return (row["medication_id"], int(row["scheduled_time"]))

    entry = exact.get((medication_id, scheduled))
    if entry and _row_key(entry) not in used:
        return entry

    best_row: Optional[Dict[str, Any]] = None
    best_score: Optional[int] = None
    reminder_mismatch_penalty = 1_000_000_000

    for row in by_med.get(medication_id, []):
        if _row_key(row) in used:
            continue

        delta = abs(row["scheduled_time"] - scheduled)
        if delta > HISTORY_MATCH_TOLERANCE_MS:
            continue

        row_reminder = row.get("reminder_id")
        reminder_mismatch = (
            reminder_id is not None
            and row_reminder is not None
            and row_reminder != reminder_id
        )
        if reminder_mismatch and delta > REMINDER_MISMATCH_MAX_DELTA_MS:
            continue

        reminder_penalty = reminder_mismatch_penalty if reminder_mismatch else 0
        score = reminder_penalty + delta
        if best_score is None or score < best_score:
            best_row = row
            best_score = score

    return best_row


def taken_timestamp(entry: Optional[Dict[str, Any]], scheduled_fallback: int) -> Optional[int]:
    if not entry:
        return None
    taken_time = entry.get("taken_time")
    if taken_time:
        return int(taken_time)
    scheduled_time = entry.get("scheduled_time")
    if scheduled_time:
        return int(scheduled_time)
    return scheduled_fallback


def last_taken_in_period(
    by_med: Dict[int, List[Dict]],
    medication_id: int,
    period_start_ms: int,
    period_end_ms: int,
    reminder_labels: Dict[int, Optional[str]],
) -> Tuple[Optional[int], Optional[str]]:
    best_time: Optional[int] = None
    best_label: Optional[str] = None

    for row in by_med.get(medication_id, []):
        scheduled = row["scheduled_time"]
        if scheduled < period_start_ms or scheduled > period_end_ms:
            continue
        if str(row.get("status", "")).lower() != "taken":
            continue

        taken_at = taken_timestamp(row, scheduled)
        if taken_at is None:
            continue
        if best_time is None or taken_at > best_time:
            best_time = taken_at
            reminder_id = row.get("reminder_id")
            best_label = reminder_labels.get(reminder_id) if reminder_id else None

    return best_time, best_label
