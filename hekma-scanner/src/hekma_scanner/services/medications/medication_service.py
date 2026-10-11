from typing import Any, Dict, List, Optional

from ...repositories.medication_reminders_repo import (
    create_reminder,
    delete_reminders_by_medication,
    get_reminders_by_medication,
)
from ...repositories.medication_repo import (
    create_medication,
    delete_medication,
    get_medication,
    get_medications_by_patient,
    medication_belongs_to_patient,
    update_medication,
)
from ...utils.frequency_reminder_rules import validate_reminders_match_frequency
from ...utils.medication_constants import MedicationFrequency, normalize_frequency
from ...utils.medication_payload import apply_as_needed_schedule, normalize_medication_payload
from ...utils.prescription_dates import format_prescription_date
from ...utils.prescription_timing import frequency_for_slot_count
from ...utils.reminder_resolver import resolve_reminders
from .exceptions import InvalidReminderScheduleError, MedicationNotFoundError
from .fhir_dual_write import MedicationFhirDualWriter
from .schedule_service import MedicationScheduleService

# Every column update_medication writes, so a partial PUT can be topped up.
_UPDATE_FIELD_COLUMNS = {
    "name": "name",
    "dosage": "dosage",
    "howMuchToTake": "how_much_to_take",
    "strength": "strength",
    "medicationType": "medication_type",
    "frequency": "frequency",
    "startDate": "start_date",
    "endDate": "end_date",
    "instructions": "instructions",
    "isReminderEnabled": "is_reminder_enabled",
    "status": "status",
    "notes": "notes",
    "prescriptionId": "prescription_id",
    "doctorName": "doctor_name",
    "facilityName": "facility_name",
}


