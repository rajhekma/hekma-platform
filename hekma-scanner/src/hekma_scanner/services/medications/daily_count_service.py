"""Daily quantity tracking for count-based medications."""

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from ...repositories.medication_daily_count_repo import (
    MedicationDailyCountRepository,
)
from ...utils.patient_timezone import resolve_timezone_for_patient
from .exceptions import (
    DailyCountLimitError,
    DailyCountNotConfiguredError,
    InvalidDoseProgressError,
    MedicationNotFoundError,
)


class MedicationDailyCountService:
    """Manage daily targets and atomic use counts in the resolved patient timezone."""

    def __init__(
        self, repository: Optional[MedicationDailyCountRepository] = None
    ) -> None:
        self._repo = repository or MedicationDailyCountRepository()

    def set_target(
        self, patient_id: str, medication_id: int, target_count: int
    ) -> Dict[str, Any]:
        """Configure how many uses the patient should complete each day."""
        if not 1 <= target_count <= 1000:
            raise InvalidDoseProgressError(
                "dailyTargetCount must be between 1 and 1000"
            )
        medication = self._repo.set_target(patient_id, medication_id, target_count)
        if not medication:
            raise MedicationNotFoundError("Medication not found for this patient")
        return dict(medication)

    def get_summary(
        self,
        patient_id: str,
        medication_id: int,
        target_date: Optional[date] = None,
        timezone_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return target, taken, remaining, active, and missed counts for one day."""
        tz = resolve_timezone_for_patient(patient_id, timezone_name)
        today = datetime.now(tz).date()
        day = target_date or today
        if day > today:
            raise InvalidDoseProgressError("Daily medication count date cannot be in the future")

        medication = self._load_medication(patient_id, medication_id)
        row = self._repo.get_daily_count(medication_id, day)
        return self._build_summary(medication, row, day, today, str(tz))

    def record_taken(
        self,
        patient_id: str,
        medication_id: int,
        count: int = 1,
        taken_time: Optional[int] = None,
        timezone_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record one or more uses and reduce the day's remaining active count."""
        self._validate_change_count(count)
        tz = resolve_timezone_for_patient(patient_id, timezone_name)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        event_ms = int(taken_time or now_ms)
        if event_ms > now_ms + 5 * 60 * 1000:
            raise InvalidDoseProgressError("takenTime cannot be in the future")

        day = datetime.fromtimestamp(event_ms / 1000, tz=tz).date()
        medication = self._load_medication(patient_id, medication_id)
        target_count = int(medication["daily_target_count"])
        row = self._repo.increment(
            medication_id, day, str(tz), target_count, count
        )
        if not row:
            raise DailyCountLimitError(
                "Taken count would exceed the medication's daily target"
            )
        return self._build_summary(
            medication, row, day, datetime.now(tz).date(), str(tz)
        )

    def undo_taken(
        self,
        patient_id: str,
        medication_id: int,
        count: int = 1,
        target_date: Optional[date] = None,
        timezone_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Undo one or more uses without allowing the taken count below zero."""
        self._validate_change_count(count)
        tz = resolve_timezone_for_patient(patient_id, timezone_name)
        today = datetime.now(tz).date()
        day = target_date or today
        if day > today:
            raise InvalidDoseProgressError("Daily medication count date cannot be in the future")

        medication = self._load_medication(patient_id, medication_id)
        row = self._repo.decrement(medication_id, day, count)
        if not row:
            raise DailyCountLimitError(
                "Cannot undo more uses than have been recorded for this day"
            )
        return self._build_summary(medication, row, day, today, str(tz))

    def _load_medication(self, patient_id: str, medication_id: int) -> Dict[str, Any]:
        """Load an owned active medication and require count tracking to be configured."""
        medication = self._repo.get_target(patient_id, medication_id)
        if not medication:
            raise MedicationNotFoundError("Medication not found for this patient")
        if str(medication.get("status") or "").strip().lower() != "active":
            raise InvalidDoseProgressError(
                "Daily count tracking is only available for Active medications"
            )
        if not medication.get("daily_target_count"):
            raise DailyCountNotConfiguredError(
                "Set dailyTargetCount before recording count-based medication uses"
            )
        return dict(medication)

    @staticmethod
    def _validate_change_count(count: int) -> None:
        """Reject non-positive or unreasonably large counter changes."""
        if not 1 <= count <= 1000:
            raise InvalidDoseProgressError("count must be between 1 and 1000")

    @staticmethod
    def _build_summary(
        medication: Dict[str, Any],
        row: Optional[Dict],
        day: date,
        today: date,
        timezone_name: str,
    ) -> Dict[str, Any]:
        """Calculate daily state without persisting synthetic missed events."""
        target = int(
            row["target_count"] if row else medication["daily_target_count"]
        )
        taken = int(row["taken_count"] if row else 0)
        remaining = max(target - taken, 0)
        is_closed = day < today
        missed = remaining if is_closed else 0
        active = 0 if is_closed else remaining
        if remaining == 0:
            status = "completed"
        elif is_closed:
            status = "missed"
        else:
            status = "active"

        return {
            "medicationId": medication["id"],
            "medicationName": medication.get("name"),
            "date": day.isoformat(),
            "timezone": row.get("timezone", timezone_name) if row else timezone_name,
            "targetCount": target,
            "takenCount": taken,
            "remainingCount": remaining,
            "activeCount": active,
            "missedCount": missed,
            "status": status,
        }
