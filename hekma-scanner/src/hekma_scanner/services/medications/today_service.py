from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from ...config.medication_dose_config import get_medication_dose_config
from ...repositories.medication_history_repo import get_dose_history_for_day
from ...repositories.medication_repo import get_medications_by_patient
from ...repositories.medication_reminders_repo import get_reminders_by_medication
from ...utils.dose_status import (
    can_change_dose_status,
    can_log_dose,
    compliance_status_for_slot,
    dose_edit_deadline_ms,
    is_overdue_pending,
)
from ...utils.compliance_history import find_history_entry_for_today_slot, index_history
from ...utils.patient_timezone import today_context
from ...utils.reminder_resolver import (
    dose_slot_name,
    resolve_reminder,
    scheduled_time_ms,
)

_TAKEN_STATUSES = frozenset({"taken", "Taken"})
_MISSED_STATUSES = frozenset({"missed", "Missed"})
_PENDING_STATUSES = frozenset({"pending", "Pending"})
_SKIPPED_STATUSES = frozenset({"skipped", "Skipped"})


class TodayMedicationService:
    """Builds today's dose schedule and adherence metrics."""

    def get_schedule(
        self,
        patient_id: str,
        target_date: Optional[date] = None,
        include_metrics: bool = False,
        timezone_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        day, now_ms, tz = today_context(
            patient_id=patient_id,
            target_date=target_date,
            timezone_name=timezone_name,
        )

        active_meds = [
            m for m in get_medications_by_patient(patient_id) if m.get("status") == "Active"
        ]
        medication_ids = [m["id"] for m in active_meds]
        day_history = (
            get_dose_history_for_day(medication_ids, day, tz) if medication_ids else []
        )

        history_exact, history_by_med = index_history(day_history)
        doses = self._build_doses(active_meds, day, history_exact, history_by_med, now_ms, tz)
        doses.sort(key=lambda d: d["scheduledTime"])

        result: Dict[str, Any] = {
            "date": day.isoformat(),
            "timezone": str(tz),
            "doses": doses,
            "medications": active_meds,
        }
        if include_metrics:
            result["metrics"] = self._compute_metrics(doses, now_ms, tz)
        return result

    def _build_doses(
        self,
        active_meds: List[Dict],
        day: date,
        history_exact: Dict,
        history_by_med: Dict[int, List[Dict]],
        now_ms: int,
        tz,
    ) -> List[Dict[str, Any]]:
        doses: List[Dict[str, Any]] = []
        for med in active_meds:
            # Count-based meds use daily-count APIs, not slot schedules.
            if med.get("daily_target_count"):
                continue

            reminders = get_reminders_by_medication(med["id"])
            used_history_keys: set = set()

            if not reminders:
                doses.append(
                    self._dose_slot(
                        med,
                        None,
                        resolve_reminder({"label": "Morning"}),
                        day,
                        history_exact,
                        history_by_med,
                        used_history_keys,
                        now_ms,
                        tz,
                    )
                )
                continue

            for reminder in reminders:
                resolved = resolve_reminder(reminder)
                doses.append(
                    self._dose_slot(
                        med,
                        reminder["id"],
                        resolved,
                        day,
                        history_exact,
                        history_by_med,
                        used_history_keys,
                        now_ms,
                        tz,
                    )
                )
        return doses

    def _dose_slot(
        self,
        med: Dict,
        reminder_id: Optional[int],
        resolved: Dict[str, Any],
        day: date,
        history_exact: Dict,
        history_by_med: Dict[int, List[Dict]],
        used_history_keys: set,
        now_ms: int,
        tz,
    ) -> Dict[str, Any]:
        scheduled_time = scheduled_time_ms(day, resolved, tz)
        history_entry = (
            find_history_entry_for_today_slot(
                med["id"],
                scheduled_time,
                reminder_id,
                history_exact,
                history_by_med,
                used_history_keys,
            )
            or {}
        )
        if history_entry:
            used_history_keys.add(
                (history_entry["medication_id"], int(history_entry["scheduled_time"]))
            )
        status = self._resolve_status(history_entry, scheduled_time, now_ms, tz)
        slot = dose_slot_name(resolved.get("label"), scheduled_time, tz)
        return {
            "medicationId": med["id"],
            "medicationName": med["name"],
            "dosage": med["dosage"],
            "howMuchToTake": med.get("how_much_to_take", ""),
            "strength": med.get("strength", ""),
            "medicationType": med.get("medication_type"),
            "frequency": med["frequency"],
            "reminderId": reminder_id,
            "scheduledTime": scheduled_time,
            "label": resolved.get("label"),
            "slot": slot,
            "scheduledHour": resolved["hour"],
            "scheduledMinute": resolved["minute"],
            "status": status,
            "takenTime": history_entry.get("taken_time"),
            "loggableUntil": dose_edit_deadline_ms(scheduled_time, tz),
            # Missed after slot end can still be marked taken within 24h.
            "canLogTaken": status in ("pending", "missed")
            and can_log_dose(scheduled_time, now_ms, tz),
            "canChangeStatus": status in ("taken", "skipped", "pending", "missed")
            and can_change_dose_status(scheduled_time, now_ms, tz),
            "canUndoTaken": status in ("taken", "skipped")
            and can_change_dose_status(scheduled_time, now_ms, tz),
            "isOverdue": is_overdue_pending(status, scheduled_time, now_ms, tz),
        }

    @staticmethod
    def _resolve_status(
        history_entry: Dict, scheduled_time: int, now_ms: int, tz
    ) -> str:
        """Return stored status or calculate missed after the display slot ends."""
        return compliance_status_for_slot(
            history_entry or None, scheduled_time, now_ms, tz
        )

    @staticmethod
    def _compute_metrics(doses: List[Dict], now_ms: int, tz=None) -> Dict[str, Any]:
        """Summarize total and per-slot dose states for the current local day."""
        total = len(doses)
        taken = sum(1 for d in doses if d["status"] in _TAKEN_STATUSES)
        missed = sum(1 for d in doses if d["status"] in _MISSED_STATUSES)
        pending = sum(1 for d in doses if d["status"] in _PENDING_STATUSES)
        skipped = sum(1 for d in doses if d["status"] in _SKIPPED_STATUSES)
        due_doses = [d for d in doses if d["scheduledTime"] <= now_ms]
        due_so_far = len(due_doses)
        upcoming = total - due_so_far
        overdue_pending = sum(
            1
            for d in doses
            if is_overdue_pending(d["status"], d["scheduledTime"], now_ms, tz)
        )
        taken_due_so_far = sum(
            1 for d in due_doses if d["status"] in _TAKEN_STATUSES
        )
        adherence_rate = (
            round((taken_due_so_far / due_so_far) * 100, 1) if due_so_far else 100.0
        )
        by_slot: Dict[str, Dict[str, int]] = {}
        for configured_slot in get_medication_dose_config().slots:
            slot = configured_slot.name
            slot_doses = [d for d in doses if d.get("slot") == slot]
            by_slot[slot] = {
                "totalCount": len(slot_doses),
                "takenCount": sum(
                    1 for d in slot_doses if d["status"] in _TAKEN_STATUSES
                ),
                "missedCount": sum(
                    1 for d in slot_doses if d["status"] in _MISSED_STATUSES
                ),
                "activeCount": sum(
                    1 for d in slot_doses if d["status"] in _PENDING_STATUSES
                ),
                "skippedCount": sum(
                    1 for d in slot_doses if d["status"] in _SKIPPED_STATUSES
                ),
            }

        return {
            "totalDosesToday": total,
            "takenCount": taken,
            "missedCount": missed,
            "pendingCount": pending,
            "activeDoseCount": pending,
            "skippedCount": skipped,
            "dueSoFar": due_so_far,
            "upcomingCount": upcoming,
            "overduePendingCount": overdue_pending,
            "adherenceRate": adherence_rate,
            "doseCountsBySlot": by_slot,
        }
