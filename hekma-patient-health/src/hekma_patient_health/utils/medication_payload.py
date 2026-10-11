from typing import Any, Dict, Optional

from .medication_constants import MedicationFrequency, normalize_frequency
from .medication_form_inference import infer_medication_type


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def apply_as_needed_schedule(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    When the app marks a medicine as PRN / as-needed, drop fixed-frequency rules.

    The UI may still send ``onceDaily`` from the frequency picker while the
    as-needed toggle is on; treat that as PRN with no reminder slots.
    """
    result = dict(data)
    prn_flag = (
        _truthy(result.get("asNeeded"))
        or _truthy(result.get("isAsNeeded"))
        or _truthy(result.get("prn"))
        or _truthy(result.get("isPrn"))
    )
    freq = normalize_frequency(result.get("frequency"))
    if prn_flag or freq == MedicationFrequency.AS_NEEDED.value:
        result["frequency"] = MedicationFrequency.AS_NEEDED.value
        result["isReminderEnabled"] = False
        result["reminders"] = []
        result["reminderLabels"] = []
    return result


def build_display_dosage(how_much_to_take: str, strength: str, fallback: str = "") -> str:
    parts = [p.strip() for p in (how_much_to_take, strength) if p and p.strip()]
    if parts:
        return " ".join(parts)
    return fallback.strip() or "As directed"


def normalize_medication_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map API/UI fields to DB columns; keep legacy `dosage` in sync."""
    result = apply_as_needed_schedule(dict(data))

    how_much = (result.get("howMuchToTake") or result.get("how_much_to_take") or "").strip()
    strength = (result.get("strength") or "").strip()
    legacy_dosage = (result.get("dosage") or "").strip()

    if not how_much and not strength and legacy_dosage:
        how_much = legacy_dosage

    result["howMuchToTake"] = how_much
    result["strength"] = strength
    result["dosage"] = build_display_dosage(how_much, strength, legacy_dosage)

    med_type = result.get("medicationType", result.get("medication_type"))
    if med_type is not None and hasattr(med_type, "value"):
        med_type = med_type.value
    inferred = infer_medication_type(
        result.get("name"),
        dosage=result.get("dosage"),
        how_much_to_take=how_much,
        strength=strength,
        medication_type=med_type,
    )
    if inferred:
        result["medicationType"] = inferred
    elif med_type is not None:
        result["medicationType"] = med_type

    doctor_val = (
        result.get("doctorName")
        or result.get("doctor")
        or result.get("prescriberName")
        or result.get("doctor_name")
    )
    if isinstance(doctor_val, str):
        doctor_val = doctor_val.strip()
        if doctor_val.lower() == "uncertain" or not doctor_val:
            doctor_val = None
    else:
        doctor_val = None
    result["doctorName"] = doctor_val

    facility_val = (
        result.get("facilityName")
        or result.get("clinicName")
        or result.get("hospitalName")
        or result.get("clinic")
        or result.get("facility_name")
        or result.get("facility")
    )
    if isinstance(facility_val, str):
        facility_val = facility_val.strip()
        if facility_val.lower() == "uncertain" or not facility_val:
            facility_val = None
    else:
        facility_val = None
    result["facilityName"] = facility_val

    pdate_val = (
        result.get("prescriptionDate")
        or result.get("prescription_date")
        or result.get("date")
    )
    if isinstance(pdate_val, str):
        pdate_val = pdate_val.strip()
        if pdate_val.lower() == "uncertain" or not pdate_val:
            pdate_val = None
    else:
        pdate_val = None
    result["prescriptionDate"] = pdate_val

    return result
