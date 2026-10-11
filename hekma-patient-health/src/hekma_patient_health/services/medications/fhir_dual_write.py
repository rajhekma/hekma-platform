"""Best-effort dual-write of adherence medications into fastenhealth_medicationrequest."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ...repositories.medication_repo import set_medication_hekma_id
from ...utils.prescription_dates import format_prescription_date
from ..clinical_fhir.models import ClinicalSource, FhirWriteResult
from ..clinical_fhir.projector import ClinicalFhirProjector, dual_write_enabled

logger = logging.getLogger(__name__)


def medication_row_to_fhir_record(
    medication: Dict[str, Any],
    reminders: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Shape a medications-table row for MedicationRequestMapper.to_fhir."""
    record: Dict[str, Any] = {
        "id": medication.get("id"),
        "name": medication.get("name"),
        "dosage": medication.get("dosage"),
        "howMuchToTake": medication.get("how_much_to_take"),
        "strength": medication.get("strength"),
        "medicationType": medication.get("medication_type"),
        "frequency": medication.get("frequency"),
        "startDate": format_prescription_date(medication.get("start_date")),
        "endDate": format_prescription_date(medication.get("end_date")),
        "prescriptionDate": format_prescription_date(medication.get("prescription_date")),
        "instructions": medication.get("instructions"),
        "status": medication.get("status"),
        "notes": medication.get("notes"),
        "doctorName": medication.get("doctor_name"),
        "facilityName": medication.get("facility_name"),
        "prescriptionId": medication.get("prescription_id"),
        "dailyTargetCount": medication.get("daily_target_count"),
        "isReminderEnabled": medication.get("is_reminder_enabled"),
    }
    if reminders:
        record["reminders"] = reminders
    return record


def infer_medication_clinical_source(medication: Dict[str, Any]) -> ClinicalSource:
    """Scan-saved rows link to prescriptions; manual app entry does not."""
    if medication.get("prescription_id"):
        return ClinicalSource.SCAN
    raw = str(medication.get("source") or "").strip().lower()
    if raw == ClinicalSource.SCAN.value:
        return ClinicalSource.SCAN
    return ClinicalSource.MANUAL


class MedicationFhirDualWriter:
    """Project Postgres medications rows to FHIR without blocking adherence writes."""

    def __init__(self, projector: Optional[ClinicalFhirProjector] = None):
        self._projector = projector or ClinicalFhirProjector()

    def sync_medication(
        self,
        patient_id: str,
        medication: Dict[str, Any],
        reminders: Optional[List[Dict[str, Any]]] = None,
        *,
        source: Optional[ClinicalSource] = None,
    ) -> FhirWriteResult:
        if not dual_write_enabled():
            return FhirWriteResult(ok=True, extras={"skipped": "disabled"})
        med_id = medication.get("id")
        if med_id is None:
            return FhirWriteResult(ok=False, error="medication id required")
        src = source or infer_medication_clinical_source(medication)
        record = medication_row_to_fhir_record(medication, reminders)
        result = self._projector.project_mysql_row(
            str(patient_id),
            "medications",
            record,
            src,
            document_id=str(medication.get("prescription_id") or "") or None,
        )
        if result.ok and result.hekma_id:
            try:
                set_medication_hekma_id(int(med_id), str(result.hekma_id))
                medication["hekma_id"] = str(result.hekma_id)
            except Exception:
                logger.warning(
                    "Failed to persist hekma_id on medication id=%s",
                    med_id,
                    exc_info=True,
                )
        elif not result.ok:
            logger.warning(
                "Medication FHIR dual-write failed patient_id=%s medication_id=%s error=%s",
                patient_id,
                med_id,
                result.error,
            )
        return result

    def retire_medication(self, patient_id: str, medication_id: int) -> FhirWriteResult:
        if not dual_write_enabled():
            return FhirWriteResult(ok=True, extras={"skipped": "disabled"})
        result = self._projector.retire_mysql_row(
            str(patient_id), "medications", int(medication_id)
        )
        if not result.ok:
            logger.warning(
                "Medication FHIR retire failed patient_id=%s medication_id=%s error=%s",
                patient_id,
                medication_id,
                result.error,
            )
        return result
