from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...repositories.medication_history_repo import (
    get_dose_history,
    insert_history_entry,
    upsert_history_entry,
)
from ...repositories.medication_reminders_repo import get_reminders_by_medication
from ...repositories.medication_repo import medication_belongs_to_patient
from ...utils.dose_status import validate_patient_dose_entry
from ...utils.patient_timezone import resolve_timezone_for_patient
from ...utils.reminder_resolver import scheduled_time_ms_from_epoch
from .exceptions import InvalidDoseProgressError, MedicationNotFoundError


class DoseHistoryService:
    """Manages medication dose log sync and progress updates."""

    @staticmethod
    def _now_ms() -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    @staticmethod
    def _ensure_medication_owned(entry: Dict[str, Any], patient_id: Optional[str]) -> None:
        """Reject writes for medications that are missing or not owned by patient_id."""
        if not patient_id:
            raise InvalidDoseProgressError(
                "patient_id is required to update dose history"
            )
        medication_id = entry.get("medicationId")
        try:
            medication_id = int(medication_id)
        except (TypeError, ValueError) as exc:
            raise InvalidDoseProgressError("medicationId is required") from exc
        if not medication_belongs_to_patient(medication_id, patient_id):
            raise MedicationNotFoundError("Medication not found for this patient")

    @staticmethod
    def _align_scheduled_time(entry: Dict[str, Any], tz) -> Dict[str, Any]:
        """Ensure scheduledTime matches canonical label times (Morning, Night, etc.)."""
        reminder_id = entry.get("reminderId")
        medication_id = entry.get("medicationId")
        scheduled = int(entry["scheduledTime"])
        if not reminder_id or not medication_id:
            return entry

        reminders = get_reminders_by_medication(medication_id)
        reminder = next((r for r in reminders if r["id"] == reminder_id), None)
        if not reminder:
            return entry

        expected = scheduled_time_ms_from_epoch(scheduled, reminder, tz)
        if scheduled != expected:
            entry = {**entry, "scheduledTime": expected}
        return entry

    def _prepare_entry(
        self,
        entry: Dict[str, Any],
        now_ms: int,
        tz,
        patient_id: Optional[str],
    ) -> Dict[str, Any]:
        """Validate ownership and dose rules before persisting a history row."""
        self._ensure_medication_owned(entry, patient_id)
        try:
            aligned = self._align_scheduled_time(entry, tz)
            return validate_patient_dose_entry(aligned, now_ms, tz)
        except ValueError as exc:
            raise InvalidDoseProgressError(str(exc)) from exc

    def sync_entries(
        self,
        entries: List[Dict[str, Any]],
        patient_id: Optional[str] = None,
        timezone_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        accepted = rejected = 0
        errors: List[str] = []
        now_ms = self._now_ms()
        tz = resolve_timezone_for_patient(patient_id, timezone_name)

        for entry in entries:
            try:
                insert_history_entry(
                    self._prepare_entry(entry, now_ms, tz, patient_id)
                )
                accepted += 1
            except MedicationNotFoundError as exc:
                rejected += 1
                errors.append(str(exc))
            except (InvalidDoseProgressError, Exception) as exc:
                rejected += 1
                errors.append(str(exc))

        return {"accepted": accepted, "rejected": rejected, "errors": errors}

    def update_progress(
        self,
        entries: List[Dict[str, Any]],
        patient_id: Optional[str] = None,
        timezone_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        updated: List[Dict] = []
        errors: List[str] = []
        now_ms = self._now_ms()
        tz = resolve_timezone_for_patient(patient_id, timezone_name)

        for entry in entries:
            try:
                updated.append(
                    upsert_history_entry(
                        self._prepare_entry(entry, now_ms, tz, patient_id)
                    )
                )
            except MedicationNotFoundError as exc:
                errors.append(str(exc))
            except InvalidDoseProgressError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(str(exc))

        return {"updated": len(updated), "entries": updated, "errors": errors}

    def get_history(
        self,
        medication_ids: List[int],
        from_time: Optional[int] = None,
        to_time: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return get_dose_history(medication_ids, from_time, to_time)
