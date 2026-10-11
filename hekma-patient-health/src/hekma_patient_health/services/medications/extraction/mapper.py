from typing import Any, Dict, List

from ....utils.medication_constants import MedicationFrequency, normalize_frequency
from ....utils.medication_form_inference import infer_medication_type
from ....utils.medication_payload import build_display_dosage
from ....utils.prescription_dates import normalize_prescription_date
from ....utils.prescription_timing import (
    clear_unsupported_schedule,
    reconcile_frequency_with_slots,
    slots_from_timing,
    _clean_text,
    _is_form_only_dosage,
)


class PrescriptionDataMapper:
    """Maps AI extraction output to medication create payloads (SRP)."""

    @staticmethod
    def to_medication_payloads(extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
        payloads: List[Dict[str, Any]] = []
        doctor_name = (extracted.get("doctor_name") or "").strip()
        if doctor_name.lower() == "uncertain":
            doctor_name = ""
        clinic_name = (extracted.get("clinic") or extracted.get("facility") or "").strip()
        if clinic_name.lower() == "uncertain":
            clinic_name = ""
        # OCR often returns DD/MM/YYYY; normalize before DATE columns.
        prescription_date = normalize_prescription_date(extracted.get("date"))

        for medicine in extracted.get("medicines") or []:
            payload = PrescriptionDataMapper._normalize_medicine(medicine)
            if payload:
                if doctor_name:
                    payload["doctorName"] = doctor_name
                if clinic_name:
                    payload["facilityName"] = clinic_name
                if prescription_date:
                    payload["prescriptionDate"] = prescription_date
                payloads.append(payload)
        return payloads

    @staticmethod
    def enrich_prescription_payload(payload: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
        enriched = dict(payload)
        enriched["extractedData"] = extracted
        if not enriched.get("prescriberName") and extracted.get("doctor_name"):
            enriched["prescriberName"] = extracted["doctor_name"]
        if not enriched.get("prescriptionDate") and extracted.get("date"):
            enriched["prescriptionDate"] = normalize_prescription_date(extracted.get("date"))
        elif enriched.get("prescriptionDate"):
            enriched["prescriptionDate"] = normalize_prescription_date(
                enriched.get("prescriptionDate")
            )
        return enriched

    @staticmethod
    def normalize_medicine(medicine: Dict[str, Any]) -> Dict[str, Any]:
        return PrescriptionDataMapper._normalize_medicine(medicine)

    @staticmethod
    def _normalize_medicine(medicine: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(medicine.get("timing"), dict):
            medicine = clear_unsupported_schedule(medicine)
        name = (medicine.get("name") or "").strip()
        if not name or name.lower() == "uncertain":
            return {}

        strength = _clean_text(medicine.get("strength"))
        how_much = _clean_text(medicine.get("dosage"))
        if _is_form_only_dosage(how_much):
            how_much = ""

        # A prescription that states no frequency is a PRN medicine. Defaulting to
        # Once Daily invents a schedule the prescriber never wrote.
        stated_frequency = _clean_text(medicine.get("frequency"))
        frequency = normalize_frequency(stated_frequency) if stated_frequency else ""

        instructions = _clean_text(medicine.get("instructions"))

        slots = medicine.get("reminders") or slots_from_timing(medicine.get("timing"))
        if not frequency:
            # Only infer when unstated. A stated frequency passes through so the
            # validator, not this mapper, judges a mismatched slot count.
            frequency, slots = reconcile_frequency_with_slots(frequency, slots)

        # PRN has no schedule, so there is nothing to remind about.
        is_prn = frequency == MedicationFrequency.AS_NEEDED.value

        payload = {
            "name": name,
            "howMuchToTake": how_much,
            "strength": strength,
            "dosage": build_display_dosage(how_much, strength),
            "frequency": frequency,
            "instructions": instructions,
            "isReminderEnabled": not is_prn,
            "status": "Active",
            "notes": _clean_text(medicine.get("duration")),
        }
        if slots:
            payload["reminders"] = slots
        med_type = infer_medication_type(
            name,
            dosage=how_much or medicine.get("dosage"),
            how_much_to_take=how_much,
            strength=strength,
            medication_type=medicine.get("medicationType") or medicine.get("form"),
        )
        if med_type:
            payload["medicationType"] = med_type
        return payload
