from typing import Any, Dict, List, Optional, Tuple

from ..clinical_fhir.hekma_clinical_store import HekmaClinicalStore
from ..clinical_fhir.models import ClinicalSource
from ..clinical_scans.exceptions import RecordAlreadyExistsError
from ..clinical_scans.modules import ClinicalModule
from ...utils.medication_form_inference import enrich_medicine_form_fields
from ...utils.prescription_dates import format_prescription_date
from ...utils.vital_signs_normalization import normalize_vital_sign_record
from ...utils.prescription_timing import (
    TIMING_PROMPT,
    TIMING_SCHEMA,
    clear_unsupported_schedule,
    reconcile_frequency_with_slots,
    slots_from_timing,
)


def _anti_hallucination_rules() -> str:
    """Block inferred rows, borrowed sections, and invented codes/values."""
    return (
        " Extract only text that is printed. Do not invent codes, values, substances, "
        "vaccines, procedures, or diagnoses. Do not infer a diagnosis from BMI, blood "
        "pressure, or lab numbers unless that diagnosis is written on the page. "
        "Do not copy chief complaints (C/o) into diagnoses unless they appear under Diagnosis. "
        "Do not copy prescription (Rx) drug names into procedures, labs, or immunizations. "
        "If allergies are printed as NKDA, Nil, None, or no known allergies, return an empty array. "
        "If this module's section is absent, return an empty array — do not borrow rows from other sections. "
        "Procedure/investigation findings (ECG interpretation, imaging impression, endoscopy notes) are not diagnoses "
        "unless they appear under a Diagnosis or Impression heading."
    )


def _mixed_document_rules(invalid_code: str) -> str:
    """Tell Vision this module can appear as one section of a multi-section OPD sheet."""
    return (
        " The document may be a mixed OPD / consultation / prescription sheet that also "
        "contains other labeled sections (immunization, vital signs, allergies, diagnosis, "
        "lab results, procedures, advice). Extract this module's section whenever it is "
        "present as a table, labeled list, or labeled values. If this section is absent, "
        f"return an empty array. Set error to {invalid_code} only for non-medical images "
        "(scenery, IDs, blank pages) — never because other clinical sections are also present."
        + _anti_hallucination_rules()
    )


_PLACEHOLDER_ALLERGENS = {
    "nkda",
    "nka",
    "nil",
    "none",
    "na",
    "nil known",
    "no known drug allergies",
    "no known allergies",
    "no known allergy",
    "no known drug allergy",
}


def _is_placeholder_allergen(substance: str) -> bool:
    """True for NKDA / Nil / None rows that must not persist as an allergy."""
    key = " ".join((substance or "").lower().split())
    if key in _PLACEHOLDER_ALLERGENS:
        return True
    return key.startswith("no known")


def _normalize_allergy(item: Dict[str, Any], fallback_date: Optional[str] = None) -> Dict[str, Any]:
    """Map a Vision allergy object onto the CTMS allergy payload; skip unnamed/NKDA rows."""
    substance = (item.get("substance") or "").strip()
    if not substance or substance.lower() == "uncertain" or _is_placeholder_allergen(substance):
        return {}

    criticality = (item.get("criticality") or "low").strip().lower()
    if criticality not in ("high", "low", "unable-to-assess"):
        criticality = "low"

    category = (item.get("category") or "medication").strip().lower()
    if category not in ("food", "medication", "environment", "biologic"):
        category = "medication"

    status = (item.get("status") or "active").strip().lower()
    if status not in ("active", "inactive", "resolved"):
        status = "active"

    reaction = (item.get("reaction") or "").strip()
    if reaction.lower() == "uncertain":
        reaction = ""

    last_occ = (item.get("lastOccurrence") or item.get("last_occurrence") or "").strip()
    onset = (
        item.get("onset")
        or item.get("onsetDate")
        or item.get("startDate")
        or last_occ
        or fallback_date
        or ""
    ).strip()
    if onset.lower() == "uncertain":
        onset = ""

    notes = (item.get("notes") or "").strip()
    if notes.lower() == "uncertain":
        notes = ""

    payload: Dict[str, Any] = {
        "substance": substance,
        "criticality": criticality,
        "category": category,
        "status": status,
        "reaction": reaction,
        "onsetDate": onset,
        "notes": notes,
    }
    if last_occ:
        payload["lastOccurrence"] = last_occ
    return payload


