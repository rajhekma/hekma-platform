"""Map CTMS/manual/scan payloads onto FHIR R4 resources."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Protocol, Tuple

from ..clinical_scans.modules import ClinicalModule
from ...utils.vital_signs_normalization import (
    is_blood_pressure,
    normalize_vital_sign_record,
    split_bp_values,
)
from .identity import read_ctms_payload


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _iso_date(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None

    # Handle ISO formatted dates/datetimes like "2025-05-20" or "2025-05-20T00:00:00Z"
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            pass

    # Handle 4-digit year like "2021"
    if len(text) == 4 and text.isdigit():
        return text

    # Handle DD/MM/YYYY, MM/DD/YYYY, YYYY/MM/DD
    if "/" in text:
        parts = text.split()[0].split("/")
        if len(parts) == 3:
            p0, p1, p2 = parts[0].strip(), parts[1].strip(), parts[2].strip()
            # If p0 is 4 digits -> YYYY/MM/DD
            if len(p0) == 4 and p0.isdigit() and p1.isdigit() and p2.isdigit():
                try:
                    return date(int(p0), int(p1), int(p2)).isoformat()
                except ValueError:
                    pass
            # If p2 is 4 digits -> DD/MM/YYYY or MM/DD/YYYY
            elif len(p2) == 4 and p2.isdigit() and p0.isdigit() and p1.isdigit():
                v0, v1, y = int(p0), int(p1), int(p2)
                # If first number > 12, it must be day (DD/MM/YYYY)
                if v0 > 12 and 1 <= v1 <= 12:
                    try:
                        return date(y, v1, v0).isoformat()
                    except ValueError:
                        pass
                # If second number > 12, it must be day (MM/DD/YYYY)
                elif v1 > 12 and 1 <= v0 <= 12:
                    try:
                        return date(y, v0, v1).isoformat()
                    except ValueError:
                        pass
                # Both <= 12: default to DD/MM/YYYY (international/clinical standard)
                else:
                    try:
                        return date(y, v1, v0).isoformat()
                    except ValueError:
                        pass

    # Handle DD-MM-YYYY
    if "-" in text:
        parts = text.split()[0].split("-")
        if len(parts) == 3:
            p0, p1, p2 = parts[0].strip(), parts[1].strip(), parts[2].strip()
            if len(p2) == 4 and p2.isdigit() and p0.isdigit() and p1.isdigit():
                v0, v1, y = int(p0), int(p1), int(p2)
                if v0 > 12 and 1 <= v1 <= 12:
                    try:
                        return date(y, v1, v0).isoformat()
                    except ValueError:
                        pass
                elif v1 > 12 and 1 <= v0 <= 12:
                    try:
                        return date(y, v0, v1).isoformat()
                    except ValueError:
                        pass
                else:
                    try:
                        return date(y, v1, v0).isoformat()
                    except ValueError:
                        pass

    # Fallback to dateutil parser
    try:
        from dateutil import parser as dt_parser
        parsed = dt_parser.parse(text, dayfirst=True)
        return parsed.date().isoformat()
    except Exception:
        pass

    # Named months, as prescriptions print them (08-Sep-2026). Without this the
    # truncation below would emit "08-Sep-202" as if it were a FHIR date.
    from ...utils.prescription_dates import normalize_prescription_date

    named_month = normalize_prescription_date(text)
    if named_month:
        return named_month

    return text[:10]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _code_text(resource: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        obj = resource.get(key)
        if isinstance(obj, dict):
            text = _text(obj.get("text"))
            if text:
                return text
            coding = obj.get("coding") or []
            if coding and isinstance(coding[0], dict):
                return _text(coding[0].get("display") or coding[0].get("code"))
        elif obj:
            return _text(obj)
    return ""


def _coding_code(obj: Any) -> str:
    if isinstance(obj, dict):
        coding = obj.get("coding") or []
        if coding and isinstance(coding[0], dict):
            return _text(coding[0].get("code") or coding[0].get("display"))
        return _text(obj.get("code") or obj.get("text"))
    return _text(obj)


def _note_text(resource: Dict[str, Any]) -> str:
    note = resource.get("note")
    if isinstance(note, list) and note and isinstance(note[0], dict):
        return _text(note[0].get("text"))
    return _text(resource.get("notes"))


def _first_date(*values: Any) -> Optional[str]:
    for value in values:
        parsed = _iso_date(value)
        if parsed:
            return parsed
        if isinstance(value, dict):
            parsed = _iso_date(value.get("start") or value.get("end"))
            if parsed:
                return parsed
    return None


_ALLERGY_CATEGORY_TO_MYSQL = {
    "medication": "DRUG",
    "drug": "DRUG",
    "food": "FOOD",
    "environment": "ENVIRONMENT",
    "biologic": "BIOLOGIC",
}

_ALLERGY_SEVERITY_ALIASES = {
    "MILD": "MILD",
    "LOW": "MILD",
    "MODERATE": "SEVERE",
    "SEVERE": "SEVERE",
    "HIGH": "SEVERE",
    "CRITICAL": "CRITICAL",
}

# GraphQL Patient360Persist stores the CTMS enum here because FHIR
# criticality is only low | high and cannot distinguish CRITICAL from SEVERE.
ALLERGY_SEVERITY_SYSTEM = "https://hekma.ai/fhir/allergy-severity"


def normalize_allergy_severity(value: Any) -> Optional[str]:
    """Map API/OCR/GraphQL severity onto the CTMS enum: MILD | SEVERE | CRITICAL."""
    if value is None or value == "":
        return None
    key = str(value).strip().upper()
    if key in _ALLERGY_SEVERITY_ALIASES:
        return _ALLERGY_SEVERITY_ALIASES[key]
    if key in ("MILD", "SEVERE", "CRITICAL"):
        return key
    return None


def allergy_fhir_criticality(severity: Optional[str]) -> str:
    """FHIR AllergyIntolerance.criticality only supports low | high."""
    normalized = normalize_allergy_severity(severity)
    if normalized in ("SEVERE", "CRITICAL"):
        return "high"
    return "low"


def read_allergy_severity_from_fhir(resource: Dict[str, Any]) -> str:
    """Resolve MILD | SEVERE | CRITICAL from a stored AllergyIntolerance resource."""
    for item in resource.get("identifier") or []:
        if isinstance(item, dict) and _text(item.get("system")) == ALLERGY_SEVERITY_SYSTEM:
            severity = normalize_allergy_severity(item.get("value"))
            if severity:
                return severity

    stamped = read_ctms_payload(resource)
    severity = normalize_allergy_severity(
        stamped.get("severity") or stamped.get("criticality")
    )
    if severity:
        return severity

    crit = _text(resource.get("criticality") or "low").lower()
    return "SEVERE" if crit in ("high", "severe") else "MILD"


def apply_allergy_severity_to_fhir(resource: Dict[str, Any], severity: Any) -> None:
    """Write FHIR criticality plus the Hekma severity identifier (Java parity)."""
    normalized = normalize_allergy_severity(severity) or "MILD"
    resource["criticality"] = allergy_fhir_criticality(normalized)
    identifiers = [
        item
        for item in (resource.get("identifier") or [])
        if not (
            isinstance(item, dict)
            and _text(item.get("system")) == ALLERGY_SEVERITY_SYSTEM
        )
    ]
    identifiers.append({"system": ALLERGY_SEVERITY_SYSTEM, "value": normalized})
    resource["identifier"] = identifiers


def _coding(code: Optional[str], display: str, system: Optional[str] = None) -> Dict[str, Any]:
    coding: Dict[str, Any] = {"display": display}
    if code:
        coding["code"] = code
    if system:
        coding["system"] = system
    return {"coding": [coding], "text": display}


def _allergy_clinical_status(status: str) -> Dict[str, Any]:
    code = (status or "active").lower()
    display_map = {"active": "Active", "inactive": "Inactive", "resolved": "Resolved"}
    display = display_map.get(code, "Active")
    if code not in display_map:
        code = "active"
    return {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                "code": code,
                "display": display,
            }
        ]
    }


def _allergy_verification_status(status: str = "confirmed") -> Dict[str, Any]:
    code = (status or "confirmed").lower()
    display_map = {
        "confirmed": "Confirmed",
        "unconfirmed": "Unconfirmed",
        "refuted": "Refuted",
        "entered-in-error": "Entered in Error",
    }
    display = display_map.get(code, "Confirmed")
    if code not in display_map:
        code = "confirmed"
    return {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
                "code": code,
                "display": display,
            }
        ]
    }


def _condition_clinical_status(status: str) -> Dict[str, Any]:
    code = (status or "active").lower()
    display_map = {
        "active": "Active",
        "recurrence": "Recurrence",
        "relapse": "Relapse",
        "inactive": "Inactive",
        "remission": "Remission",
        "resolved": "Resolved",
    }
    display = display_map.get(code, "Active")
    if code not in display_map:
        code = "active"
    return {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                "code": code,
                "display": display,
            }
        ]
    }


def _condition_verification_status(status: str = "confirmed") -> Dict[str, Any]:
    code = (status or "confirmed").lower()
    display_map = {
        "confirmed": "Confirmed",
        "unconfirmed": "Unconfirmed",
        "provisional": "Provisional",
        "differential": "Differential",
        "refuted": "Refuted",
        "entered-in-error": "Entered in Error",
    }
    display = display_map.get(code, "Confirmed")
    if code not in display_map:
        code = "confirmed"
    return {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                "code": code,
                "display": display,
            }
        ]
    }


class FhirResourceMapper(Protocol):
    """One mapper per clinical module; output is a FHIR dict without Hekma ids."""

    resource_type: str

    def to_fhir(self, patient_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        ...


class AllergyMapper:
    resource_type = "AllergyIntolerance"

    def to_fhir(self, patient_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        substance = _text(record.get("substance") or record.get("name"))
        status = _text(record.get("status") or "active").lower()
        severity = normalize_allergy_severity(
            record.get("severity") or record.get("criticality")
        ) or "MILD"
        category = _text(record.get("category") or "medication").lower()
        if category in ("drug", "other"):
            category = "medication"
        onset = _iso_date(record.get("startDate") or record.get("onsetDate") or record.get("onset_date") or record.get("lastOccurrence") or record.get("date"))
        rec_date = _iso_date(record.get("recordedDate") or record.get("documentDate") or record.get("date"))
        end = _iso_date(record.get("endDate"))
        last_occ = _iso_date(record.get("lastOccurrence") or record.get("last_occurrence") or end)
        if status in ("resolved", "inactive") and not last_occ:
            last_occ = end or rec_date

        code_val = _text(record.get("code") or record.get("snomedCode") or record.get("rxnormCode"))
        code_obj: Dict[str, Any] = {"text": substance}
        if code_val:
            system = "http://www.nlm.nih.gov/research/umls/rxnorm" if category == "medication" and code_val.isdigit() else "http://snomed.info/sct"
            code_obj["coding"] = [
                {
                    "system": system,
                    "code": code_val,
                    "display": substance,
                }
            ]

        resource: Dict[str, Any] = {
            "resourceType": self.resource_type,
            "clinicalStatus": _allergy_clinical_status(status),
            "verificationStatus": _allergy_verification_status(record.get("verificationStatus") or "confirmed"),
            "type": _text(record.get("allergyType") or "allergy").lower() or "allergy",
            "category": [category or "medication"],
            "code": code_obj,
            "patient": {"reference": f"Patient/{patient_id}"},
            "recordedDate": rec_date or _now_iso(),
        }
        if onset:
            resource["onsetDateTime"] = onset
        if last_occ:
            resource["lastOccurrence"] = last_occ
        reaction = _text(record.get("reaction"))
        if reaction:
            resource["reaction"] = [{"manifestation": [{"text": reaction}]}]
        notes = _text(record.get("notes"))
        if notes:
            resource["note"] = [{"text": notes}]
        apply_allergy_severity_to_fhir(resource, severity)
        return resource

    def from_fhir(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """Rebuild the MySQL/API allergy fields the Medical History UI expects."""
        substance = _code_text(resource, "code")
        cat_raw = resource.get("category")
        if isinstance(cat_raw, list):
            cat_raw = cat_raw[0] if cat_raw else ""
        cat_key = _text(cat_raw).lower()
        category = _ALLERGY_CATEGORY_TO_MYSQL.get(cat_key, _text(cat_raw).upper() or None)
        severity = read_allergy_severity_from_fhir(resource)
        criticality = severity
        allergy_type = _text(resource.get("type") or "allergy").upper() or "ALLERGY"
        status = (_coding_code(resource.get("clinicalStatus")) or "active").upper()
        start = _first_date(
            resource.get("onsetDateTime"),
            resource.get("onsetPeriod"),
            resource.get("recordedDate"),
        )
        reaction = ""
        reactions = resource.get("reaction") or []
        if reactions and isinstance(reactions[0], dict):
            manifestation = reactions[0].get("manifestation") or []
            if manifestation and isinstance(manifestation[0], dict):
                reaction = _text(manifestation[0].get("text"))
        end = _first_date(resource.get("lastOccurrence")) if status not in ("ACTIVE", "") else None
        if not end and status not in ("ACTIVE", ""):
            end = _first_date(resource.get("recordedDate"))
        return {
            "substance": substance,
            "name": substance,
            "allergyType": allergy_type,
            "severity": severity,
            "criticality": criticality,
            "category": category,
            "status": status,
            "startDate": start,
            "onsetDate": start,
            "endDate": end,
            "notes": _note_text(resource),
            "reaction": reaction or None,
        }


class ConditionMapper:
    resource_type = "Condition"

    def to_fhir(self, patient_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        name = _text(record.get("conditionName") or record.get("name"))
        status = _text(record.get("status") or "active").lower()
        onset = _iso_date(record.get("startDate") or record.get("date"))
        abatement = _iso_date(record.get("endDate")) if status not in ("active", "recurrence", "relapse", "") else None
        rec_date = _iso_date(record.get("recordedDate") or record.get("documentDate") or record.get("date"))

        code_val = _text(record.get("code") or record.get("icd10Code") or record.get("snomedCode"))
        code_obj: Dict[str, Any] = {"text": name}
        if code_val:
            system = "http://hl7.org/fhir/sid/icd-10" if any(c.isalpha() for c in code_val) else "http://snomed.info/sct"
            code_obj["coding"] = [
                {
                    "system": system,
                    "code": code_val,
                    "display": name,
                }
            ]

        resource: Dict[str, Any] = {
            "resourceType": self.resource_type,
            "clinicalStatus": _condition_clinical_status(status),
            "verificationStatus": _condition_verification_status(record.get("verificationStatus") or "confirmed"),
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                            "code": "encounter-diagnosis",
                            "display": "Encounter Diagnosis",
                        }
                    ]
                }
            ],
            "code": code_obj,
            "subject": {"reference": f"Patient/{patient_id}"},
            "recordedDate": rec_date or _now_iso(),
        }
        if onset:
            resource["onsetDateTime"] = onset
        if abatement:
            resource["abatementDateTime"] = abatement
        notes = _text(record.get("notes"))
        if notes:
            resource["note"] = [{"text": notes}]
        return resource

    def from_fhir(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        name = _code_text(resource, "code")
        start = _first_date(resource.get("onsetDateTime"), resource.get("onsetPeriod"), resource.get("recordedDate"))
        status = (_coding_code(resource.get("clinicalStatus")) or "active").upper()
        end = _first_date(resource.get("abatementDateTime"), resource.get("abatementPeriod")) if status not in ("ACTIVE", "RECURRENCE", "RELAPSE") else None
        return {
            "conditionName": name,
            "name": name,
            "status": status,
            "startDate": start,
            "endDate": end,
            "notes": _note_text(resource),
        }


class LabObservationMapper:
    resource_type = "Observation"

    def to_fhir(self, patient_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        name = _text(record.get("testName") or record.get("name"))
        loinc = _text(record.get("loincCode") or record.get("testCode") or record.get("code"))
        effective = _iso_date(record.get("resultDate") or record.get("date"))
        value = _text(record.get("testValue") or record.get("value"))
        unit = _text(record.get("unit"))
        resource: Dict[str, Any] = {
            "resourceType": self.resource_type,
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "laboratory",
                            "display": "Laboratory",
                        }
                    ]
                }
            ],
            "code": _coding(loinc or None, name, "http://loinc.org" if loinc else None),
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": effective or _now_iso()[:10],
        }
        if value:
            parsed_val = _numeric_or_text(value)
            if isinstance(parsed_val, (int, float)):
                resource["valueQuantity"] = {
                    "value": parsed_val,
                    "unit": unit or "",
                    "system": "http://unitsofmeasure.org" if unit else None,
                }
            else:
                resource["valueString"] = value
        notes = _text(record.get("notes"))
        if notes:
            resource["note"] = [{"text": notes}]
        ref = _text(record.get("referenceRange"))
        if ref:
            resource["referenceRange"] = [{"text": ref}]
        return resource

    def from_fhir(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        name = _code_text(resource, "code")
        qty = resource.get("valueQuantity") if isinstance(resource.get("valueQuantity"), dict) else {}
        ref = resource.get("referenceRange")
        ref_text = ""
        if isinstance(ref, list) and ref and isinstance(ref[0], dict):
            ref_text = _text(ref[0].get("text"))
        value = qty.get("value")
        if value is None:
            value = resource.get("valueString")
        return {
            "testName": name,
            "name": name,
            "testValue": "" if value is None else str(value),
            "unit": _text(qty.get("unit")),
            "referenceRange": ref_text,
            "resultDate": _first_date(resource.get("effectiveDateTime"), resource.get("issued")),
            "notes": _note_text(resource),
            "loincCode": _coding_code(resource.get("code")),
        }


_VITAL_LOINC_MAP = {
    "blood pressure": "85354-9",
    "systolic": "8480-6",
    "diastolic": "8462-4",
    "heart rate": "8867-4",
    "pulse": "8867-4",
    "body temperature": "8310-5",
    "temperature": "8310-5",
    "oxygen saturation": "2708-6",
    "spo2": "2708-6",
    "respiratory rate": "9279-1",
    "body height": "8302-2",
    "height": "8302-2",
    "body weight": "29463-7",
    "weight": "29463-7",
    "body mass index": "39156-5",
    "bmi": "39156-5",
}


def _component_loinc(comp: Dict[str, Any]) -> str:
    code = comp.get("code") if isinstance(comp, dict) else {}
    if not isinstance(code, dict):
        return ""
    for item in code.get("coding") or []:
        if isinstance(item, dict) and item.get("code"):
            return str(item["code"])
    return _text(code.get("text")).lower()


def _component_quantity(comp: Dict[str, Any]) -> Tuple[str, str]:
    qty = comp.get("valueQuantity") if isinstance(comp, dict) else {}
    if isinstance(qty, dict) and qty.get("value") is not None:
        return str(qty.get("value")), _text(qty.get("unit"))
    return _text(comp.get("valueString")), ""


def _observation_top_quantity(resource: Dict[str, Any]) -> Tuple[str, str]:
    qty = resource.get("valueQuantity") if isinstance(resource.get("valueQuantity"), dict) else {}
    v1 = "" if qty.get("value") is None else str(qty.get("value"))
    if not v1:
        v1 = _text(resource.get("valueString"))
    return v1, _text(qty.get("unit"))


def _bp_values_from_components(components: list) -> Tuple[str, str, str]:
    systolic = ""
    diastolic = ""
    unit = ""
    for comp in components:
        if not isinstance(comp, dict):
            continue
        value, comp_unit = _component_quantity(comp)
        if not value:
            continue
        loinc = _component_loinc(comp)
        label = loinc
        if not loinc:
            label = _text((comp.get("code") or {}).get("text")).lower()
        if loinc == "8480-6" or "systolic" in label:
            systolic = value
            unit = unit or comp_unit
        elif loinc == "8462-4" or "diastolic" in label or "secondary" in label:
            diastolic = value
            unit = unit or comp_unit
    if not systolic and not diastolic and len(components) >= 2:
        q1 = components[0].get("valueQuantity") if isinstance(components[0], dict) else {}
        q2 = components[1].get("valueQuantity") if isinstance(components[1], dict) else {}
        if isinstance(q1, dict) and q1.get("value") is not None:
            systolic = str(q1.get("value"))
            unit = _text(q1.get("unit"))
        if isinstance(q2, dict) and q2.get("value") is not None:
            diastolic = str(q2.get("value"))
            unit = unit or _text(q2.get("unit"))
    return systolic, diastolic, unit


def _bp_values_from_observation(resource: Dict[str, Any]) -> Tuple[str, str, str]:
    """Read BP from FHIR including legacy manual-entry shape (top-level + secondary component)."""
    top_v1, top_unit = _observation_top_quantity(resource)
    components = resource.get("component") or []
    if not isinstance(components, list):
        components = []

    systolic, diastolic, unit = _bp_values_from_components(components)

    if not systolic and top_v1:
        systolic = top_v1
        unit = unit or top_unit

    if not diastolic and len(components) == 1:
        comp = components[0]
        if isinstance(comp, dict):
            comp_val, comp_unit = _component_quantity(comp)
            label = _component_loinc(comp) or _text((comp.get("code") or {}).get("text")).lower()
            if comp_val and (
                "secondary" in label
                or "diastolic" in label
                or (systolic and comp_val != systolic)
            ):
                diastolic = comp_val
                unit = unit or comp_unit

    if not systolic and not diastolic:
        return top_v1, "", top_unit
    return systolic, diastolic, unit


class VitalObservationMapper:
    resource_type = "Observation"

    def to_fhir(self, patient_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        record = normalize_vital_sign_record(record)
        name = _text(record.get("type") or record.get("name"))
        effective = _iso_date(record.get("dateOfObservation") or record.get("date"))
        v1 = _text(record.get("refValue1") or record.get("value"))
        v2 = _text(record.get("refValue2") or record.get("value2"))
        unit = _text(record.get("metric") or record.get("unit"))

        loinc = _text(record.get("loincCode") or record.get("code") or _VITAL_LOINC_MAP.get(name.lower()))
        code_obj = _coding(loinc or None, name, "http://loinc.org" if loinc else None)

        resource: Dict[str, Any] = {
            "resourceType": self.resource_type,
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "vital-signs",
                            "display": "Vital Signs",
                        }
                    ]
                }
            ],
            "code": code_obj,
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": effective or _now_iso()[:10],
        }
        if v1 and v2:
            resource["component"] = [
                {
                    "code": _coding("8480-6", "Systolic blood pressure", "http://loinc.org"),
                    "valueQuantity": _qty(v1, unit or "mmHg"),
                },
                {
                    "code": _coding("8462-4", "Diastolic blood pressure", "http://loinc.org"),
                    "valueQuantity": _qty(v2, unit or "mmHg"),
                },
            ]
        elif v1:
            qty = _qty(v1, unit)
            if isinstance(qty.get("value"), (int, float)):
                resource["valueQuantity"] = qty
            else:
                resource["valueString"] = v1
        notes = _text(record.get("notes"))
        if notes:
            resource["note"] = [{"text": notes}]
        return resource

    def from_fhir(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        name = _code_text(resource, "code")
        v1 = ""
        v2 = ""
        unit = ""
        components = resource.get("component") or []
        if is_blood_pressure(name):
            v1, v2, unit = _bp_values_from_observation(resource)
            v1, v2 = split_bp_values(v1, v2 or "")
        elif isinstance(components, list) and components:
            v1, v2, unit = _bp_values_from_components(components)
            if not v1 and not v2:
                v1, unit = _observation_top_quantity(resource)
        else:
            v1, unit = _observation_top_quantity(resource)
        return normalize_vital_sign_record(
            {
                "type": name,
                "name": name,
                "refValue1": v1,
                "refValue2": v2 or None,
                "metric": unit,
                "dateOfObservation": _first_date(
                    resource.get("effectiveDateTime"), resource.get("issued")
                ),
                "notes": _note_text(resource),
            }
        )


class ImmunizationMapper:
    resource_type = "Immunization"

    def to_fhir(self, patient_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        name = _text(record.get("vaccineName") or record.get("name"))
        when = _iso_date(record.get("vaccinationDate") or record.get("date"))
        cvx = _text(record.get("cvxCode") or record.get("code"))
        code_obj: Dict[str, Any] = {"text": name}
        if cvx:
            code_obj["coding"] = [{"system": "http://hl7.org/fhir/sid/cvx", "code": cvx, "display": name}]

        resource: Dict[str, Any] = {
            "resourceType": self.resource_type,
            "status": "completed",
            "vaccineCode": code_obj,
            "patient": {"reference": f"Patient/{patient_id}"},
            "primarySource": True,
            "recorded": _now_iso(),
        }
        if when:
            resource["occurrenceDateTime"] = when
        notes = _text(record.get("notes"))
        if notes:
            resource["note"] = [{"text": notes}]
        return resource

    def from_fhir(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        name = _code_text(resource, "vaccineCode")
        return {
            "vaccineName": name,
            "name": name,
            "vaccinationDate": _first_date(
                resource.get("occurrenceDateTime"),
                resource.get("occurrenceString"),
                resource.get("recorded"),
            ),
            "notes": _note_text(resource),
        }


class ProcedureMapper:
    resource_type = "Procedure"

    def to_fhir(self, patient_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        name = _text(record.get("procedureName") or record.get("name"))
        status = _text(record.get("status") or "completed").lower()
        start = _iso_date(record.get("startDate") or record.get("date"))
        end = _iso_date(record.get("endDate"))
        cpt = _text(record.get("cptCode") or record.get("snomedCode") or record.get("code"))
        code_obj: Dict[str, Any] = {"text": name}
        if cpt:
            system = "http://www.ama-assn.org/go/cpt" if cpt.isdigit() and len(cpt) == 5 else "http://snomed.info/sct"
            code_obj["coding"] = [{"system": system, "code": cpt, "display": name}]

        resource: Dict[str, Any] = {
            "resourceType": self.resource_type,
            "status": status if status in ("completed", "in-progress", "not-done", "on-hold", "stopped") else "completed",
            "code": code_obj,
            "subject": {"reference": f"Patient/{patient_id}"},
        }
        if start or end:
            period: Dict[str, Any] = {}
            if start:
                period["start"] = start
            if end:
                period["end"] = end
            resource["performedPeriod"] = period
        location = _text(record.get("location") or record.get("facility"))
        if location:
            resource["location"] = {"display": location}
        reason = _text(record.get("reason"))
        if reason:
            resource["reasonCode"] = [{"text": reason}]
        notes = _text(record.get("notes"))
        if notes:
            resource["note"] = [{"text": notes}]
        return resource

    def from_fhir(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        name = _code_text(resource, "code")
        period = resource.get("performedPeriod") if isinstance(resource.get("performedPeriod"), dict) else {}
        location = resource.get("location")
        location_name = ""
        if isinstance(location, dict):
            location_name = _text(location.get("display"))
        reason = ""
        reasons = resource.get("reasonCode") or []
        if reasons and isinstance(reasons[0], dict):
            reason = _text(reasons[0].get("text")) or _code_text(reasons[0] if "coding" in reasons[0] else {"code": reasons[0]})
        return {
            "procedureName": name,
            "name": name,
            "status": (_text(resource.get("status")) or "completed").upper(),
            "startDate": _first_date(period.get("start"), resource.get("performedDateTime")),
            "endDate": _first_date(period.get("end")),
            "location": location_name or None,
            "reason": reason or None,
            "notes": _note_text(resource),
        }


class MedicationRequestMapper:
    resource_type = "MedicationRequest"

    def to_fhir(self, patient_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        name = _text(record.get("name") or record.get("medicineName") or record.get("medicationName"))
        status = _text(record.get("status") or "active").lower()
        authored_on = _iso_date(record.get("prescriptionDate") or record.get("startDate") or record.get("date"))
        intent = _text(record.get("intent") or "order").lower()
        strength = _text(record.get("strength"))
        dosage_text = _text(record.get("dosage") or record.get("instructions"))
        frequency = _text(record.get("frequency"))
        rxnorm = _text(record.get("rxnormCode") or record.get("code"))

        code_obj: Dict[str, Any] = {"text": f"{name} {strength}".strip() if strength else name}
        if rxnorm:
            code_obj["coding"] = [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": rxnorm, "display": name}]

        resource: Dict[str, Any] = {
            "resourceType": self.resource_type,
            "status": status if status in ("active", "on-hold", "cancelled", "completed", "entered-in-error", "stopped", "draft") else "active",
            "intent": intent if intent in ("proposal", "plan", "order", "original-order", "reflex-order", "filler-order", "instance-order", "option") else "order",
            "medicationCodeableConcept": code_obj,
            "subject": {"reference": f"Patient/{patient_id}"},
            "authoredOn": authored_on or _now_iso(),
        }
        dosage_instruction: Dict[str, Any] = {}
        if dosage_text:
            dosage_instruction["text"] = dosage_text
        if frequency:
            dosage_instruction["patientInstruction"] = frequency
        if dosage_instruction:
            resource["dosageInstruction"] = [dosage_instruction]
        doctor = _text(record.get("doctorName") or record.get("prescriberName"))
        if doctor:
            resource["requester"] = {"display": doctor}
        notes = _text(record.get("notes"))
        if notes:
            resource["note"] = [{"text": notes}]
        return resource

    def from_fhir(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        mcc = resource.get("medicationCodeableConcept") if isinstance(resource.get("medicationCodeableConcept"), dict) else {}
        name = _text(mcc.get("text"))
        if not name and isinstance(mcc.get("coding"), list):
            for coding in mcc["coding"]:
                if isinstance(coding, dict) and coding.get("display"):
                    name = _text(coding.get("display"))
                    break
        status_raw = str(resource.get("status") or "active").lower()
        if status_raw == "active":
            app_status = "Active"
        elif status_raw in ("stopped", "cancelled", "completed", "on-hold"):
            app_status = "Stopped"
        else:
            app_status = status_raw.title()
        dosage_instruction = resource.get("dosageInstruction")
        dosage_text = ""
        frequency = ""
        if isinstance(dosage_instruction, list) and dosage_instruction:
            first = dosage_instruction[0]
            if isinstance(first, dict):
                dosage_text = _text(first.get("text"))
                frequency = _text(first.get("patientInstruction"))
        requester = resource.get("requester") if isinstance(resource.get("requester"), dict) else {}
        return {
            "name": name,
            "medicationName": name,
            "status": app_status,
            "dosage": dosage_text,
            "frequency": frequency,
            "instructions": dosage_text,
            "prescriptionDate": _first_date(resource.get("authoredOn")),
            "startDate": _first_date(resource.get("authoredOn")),
            "doctorName": _text(requester.get("display")),
            "notes": _note_text(resource),
        }


def _numeric_or_text(value: str) -> Any:
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _qty(value: str, unit: str) -> Dict[str, Any]:
    parsed = _numeric_or_text(value)
    qty: Dict[str, Any] = {
        "value": parsed if isinstance(parsed, (int, float)) else value,
    }
    if unit:
        qty["unit"] = unit
        qty["system"] = "http://unitsofmeasure.org"
    return qty


class MapperRegistry:
    """Resolves a ClinicalModule to its FHIR mapper (open for new modules)."""

    def __init__(self, mappers: Optional[Dict[ClinicalModule, FhirResourceMapper]] = None):
        self._mappers = mappers or {
            ClinicalModule.ALLERGIES: AllergyMapper(),
            ClinicalModule.DIAGNOSIS: ConditionMapper(),
            ClinicalModule.LAB_REPORTS: LabObservationMapper(),
            ClinicalModule.VITAL_SIGNS: VitalObservationMapper(),
            ClinicalModule.IMMUNIZATION: ImmunizationMapper(),
            ClinicalModule.PROCEDURES: ProcedureMapper(),
            ClinicalModule.MEDICATIONS: MedicationRequestMapper(),
        }

    def mapper_for(self, module: ClinicalModule) -> FhirResourceMapper:
        mapper = self._mappers.get(module)
        if mapper is None:
            raise ValueError(f"No FHIR mapper for module {module.value}")
        return mapper