class MedicationService:
    """Orchestrates medication CRUD and reminder scheduling."""

    def __init__(
        self,
        schedule_service: Optional[MedicationScheduleService] = None,
        fhir_dual_writer: Optional[MedicationFhirDualWriter] = None,
    ):
        self._schedule = schedule_service or MedicationScheduleService()
        self._fhir = fhir_dual_writer or MedicationFhirDualWriter()

    def create_with_reminders(self, patient_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._prepare_payload(body)
        medication = create_medication(patient_id, payload)
        medication["reminders"] = self._replace_reminders(
            medication["id"], payload.get("reminders", [])
        )
        self._fhir.sync_medication(patient_id, medication, medication["reminders"])
        return medication

    def create_bulk(
        self,
        patient_id: str,
        medications: List[Dict[str, Any]],
        auto_schedule: bool = True,
    ) -> List[Dict[str, Any]]:
        payloads = []
        for item in medications:
            payload = dict(item)
            # Count-based meds track uses/day; do not invent slot reminders for them.
            if (
                auto_schedule
                and not payload.get("dailyTargetCount")
                and not payload.get("reminders")
                and not payload.get("reminderLabels")
            ):
                payload["reminders"] = self._schedule.build(payload.get("frequency", ""))
            payloads.append(payload)

        # Validate every medication before the first write. Validating inside the
        # write loop left the earlier ones saved when a later one was rejected,
        # so the caller saw an error and a half-applied change.
        for payload in payloads:
            self._prepare_payload(payload)

        return [self.create_with_reminders(patient_id, p) for p in payloads]

    def _prepare_payload(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and validate a medication; raises before anything is written."""
        payload = normalize_medication_payload(apply_as_needed_schedule(body))
        if normalize_frequency(payload.get("frequency")) == MedicationFrequency.AS_NEEDED.value:
            payload["reminders"] = []
        else:
            payload["reminders"] = self._resolve_reminder_payload(payload)
        payload["frequency"] = self._infer_frequency(
            payload.get("frequency"),
            payload["reminders"],
            payload.get("dailyTargetCount"),
        )
        self._assert_reminders_match_frequency(payload)
        return payload

    def schedule(self, medication_id: int, patient_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_access(medication_id, patient_id)
        medication = get_medication(medication_id)
        reminders_payload = self._schedule.build(
            medication["frequency"],
            explicit_reminders=body.get("reminders") or body.get("reminderLabels"),
            use_frequency_defaults=body.get("useFrequencyDefaults", True),
        )
        self._assert_reminders_match_frequency(
            {
                "frequency": medication.get("frequency"),
                "reminders": reminders_payload,
                "dailyTargetCount": medication.get("daily_target_count"),
            }
        )
        medication["reminders"] = self._replace_reminders(medication_id, reminders_payload)
        return medication

    def update_with_reminders(
        self, medication_id: int, patient_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update medication fields; replace reminders only when the client sent them."""
        self._ensure_access(medication_id, patient_id)
        existing = get_medication(medication_id)
        replace_reminders = "reminders" in body or "reminderLabels" in body
        frequency_changing = "frequency" in body
        payload = normalize_medication_payload(self._merge_with_existing(body, existing))
        if replace_reminders:
            payload["reminders"] = self._resolve_reminder_payload(payload)

        if replace_reminders or frequency_changing:
            # Only fall back to the stored frequency when none was sent. A blank
            # one is a deliberate "unstated", not a reason to reuse the old value.
            if frequency_changing:
                frequency = payload.get("frequency") or ""
            else:
                frequency = (existing or {}).get("frequency")
            if "dailyTargetCount" in body:
                daily_target = payload.get("dailyTargetCount")
            else:
                daily_target = (existing or {}).get("daily_target_count")
            reminders = (
                payload.get("reminders", [])
                if replace_reminders
                else get_reminders_by_medication(medication_id)
            )
            frequency = self._infer_frequency(frequency, reminders, daily_target)
            payload["frequency"] = frequency
            self._assert_reminders_match_frequency(
                {
                    "frequency": frequency,
                    "reminders": reminders,
                    "dailyTargetCount": daily_target,
                }
            )

        medication = update_medication(medication_id, payload)
        if replace_reminders:
            medication["reminders"] = self._replace_reminders(
                medication_id, payload.get("reminders", [])
            )
        else:
            medication["reminders"] = get_reminders_by_medication(medication_id)
        self._fhir.sync_medication(patient_id, medication, medication["reminders"])
        return medication

    def remove(self, medication_id: int, patient_id: str) -> Dict[str, bool]:
        self._ensure_access(medication_id, patient_id)
        self._fhir.retire_medication(patient_id, medication_id)
        delete_medication(medication_id)
        return {"success": True}

    def list_for_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        medications = get_medications_by_patient(patient_id)
        for med in medications:
            med["reminders"] = get_reminders_by_medication(med["id"])
        return medications

    def get_details(
        self, medication_id: int, patient_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        medication = get_medication(medication_id)
        if not medication:
            return None
        if patient_id and medication.get("patient_id") != patient_id:
            return None
        medication["reminders"] = get_reminders_by_medication(medication_id)
        return medication

    def _replace_reminders(self, medication_id: int, reminders: List[Dict]) -> List[Dict]:
        delete_reminders_by_medication(medication_id)
        resolved = resolve_reminders(reminders)
        return [create_reminder(medication_id, reminder) for reminder in resolved]

    @staticmethod
    def _infer_frequency(frequency: Any, reminders: Any, daily_target: Any) -> str:
        """
        Name an unstated frequency after the slots the caller chose.

        Two slots mean Twice Daily whether they came from a scan or the app.
        A stated frequency is returned untouched, and with no slots to count
        the frequency stays blank rather than being guessed at.
        """
        stated = str(frequency or "").strip()
        if stated or daily_target:
            return stated
        slots = list(reminders or [])
        if not slots:
            return ""
        return frequency_for_slot_count(len(slots)) or ""

    @staticmethod
    def _merge_with_existing(
        body: Dict[str, Any], existing: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Fill in fields the client left out of a PUT from the stored row.

        update_medication writes every column, so an omitted field would be
        blanked — or raise KeyError for the ones it reads directly.
        dailyTargetCount is left alone: the repo keys off its absence.
        """
        merged = dict(body)
        for field, column in _UPDATE_FIELD_COLUMNS.items():
            if field not in merged and column in (existing or {}):
                merged[field] = existing[column]

        if "prescriptionDate" not in merged:
            # Stored as a DATE, which the normalizer would drop; print it first.
            stored = (existing or {}).get("prescription_date")
            if stored:
                merged["prescriptionDate"] = format_prescription_date(stored)
        return merged

    @staticmethod
    def _resolve_reminder_payload(payload: Dict[str, Any]) -> List[Dict]:
        raw = payload.get("reminders") or payload.get("reminderLabels") or []
        if not raw:
            return []
        return resolve_reminders(raw)

    @staticmethod
    def _assert_reminders_match_frequency(payload: Dict[str, Any]) -> None:
        """Reject saves when reminder slot count does not match the frequency."""
        try:
            validate_reminders_match_frequency(
                payload.get("frequency"),
                payload.get("reminders") or [],
                daily_target_count=payload.get("dailyTargetCount"),
            )
        except ValueError as exc:
            raise InvalidReminderScheduleError(str(exc)) from exc

    @staticmethod
    def _ensure_access(medication_id: int, patient_id: str) -> None:
        if not medication_belongs_to_patient(medication_id, patient_id):
            raise MedicationNotFoundError("Medication not found for this patient")