def _meta_schema(items_key: str, item_props: Dict[str, Any], item_required: List[str]) -> Dict[str, Any]:
    return {
        "name": f"{items_key}_extraction",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "error": {"type": ["string", "null"]},
                "doctor_name": {"type": "string"},
                "clinic": {"type": "string"},
                "patient_name": {"type": "string"},
                "date": {"type": "string"},
                items_key: {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": item_props,
                        "required": item_required,
                    },
                },
                "notes": {"type": "string"},
                "overall_confidence": {"type": "number"},
            },
            "required": [
                "error", "doctor_name", "clinic", "patient_name", "date",
                items_key, "notes", "overall_confidence",
            ],
        },
        "strict": True,
    }


def _enrich(payload: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(payload)
    enriched["extractedData"] = extracted
    if not enriched.get("providerName") and extracted.get("doctor_name"):
        enriched["providerName"] = extracted["doctor_name"]
    if not enriched.get("documentDate") and extracted.get("date"):
        enriched["documentDate"] = extracted["date"]
    return enriched


def _pg() -> HekmaClinicalStore:
    return HekmaClinicalStore()


def _persist_scan(module: str, patient_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = dict(payload)
    body.setdefault("source", "ocr_scan")
    try:
        return _pg().create(patient_id, module, body, ClinicalSource.SCAN)
    except RecordAlreadyExistsError:
        raise


def _match_scan(module: str, patient_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _pg().find_duplicate(patient_id, module, payload)


def _upsert_scan(module: str, patient_id: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    body = dict(payload)
    body.setdefault("source", "ocr_scan")
    existing = _pg().find_duplicate(patient_id, module, body)
    if existing:
        updated = _pg().update(
            patient_id, module, int(existing["id"]), body, ClinicalSource.SCAN
        )
        return updated, "updated"
    return _pg().create(patient_id, module, body, ClinicalSource.SCAN), "created"


class _BaseStrategy:
    module: ClinicalModule

    def enrich_scan_payload(self, payload: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
        return _enrich(payload, extracted)


class AllergyStrategy(_BaseStrategy):
    module = ClinicalModule.ALLERGIES

    def extraction_profile(self) -> Dict[str, Any]:
        return {
            "system_prompt": (
                "You extract allergy and intolerance records from clinical medical documents, allergy charts, and prescription forms."
                + _mixed_document_rules("not_an_allergy_document")
            ),
            "user_prompt": (
                "Extract each allergy from Allergen/Reaction tables, NKDA notes, and listed drug, food, "
                "or environmental allergies: substance, criticality (high/low/unable-to-assess), "
                "category (food/medication/environment/biologic), severity (mild/moderate/severe), verificationStatus (confirmed/unconfirmed), "
                "reaction, onset (YYYY-MM-DD), lastOccurrence (YYYY-MM-DD), notes, confidence."
            ),
            "json_schema": _meta_schema(
                "allergies",
                {
                    "substance":          {"type": "string"},
                    "criticality":        {"type": "string"},
                    "category":           {"type": "string"},
                    "severity":           {"type": "string"},
                    "verificationStatus": {"type": "string"},
                    "reaction":           {"type": "string"},
                    "onset":              {"type": "string"},
                    "lastOccurrence":     {"type": "string"},
                    "notes":              {"type": "string"},
                    "confidence":         {"type": "number"},
                },
                ["substance", "criticality", "category", "severity", "verificationStatus", "reaction", "onset", "lastOccurrence", "notes", "confidence"],
            ),
            "invalid_error_code": "not_an_allergy_document",
            "invalid_message": "The file does not appear to be a valid allergy document",
        }

    def map_records(self, extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
        payloads = []
        doc_date = extracted.get("date")
        if isinstance(doc_date, str):
            doc_date = doc_date.strip() or None
        else:
            doc_date = None
        for item in extracted.get("allergies") or []:
            payload = _normalize_allergy(item, fallback_date=doc_date)
            if payload:
                payloads.append(payload)
        return payloads

    def persist_record(self, patient_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _persist_scan("allergies", patient_id, payload)

    def matching_record(self, patient_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return _match_scan("allergies", patient_id, payload)

    def upsert_record(self, patient_id: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        return _upsert_scan("allergies", patient_id, payload)


class LabReportsStrategy(_BaseStrategy):
    module = ClinicalModule.LAB_REPORTS

    def extraction_profile(self) -> Dict[str, Any]:
        return {
            "system_prompt": (
                "You extract laboratory test results from lab reports, printouts, and clinical documents."
                + _mixed_document_rules("not_a_lab_report")
            ),
            "user_prompt": (
                "Extract each lab test: testName, testCode (LOINC), category, value, unit, referenceRange, "
                "interpretation (HIGH/LOW/NORMAL/CRITICAL), specimen, performer, resultDate (YYYY-MM-DD), notes, confidence."
            ),
            "json_schema": _meta_schema(
                "lab_results",
                {
                    "testName":       {"type": "string"},
                    "testCode":       {"type": "string"},
                    "category":       {"type": "string"},
                    "value":          {"type": "string"},
                    "unit":           {"type": "string"},
                    "referenceRange": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "specimen":       {"type": "string"},
                    "performer":      {"type": "string"},
                    "resultDate":     {"type": "string"},
                    "notes":          {"type": "string"},
                    "confidence":     {"type": "number"},
                },
                ["testName", "testCode", "category", "value", "unit", "referenceRange", "interpretation", "specimen", "performer", "resultDate", "notes", "confidence"],
            ),
            "invalid_error_code": "not_a_lab_report",
            "invalid_message": "The file does not appear to be a valid lab report",
        }

    def map_records(self, extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
        records = []
        for item in extracted.get("lab_results") or []:
            name = (item.get("testName") or "").strip()
            if not name or name.lower() == "uncertain":
                continue
            records.append(
                {
                    "testName":       name,
                    "testCode":       (item.get("testCode") or "").strip(),
                    "category":       (item.get("category") or "").strip(),
                    "testValue":      (item.get("value") or item.get("testValue") or "").strip(),
                    "unit":           (item.get("unit") or "").strip(),
                    "referenceRange": (item.get("referenceRange") or "").strip(),
                    "interpretation": (item.get("interpretation") or "").strip(),
                    "specimen":       (item.get("specimen") or "").strip(),
                    "performer":      (item.get("performer") or "").strip(),
                    "resultDate":     (item.get("resultDate") or extracted.get("date") or "").strip(),
                    "notes":          (item.get("notes") or "").strip(),
                }
            )
        return records

    def matching_record(self, patient_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return _match_scan("lab_reports", patient_id, payload)

    def persist_record(self, patient_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _persist_scan("lab_reports", patient_id, payload)

    def upsert_record(self, patient_id: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        return _upsert_scan("lab_reports", patient_id, payload)


class VitalSignsStrategy(_BaseStrategy):
    module = ClinicalModule.VITAL_SIGNS

    def extraction_profile(self) -> Dict[str, Any]:
        return {
            "system_prompt": (
                "You extract vital signs from clinical notes, vitals sheets, and medical documents."
                + _mixed_document_rules("not_a_vitals_document")
            ),
            "user_prompt": (
                "Extract vitals from dedicated tables OR labeled lists "
                "(Blood Pressure, Pulse/Heart Rate, Temperature, Respiratory Rate, SpO2, Height, Weight, BMI). "
                "For each: type, value (refValue1), value2 (refValue2 for BP diastolic), unit/metric, "
                "interpretation, bodySite, patientPosition, dateOfObservation (YYYY-MM-DD), notes, confidence. "
                "Split BP 128/82 into value=128 and value2=82."
            ),
            "json_schema": _meta_schema(
                "vitals",
                {
                    "type":              {"type": "string"},
                    "value":             {"type": "string"},
                    "value2":            {"type": "string"},
                    "unit":              {"type": "string"},
                    "interpretation":    {"type": "string"},
                    "bodySite":          {"type": "string"},
                    "patientPosition":   {"type": "string"},
                    "dateOfObservation": {"type": "string"},
                    "notes":             {"type": "string"},
                    "confidence":        {"type": "number"},
                },
                ["type", "value", "value2", "unit", "interpretation", "bodySite", "patientPosition", "dateOfObservation", "notes", "confidence"],
            ),
            "invalid_error_code": "not_a_vitals_document",
            "invalid_message": "The file does not appear to be a valid vitals document",
        }

    def map_records(self, extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
        records = []
        for item in extracted.get("vitals") or []:
            vital_type = (item.get("type") or "").strip()
            if not vital_type or vital_type.lower() == "uncertain":
                continue
            records.append(
                normalize_vital_sign_record(
                    {
                        "type":              vital_type,
                        "refValue1":         (item.get("value") or item.get("refValue1") or "").strip(),
                        "refValue2":         (item.get("value2") or item.get("refValue2") or "").strip() or None,
                        "metric":            (item.get("unit") or item.get("metric") or "").strip(),
                        "interpretation":    (item.get("interpretation") or "").strip(),
                        "bodySite":          (item.get("bodySite") or "").strip(),
                        "patientPosition":   (item.get("patientPosition") or "").strip(),
                        "dateOfObservation": (item.get("dateOfObservation") or extracted.get("date") or "").strip(),
                        "notes":             (item.get("notes") or "").strip(),
                    }
                )
            )
        return records

    def matching_record(self, patient_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return _match_scan("vital_signs", patient_id, payload)

    def persist_record(self, patient_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _persist_scan("vital_signs", patient_id, payload)

    def upsert_record(self, patient_id: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        return _upsert_scan("vital_signs", patient_id, payload)


class ImmunizationStrategy(_BaseStrategy):
    module = ClinicalModule.IMMUNIZATION

    def extraction_profile(self) -> Dict[str, Any]:
        return {
            "system_prompt": (
                "You extract immunization/vaccination records from vaccine cards and clinical documents."
                + _mixed_document_rules("not_an_immunization_document")
            ),
            "user_prompt": (
                "Extract vaccines: vaccineName, vaccineCode (CVX/NDC), vaccinationDate (YYYY-MM-DD), doseQuantity, lotNumber, manufacturer, expirationDate, site, route, performer, notes, confidence."
            ),
            "json_schema": _meta_schema(
                "immunizations",
                {
                    "vaccineName":     {"type": "string"},
                    "vaccineCode":     {"type": "string"},
                    "vaccinationDate": {"type": "string"},
                    "doseQuantity":    {"type": "string"},
                    "lotNumber":       {"type": "string"},
                    "manufacturer":    {"type": "string"},
                    "expirationDate":  {"type": "string"},
                    "site":            {"type": "string"},
                    "route":           {"type": "string"},
                    "performer":       {"type": "string"},
                    "notes":           {"type": "string"},
                    "confidence":      {"type": "number"},
                },
                ["vaccineName", "vaccineCode", "vaccinationDate", "doseQuantity", "lotNumber", "manufacturer", "expirationDate", "site", "route", "performer", "notes", "confidence"],
            ),
            "invalid_error_code": "not_an_immunization_document",
            "invalid_message": "The file does not appear to be a valid immunization document",
        }

    def map_records(self, extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
        records = []
        for item in extracted.get("immunizations") or []:
            name = (item.get("vaccineName") or "").strip()
            if not name or name.lower() == "uncertain":
                continue
            records.append(
                {
                    "vaccineName":     name,
                    "vaccineCode":     (item.get("vaccineCode") or "").strip(),
                    "vaccinationDate": (item.get("vaccinationDate") or extracted.get("date") or "").strip(),
                    "doseQuantity":    (item.get("doseQuantity") or "").strip(),
                    "lotNumber":       (item.get("lotNumber") or "").strip(),
                    "manufacturer":    (item.get("manufacturer") or "").strip(),
                    "expirationDate":  (item.get("expirationDate") or "").strip(),
                    "site":            (item.get("site") or "").strip(),
                    "route":           (item.get("route") or "").strip(),
                    "performer":       (item.get("performer") or "").strip(),
                    "notes":           (item.get("notes") or "").strip(),
                }
            )
        return records

    def matching_record(self, patient_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return _match_scan("immunization", patient_id, payload)

    def persist_record(self, patient_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _persist_scan("immunization", patient_id, payload)

    def upsert_record(self, patient_id: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        return _upsert_scan("immunization", patient_id, payload)


class ProceduresStrategy(_BaseStrategy):
    module = ClinicalModule.PROCEDURES

    def extraction_profile(self) -> Dict[str, Any]:
        return {
            "system_prompt": (
                "You extract medical procedures and diagnostic investigations from operative notes, "
                "procedure reports, and clinical documents."
                + _mixed_document_rules("not_a_procedure_document")
            ),
            "user_prompt": (
                "Extract procedures from a Procedures / Investigations table or list, including diagnostic "
                "work such as ECG, X-ray, ultrasound, CT/MRI, endoscopy, biopsy, and swabs — not only surgery. "
                "For each: procedureName, code (CPT/SNOMED), category, status, bodySite, performer, facility, "
                "startDate (YYYY-MM-DD), endDate (YYYY-MM-DD), reason, outcome, complication, followUp, notes, confidence. "
                "Put printed findings (e.g. Normal, Culture: Negative) in outcome or notes. "
                "Do not move blood/urine chemistry rows from a Lab Results table into procedures."
            ),
            "json_schema": _meta_schema(
                "procedures",
                {
                    "procedureName": {"type": "string"},
                    "code":          {"type": "string"},
                    "category":      {"type": "string"},
                    "status":        {"type": "string"},
                    "bodySite":      {"type": "string"},
                    "performer":     {"type": "string"},
                    "facility":      {"type": "string"},
                    "startDate":     {"type": "string"},
                    "endDate":       {"type": "string"},
                    "reason":        {"type": "string"},
                    "outcome":       {"type": "string"},
                    "complication":  {"type": "string"},
                    "followUp":      {"type": "string"},
                    "notes":         {"type": "string"},
                    "confidence":    {"type": "number"},
                },
                [
                    "procedureName", "code", "category", "status", "bodySite", "performer", "facility",
                    "startDate", "endDate", "reason", "outcome", "complication", "followUp", "notes", "confidence",
                ],
            ),
            "invalid_error_code": "not_a_procedure_document",
            "invalid_message": "The file does not appear to be a valid procedure document",
        }

    def map_records(self, extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
        records = []
        for item in extracted.get("procedures") or []:
            name = (item.get("procedureName") or "").strip()
            if not name or name.lower() == "uncertain":
                continue
            records.append(
                {
                    "procedureName": name,
                    "code":          (item.get("code") or "").strip(),
                    "category":      (item.get("category") or "").strip(),
                    "status":        (item.get("status") or "completed").strip(),
                    "bodySite":      (item.get("bodySite") or item.get("location") or "").strip(),
                    "performer":     (item.get("performer") or "").strip(),
                    "facility":      (item.get("facility") or "").strip(),
                    "startDate":     (item.get("startDate") or extracted.get("date") or "").strip(),
                    "endDate":       (item.get("endDate") or "").strip() or None,
                    "reason":        (item.get("reason") or "").strip(),
                    "outcome":       (item.get("outcome") or "").strip(),
                    "complication":  (item.get("complication") or "").strip(),
                    "followUp":      (item.get("followUp") or "").strip(),
                    "notes":         (item.get("notes") or "").strip(),
                }
            )
        return records

    def matching_record(self, patient_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return _match_scan("procedures", patient_id, payload)

    def persist_record(self, patient_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _persist_scan("procedures", patient_id, payload)

    def upsert_record(self, patient_id: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        return _upsert_scan("procedures", patient_id, payload)


class DiagnosisStrategy(_BaseStrategy):
    module = ClinicalModule.DIAGNOSIS

    def extraction_profile(self) -> Dict[str, Any]:
        return {
            "system_prompt": (
                "You extract diagnoses/medical conditions from clinical notes and reports."
                + _mixed_document_rules("not_a_diagnosis_document")
            ),
            "user_prompt": (
                "Extract conditions only from a Diagnosis, Impression, Assessment, or Medical Conditions heading. "
                "Do not copy procedure/investigation Findings (ECG interpretation, imaging, endoscopy) into conditions. "
                "Do not copy C/o complaints into conditions. "
                "For each: conditionName, code (ICD-10/SNOMED), clinicalStatus (ACTIVE/RESOLVED/INACTIVE), "
                "verificationStatus, category, severity, bodySite, startDate (YYYY-MM-DD), endDate (YYYY-MM-DD), recordedBy, notes, confidence."
            ),
            "json_schema": _meta_schema(
                "conditions",
                {
                    "conditionName":      {"type": "string"},
                    "code":               {"type": "string"},
                    "clinicalStatus":     {"type": "string"},
                    "verificationStatus": {"type": "string"},
                    "category":           {"type": "string"},
                    "severity":           {"type": "string"},
                    "bodySite":           {"type": "string"},
                    "startDate":          {"type": "string"},
                    "endDate":            {"type": "string"},
                    "recordedBy":         {"type": "string"},
                    "notes":              {"type": "string"},
                    "confidence":         {"type": "number"},
                },
                ["conditionName", "code", "clinicalStatus", "verificationStatus", "category", "severity", "bodySite", "startDate", "endDate", "recordedBy", "notes", "confidence"],
            ),
            "invalid_error_code": "not_a_diagnosis_document",
            "invalid_message": "The file does not appear to be a valid diagnosis document",
        }

    def map_records(self, extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
        records = []
        for item in extracted.get("conditions") or []:
            name = (item.get("conditionName") or "").strip()
            if not name or name.lower() == "uncertain":
                continue
            status = (item.get("clinicalStatus") or item.get("status") or "ACTIVE").strip()
            end_date = (item.get("endDate") or "").strip() or None
            if status.lower() in ("active", "recurrence", "relapse"):
                end_date = None
            records.append(
                {
                    "conditionName":      name,
                    "code":               (item.get("code") or "").strip(),
                    "status":             status,
                    "verificationStatus": (item.get("verificationStatus") or "").strip(),
                    "category":           (item.get("category") or "").strip(),
                    "severity":           (item.get("severity") or "").strip(),
                    "bodySite":           (item.get("bodySite") or "").strip(),
                    "startDate":          (item.get("startDate") or extracted.get("date") or "").strip(),
                    "endDate":            end_date,
                    "recordedBy":         (item.get("recordedBy") or "").strip(),
                    "notes":              (item.get("notes") or "").strip(),
                }
            )
        return records

    def matching_record(self, patient_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return _match_scan("diagnosis", patient_id, payload)

    def persist_record(self, patient_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _persist_scan("diagnosis", patient_id, payload)

    def upsert_record(self, patient_id: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        return _upsert_scan("diagnosis", patient_id, payload)


def _clean_meta(value: Any) -> str:
    """Blank out the model's 'uncertain' marker so it never reaches the UI."""
    text = (value or "").strip() if isinstance(value, str) else ""
    return "" if text.lower() == "uncertain" else text


class MedicationStrategy(_BaseStrategy):
    module = ClinicalModule.MEDICATIONS

    def extraction_profile(self) -> Dict[str, Any]:
        return {
            "system_prompt": (
                "You are a medical prescription and medication extraction specialist. "
                "You inspect scanned, photographed, or PDF medical documents, OPD sheets, and prescription charts. "
                "Extract only data that is clearly visible. Do not guess, infer, or hallucinate any data. "
                "For handwritten text, transcribe legible text and mark uncertain fields as 'uncertain'. "
                + _mixed_document_rules("not_a_medication_document")
            ),
            "user_prompt": (
                "Extract all prescribed medications/medicines from the document. "
                "Use standardized frequencies where possible: "
                "Once Daily, Twice Daily, Three Times Daily, Four Times Daily, Every other day, Once Weekly, Once Monthly, As Needed (PRN). "
                "Only report a frequency the document actually states; if it states none, return an empty frequency. "
                "For each medicine: name, strength (e.g. 500mg), dosage (e.g. 1 tablet), frequency, duration, instructions, timing, confidence. "
                + TIMING_PROMPT
                + " Also extract doctor_name, clinic, patient_name, date."
            ),
            "json_schema": _meta_schema(
                "medicines",
                {
                    "name": {"type": "string"},
                    "strength": {"type": "string"},
                    "dosage": {"type": "string"},
                    "frequency": {"type": "string"},
                    "duration": {"type": "string"},
                    "instructions": {"type": "string"},
                    "timing": TIMING_SCHEMA,
                    "confidence": {"type": "number"},
                },
                [
                    "name",
                    "strength",
                    "dosage",
                    "frequency",
                    "duration",
                    "instructions",
                    "timing",
                    "confidence",
                ],
            ),
            "invalid_error_code": "not_a_medication_document",
            "invalid_message": "The file does not appear to be a valid prescription or medication document",
        }

    def map_records(self, extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
        records = []
        doctor_name = _clean_meta(extracted.get("doctor_name"))
        clinic_name = _clean_meta(extracted.get("clinic") or extracted.get("facility"))
        # Absent or unreadable dates stay empty for the user to fill in.
        prescription_date = format_prescription_date(extracted.get("date"))
        for raw in extracted.get("medicines") or extracted.get("medications") or []:
            item = enrich_medicine_form_fields(dict(raw))
            item = clear_unsupported_schedule(item)
            name = (item.get("name") or "").strip()
            if not name or name.lower() == "uncertain":
                continue
            stated = (item.get("frequency") or "").strip()
            if stated.lower() == "uncertain":
                stated = ""
            slots = item.get("reminders") or slots_from_timing(item.get("timing"))
            frequency = stated
            if not frequency:
                frequency, slots = reconcile_frequency_with_slots(stated, slots)
            how_much = (
                item.get("howMuchToTake")
                or item.get("how_much_to_take")
                or item.get("dosage")
                or ""
            ).strip()
            records.append(
                {
                    "name": name,
                    "strength": (item.get("strength") or "").strip(),
                    "dosage": (item.get("dosage") or how_much).strip(),
                    "howMuchToTake": how_much,
                    "medicationType": item.get("medicationType"),
                    "frequency": frequency,
                    "duration": (item.get("duration") or "").strip(),
                    "instructions": (item.get("instructions") or "").strip(),
                    "reminders": slots,
                    "confidence": float(item.get("confidence") or 1.0),
                    # Preview should show the same prescriber/date the save stores.
                    "doctorName": doctor_name,
                    "facilityName": clinic_name,
                    "prescriptionDate": prescription_date,
                }
            )
        return records

    def matching_record(self, patient_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None

    def persist_record(self, patient_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return payload

    def upsert_record(self, patient_id: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        return payload, "created"


def build_strategy_registry() -> Dict[ClinicalModule, Any]:
    strategies = [
        AllergyStrategy(),
        LabReportsStrategy(),
        VitalSignsStrategy(),
        ImmunizationStrategy(),
        ProceduresStrategy(),
        DiagnosisStrategy(),
        MedicationStrategy(),
    ]
    return {s.module: s for s in strategies}
