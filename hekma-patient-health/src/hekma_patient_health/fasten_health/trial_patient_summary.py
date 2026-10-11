"""
Trial-matching patient summary from exported Fasten Health FHIR rows.

Produces:
  - structured_json: deduplicated compact clinical facts for downstream pipelines
  - summary_text: one-paragraph narrative for clinical trial eligibility screening
  - disease_list: confirmed condition names for eligibility filters
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_SKIP_AI = os.getenv("FASTEN_EXPORT_SKIP_AI", "false").lower() in ("1", "true", "yes")
_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
_MAX_LIST_ITEMS = 50
_SUMMARY_MAX_TOKENS = int(os.getenv("FASTEN_TRIAL_SUMMARY_MAX_TOKENS", "1600"))

_TRIAL_SUMMARY_SYSTEM_PROMPT = """
You are generating a clinical summary from a patient's structured health record (FHIR-based JSON export) for clinical trial eligibility screening.

Using only the data in the `data` object (plus any provided data_quality_issues / data_recency notes), produce ONE flowing paragraph.

Requirements:
1. De-duplicate — the same clinical fact may appear across multiple connections; merge into single clinical statements.
2. Cover these categories when present: demographics (name, sex, DOB, age if calculable, location, marital status, race/ethnicity); active and resolved conditions with onset/resolution dates or onset age; allergies/intolerances with substance, severity/criticality, onset year if available, and status; medications with dose, route, and date range of use (including inhalers/asthma meds if present); immunizations with exact vaccine names and dates; procedures with dates; inpatient/outpatient encounters with facility/location and dates; care-plan notes if clinically relevant; lab results with values and reference ranges (explicitly flag out-of-range values); vital signs with dates (note if blood pressure is elevated/hypertensive); social history including smoking status and smoking period if present.
3. Flag data-quality issues — mention inconsistencies instead of silently resolving them (example: conflicting onset dates or onset age vs calendar onset for the same condition; allergy marked both severe and later resolved in one record).
4. Flag data recency — state that clinical data is dated to the most recent year/date in the record and, if old, say clearly that there is no documentation reflecting current status many years later and that this is an important caveat for trial-eligibility assessment.
5. Style:
   - Start with the patient name and demographics in this pattern when available:
     "<Name> is a <sex> patient born <Month D, YYYY> (age ~N), residing in <City, ST>, <marital status>, <race>, <ethnicity>."
   - Prefer specific clinical detail over generic phrasing.
   - Prefer exact dates (e.g., August 6–13, 2012) over vague month-only phrasing when dates exist.
   - Prefer clean disease/medication names (e.g., "Asthma", "Pneumonia") rather than long status-embedded FHIR text strings.
   - Write one continuous paragraph. No headings, bullets, tables, or numbered lists.
   - Do NOT invent facts. Do NOT add recommendations.
6. Omit raw FHIR IDs, system URLs, org connection IDs, and other non-clinical metadata.

Return only the summary paragraph text.
""".strip()

_DISEASE_LIST_SYSTEM_PROMPT = """
You are an expert clinical information extraction system.

Task: Extract all confirmed disease or condition names from the given clinical text.

Output Requirements:
* Return ONLY valid JSON.
* Use this exact schema:
{"disease_list": ["disease 1", "disease 2"]}

Rules:
1. Include only confirmed diagnoses or clearly stated medical conditions.
2. Exclude symptoms, signs, procedures, lab results, medications, demographics.
3. Only use the "conditions" field for diagnoses.
4. Ignore ruled-out or family-history-only conditions unless confirmed.
5. Normalize abbreviations and remove duplicates (case-insensitive).

If no diseases or conditions are found, return:
{"disease_list": []}
""".strip()

_SOCIAL_HISTORY_HINTS = frozenset({
    "smoking",
    "tobacco",
    "alcohol",
    "substance",
    "social history",
})

_ACTIVE_CONDITION_CODES = frozenset({"active", "recurrence", "relapse"})
_RESOLVED_CONDITION_CODES = frozenset({"resolved", "inactive", "remission"})
_RESOLVED_SNOMED_CODES = frozenset({"413322009"})  # SNOMED: Resolved
_ACTIVE_STATUS_RE = re.compile(r"\bstatus\s*[-:]?\s*active\b", re.IGNORECASE)
_RESOLVED_STATUS_RE = re.compile(r"\bstatus\s*[-:]?\s*resolved\b", re.IGNORECASE)
_CLEAN_CONDITION_NAME_RE = re.compile(
    r"\s*\(.*?\)|\s*:\s*status\s*[-:].*$|\s*health status:.*$",
    re.IGNORECASE,
)


@dataclass
class TrialPatientSummary:
    """Trial-matching summary block for one patient export."""

    summary_text: str
    structured_json: Dict[str, Any]
    disease_list: List[str]
    generated_by: str
    model: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary_text": self.summary_text,
            "structured_json": self.structured_json,
            "disease_list": self.disease_list,
            "generated_by": self.generated_by,
            "model": self.model,
        }


@dataclass
class _DedupeState:
    seen_keys: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    duplicate_count: int = 0
    quality_issues: List[str] = field(default_factory=list)


def _parse_raw(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _safe_get_display(resource: Dict[str, Any], *paths: List[Any]) -> Optional[str]:
    for path in paths:
        value: Any = resource
        try:
            for key in path:
                value = value[key]
            if value:
                return str(value).strip()
        except (KeyError, IndexError, TypeError):
            continue
    return None


def _normalize_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _calculate_age(birth_date: Optional[str], as_of: Optional[date] = None) -> Optional[int]:
    dob = _parse_date(birth_date)
    if not dob:
        return None
    today = as_of or date.today()
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return max(years, 0)


def _condition_status_code(raw: Dict[str, Any], field_name: str) -> str:
    block = raw.get(field_name) or {}
    for coding in block.get("coding") or []:
        code = str(coding.get("code") or "").lower()
        display = str(coding.get("display") or "").lower()
        if code in _RESOLVED_SNOMED_CODES or display in _RESOLVED_CONDITION_CODES:
            return "resolved"
        if display in _ACTIVE_CONDITION_CODES or code in _ACTIVE_CONDITION_CODES:
            return display if display in _ACTIVE_CONDITION_CODES else code
        if code:
            return code
    text = str(block.get("text") or "").lower()
    if text in _ACTIVE_CONDITION_CODES or text in _RESOLVED_CONDITION_CODES:
        return text
    return ""


def _clean_condition_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    cleaned = _CLEAN_CONDITION_NAME_RE.sub("", name).strip(" :-")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or name.strip()


def _infer_condition_status(raw: Dict[str, Any], display_name: Optional[str]) -> str:
    """Derive active/resolved/unknown from FHIR clinicalStatus or embedded text."""
    coded = _condition_status_code(raw, "clinicalStatus")
    if coded in _ACTIVE_CONDITION_CODES or coded in _RESOLVED_CONDITION_CODES:
        return coded
    if coded in _RESOLVED_SNOMED_CODES:
        return "resolved"

    text_blob = " ".join(
        [
            str(display_name or ""),
            str((raw.get("code") or {}).get("text") or ""),
            str((raw.get("clinicalStatus") or {}).get("text") or ""),
        ]
    )
    if _RESOLVED_STATUS_RE.search(text_blob):
        return "resolved"
    if _ACTIVE_STATUS_RE.search(text_blob):
        return "active"

    period = raw.get("onsetPeriod") or {}
    if period.get("end") and not period.get("start"):
        return "resolved"
    return "unknown"


def _extract_condition_dates(raw: Dict[str, Any]) -> Dict[str, Any]:
    period = raw.get("onsetPeriod") or {}
    onset_age = raw.get("onsetAge") or {}
    onset_age_years = None
    if isinstance(onset_age, dict) and onset_age.get("value") is not None:
        onset_age_years = onset_age.get("value")

    return {
        "onset_date": (
            raw.get("onsetDateTime")
            or period.get("start")
            or raw.get("recordedDate")
        ),
        "resolution_date": raw.get("abatementDateTime") or period.get("end"),
        "onset_age_years": onset_age_years,
    }


def _resource_type_from_row(table_name: str, raw: Dict[str, Any]) -> str:
    return str(raw.get("resourceType") or table_name.replace("fastenhealth_", "")).lower()


def _clinical_fingerprint(table_name: str, raw: Dict[str, Any]) -> str:
    """Build a dedupe key from clinical identity, ignoring org_connection_id."""
    resource_type = _resource_type_from_row(table_name, raw)
    name = (
        _safe_get_display(raw, ["code", "text"], ["code", "coding", 0, "display"])
        or _safe_get_display(
            raw,
            ["medicationCodeableConcept", "text"],
            ["medicationCodeableConcept", "coding", 0, "display"],
        )
        or _safe_get_display(raw, ["vaccineCode", "text"], ["vaccineCode", "coding", 0, "display"])
        or _safe_get_display(raw, ["type", 0, "text"], ["type", 0, "coding", 0, "display"])
    )
    date_hint = (
        raw.get("onsetDateTime")
        or raw.get("recordedDate")
        or raw.get("authoredOn")
        or raw.get("effectiveDateTime")
        or raw.get("occurrenceDateTime")
        or raw.get("performedDateTime")
    )
    return "|".join(
        [
            table_name,
            resource_type,
            _normalize_text(name),
            str(date_hint or "")[:10],
        ]
    )


def _dedupe_rows(
    table_name: str,
    rows: List[Dict[str, Any]],
    state: _DedupeState,
) -> List[Dict[str, Any]]:
    """Merge duplicate resources that appear across org connections."""
    deduped: List[Dict[str, Any]] = []
    for row in rows:
        raw = _parse_raw(row.get("raw_resource"))
        resource_id = str(row.get("resource_id") or raw.get("id") or "").strip()
        fingerprint = _clinical_fingerprint(table_name, raw)
        dedupe_key = f"{table_name}|id:{resource_id}" if resource_id else fingerprint

        if dedupe_key in state.seen_keys:
            state.duplicate_count += 1
            prior = state.seen_keys[dedupe_key]
            prior_onset = prior.get("_onset_date")
            current_onset = raw.get("onsetDateTime") or raw.get("recordedDate")
            if prior_onset and current_onset and str(prior_onset)[:10] != str(current_onset)[:10]:
                label = _safe_get_display(raw, ["code", "text"], ["code", "coding", 0, "display"]) or resource_id
                state.quality_issues.append(
                    f"Conflicting dates for {label}: {prior_onset} vs {current_onset}"
                )
            continue

        clean_row = {
            "raw_resource": raw,
            "created_at": row.get("created_at"),
        }
        clean_row["_onset_date"] = raw.get("onsetDateTime") or raw.get("recordedDate")
        state.seen_keys[dedupe_key] = clean_row
        deduped.append(clean_row)
    return deduped


def deduplicate_export_data(
    export_data: Dict[str, List[Dict[str, Any]]],
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str], int]:
    """Return deduplicated table data plus quality notes and duplicate count."""
    state = _DedupeState()
    deduped_data: Dict[str, List[Dict[str, Any]]] = {}
    for table_name, rows in export_data.items():
        if not rows:
            continue
        deduped_data[table_name] = _dedupe_rows(table_name, rows, state)
    return deduped_data, state.quality_issues, state.duplicate_count


def _strip_metadata_from_data(
    export_data: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Remove non-clinical metadata before sending to the LLM."""
    cleaned: Dict[str, List[Dict[str, Any]]] = {}
    for table_name, rows in export_data.items():
        table_rows: List[Dict[str, Any]] = []
        for row in rows:
            raw = _parse_raw(row.get("raw_resource"))
            table_rows.append({"raw_resource": _sanitize_raw_resource(raw)})
        if table_rows:
            cleaned[table_name] = table_rows
    return cleaned


def _sanitize_raw_resource(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Drop FHIR ids, meta, and identifier blocks from raw_resource."""
    if not raw:
        return {}
    cleaned = json.loads(json.dumps(raw, default=str))
    for key in ("id", "meta", "identifier", "subject", "patient", "encounter"):
        cleaned.pop(key, None)
    return cleaned


def _extract_address(raw: Dict[str, Any]) -> Optional[str]:
    addresses = raw.get("address") or []
    if not addresses or not isinstance(addresses[0], dict):
        return None
    addr = addresses[0]
    parts = [
        " ".join(addr.get("line") or []),
        addr.get("city"),
        addr.get("state"),
        addr.get("postalCode"),
        addr.get("country"),
    ]
    text = ", ".join(part for part in parts if part)
    return text or None


def _extract_extension_value(raw: Dict[str, Any], url_fragment: str) -> Optional[str]:
    for ext in raw.get("extension") or []:
        url = str(ext.get("url") or "")
        if url_fragment.lower() in url.lower():
            if ext.get("valueString"):
                return str(ext["valueString"])
            if ext.get("valueCodeableConcept"):
                return _safe_get_display(
                    ext["valueCodeableConcept"],
                    ["text"],
                    ["coding", 0, "display"],
                )
    return None


def _extract_demographics(patient_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not patient_rows:
        return {}

    merged_names: List[str] = []
    genders: List[str] = []
    birth_dates: List[str] = []
    locations: List[str] = []
    marital_statuses: List[str] = []
    races: List[str] = []
    ethnicities: List[str] = []

    for row in patient_rows:
        raw = _parse_raw(row.get("raw_resource"))
        name = _safe_get_display(raw, ["name", 0, "text"])
        if not name:
            family = (raw.get("name") or [{}])[0].get("family", "")
            given = " ".join((raw.get("name") or [{}])[0].get("given") or [])
            name = f"{given} {family}".strip()
        if name:
            merged_names.append(name)
        if raw.get("gender"):
            genders.append(str(raw["gender"]))
        if raw.get("birthDate"):
            birth_dates.append(str(raw["birthDate"]))
        if _extract_address(raw):
            locations.append(_extract_address(raw) or "")
        marital = _safe_get_display(raw, ["maritalStatus", "text"], ["maritalStatus", "coding", 0, "display"])
        if marital:
            marital_statuses.append(marital)
        race = _extract_extension_value(raw, "race") or _safe_get_display(
            raw, ["extension", 0, "valueCodeableConcept", "text"]
        )
        if race:
            races.append(race)
        ethnicity = _extract_extension_value(raw, "ethnicity")
        if ethnicity:
            ethnicities.append(ethnicity)

    birth_date = birth_dates[0] if birth_dates else None
    demo: Dict[str, Any] = {
        "name": merged_names[0] if merged_names else None,
        "sex": genders[0] if genders else None,
        "birth_date": birth_date,
        "age_years": _calculate_age(birth_date),
        "location": locations[0] if locations else None,
        "marital_status": marital_statuses[0] if marital_statuses else None,
        "race": races[0] if races else None,
        "ethnicity": ethnicities[0] if ethnicities else None,
    }
    if len(set(genders)) > 1:
        demo["data_quality_note"] = f"Conflicting sex values across patient records: {sorted(set(genders))}"
    if len(set(birth_dates)) > 1:
        demo["data_quality_note"] = (
            f"Conflicting birth dates across patient records: {sorted(set(birth_dates))}"
        )
    return demo


def _extract_conditions(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract and merge conditions by clean disease name."""
    merged: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        raw = _parse_raw(row.get("raw_resource"))
        if _condition_status_code(raw, "verificationStatus") == "entered-in-error":
            continue

        coding_name = _safe_get_display(raw, ["code", "coding", 0, "display"])
        text_name = _safe_get_display(raw, ["code", "text"])
        name = _clean_condition_name(coding_name or text_name)
        if not name:
            continue

        status = _infer_condition_status(raw, text_name or coding_name)
        dates = _extract_condition_dates(raw)
        key = name.lower()
        existing = merged.get(key)
        if not existing:
            merged[key] = {
                "name": name,
                "clinical_status": status,
                "onset_date": dates["onset_date"],
                "resolution_date": dates["resolution_date"],
                "onset_age_years": dates["onset_age_years"],
                "status_sources": [status] if status != "unknown" else [],
                "onset_sources": [dates["onset_date"]] if dates["onset_date"] else [],
            }
            continue

        if dates["onset_date"]:
            existing["onset_sources"].append(dates["onset_date"])
            if not existing.get("onset_date"):
                existing["onset_date"] = dates["onset_date"]
        if dates["resolution_date"] and not existing.get("resolution_date"):
            existing["resolution_date"] = dates["resolution_date"]
        if dates["onset_age_years"] is not None and existing.get("onset_age_years") is None:
            existing["onset_age_years"] = dates["onset_age_years"]
        if status != "unknown":
            existing["status_sources"].append(status)
            if existing["clinical_status"] == "unknown" or (
                status == "active" and existing["clinical_status"] != "active"
            ):
                existing["clinical_status"] = status

    items: List[Dict[str, Any]] = []
    for item in merged.values():
        onset_dates = sorted(
            {
                str(value)[:10]
                for value in item.pop("onset_sources", [])
                if value
            }
        )
        statuses = sorted(set(item.pop("status_sources", [])))
        notes: List[str] = []
        if len(onset_dates) > 1:
            notes.append(f"Conflicting onset dates: {', '.join(onset_dates)}")
        if item.get("onset_date") and item.get("onset_age_years") is not None:
            notes.append(f"Onset also recorded as age {item['onset_age_years']}")
        if len(statuses) > 1:
            notes.append(f"Conflicting statuses: {', '.join(statuses)}")
        if notes:
            item["data_quality_notes"] = notes
        items.append(item)

    return items[:_MAX_LIST_ITEMS]


def _extract_allergies(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        raw = _parse_raw(row.get("raw_resource"))
        substance = (
            _safe_get_display(raw, ["code", "text"], ["code", "coding", 0, "display"])
            or _safe_get_display(raw, ["reaction", 0, "substance", "text"])
        )
        if not substance:
            continue
        items.append(
            {
                "substance": substance,
                "severity": _safe_get_display(raw, ["reaction", 0, "severity"]),
                "criticality": raw.get("criticality"),
                "status": raw.get("clinicalStatus") or raw.get("verificationStatus") or raw.get("status"),
            }
        )
    return items[:_MAX_LIST_ITEMS]


def _extract_medications(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        raw = _parse_raw(row.get("raw_resource"))
        name = _safe_get_display(
            raw,
            ["medicationCodeableConcept", "text"],
            ["medicationCodeableConcept", "coding", 0, "display"],
        )
        if not name:
            continue
        dosage = (raw.get("dosageInstruction") or [{}])[0]
        dose = _safe_get_display(dosage, ["doseAndRate", 0, "doseQuantity", "value"])
        unit = _safe_get_display(dosage, ["doseAndRate", 0, "doseQuantity", "unit"])
        route = _safe_get_display(dosage, ["route", "text"], ["route", "coding", 0, "display"])
        items.append(
            {
                "name": name,
                "status": raw.get("status"),
                "dose": f"{dose} {unit}".strip() if dose else None,
                "route": route,
                "start_date": raw.get("authoredOn") or raw.get("dateWritten") or raw.get("effectiveDateTime"),
                "end_date": raw.get("dateEnded"),
            }
        )
    return items[:_MAX_LIST_ITEMS]


def _extract_immunizations(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        raw = _parse_raw(row.get("raw_resource"))
        vaccine = _safe_get_display(
            raw,
            ["vaccineCode", "text"],
            ["vaccineCode", "coding", 0, "display"],
        )
        if not vaccine:
            continue
        items.append(
            {
                "vaccine": vaccine,
                "status": raw.get("status"),
                "date": raw.get("occurrenceDateTime") or raw.get("date"),
            }
        )
    return items[:_MAX_LIST_ITEMS]


def _extract_procedures(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        raw = _parse_raw(row.get("raw_resource"))
        name = _safe_get_display(raw, ["code", "text"], ["code", "coding", 0, "display"])
        if not name:
            continue
        performed = raw.get("performedDateTime") or raw.get("performedPeriod", {}).get("start")
        items.append({"name": name, "status": raw.get("status"), "date": performed})
    return items[:_MAX_LIST_ITEMS]


def _observation_category(raw: Dict[str, Any]) -> str:
    categories = raw.get("category") or []
    codes: List[str] = []
    for cat in categories:
        for coding in cat.get("coding") or []:
            if coding.get("code"):
                codes.append(str(coding["code"]).lower())
    text = " ".join(codes)
    if "laboratory" in text:
        return "laboratory"
    if "vital-signs" in text or "vital-signs" in str(raw.get("code", {})).lower():
        return "vital-signs"
    name = _normalize_text(_safe_get_display(raw, ["code", "text"], ["code", "coding", 0, "display"]))
    if any(token in name for token in _SOCIAL_HISTORY_HINTS):
        return "social-history"
    return "other"


def _extract_observation_entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    value_quantity = raw.get("valueQuantity") or {}
    value_text = value_quantity.get("value")
    unit = value_quantity.get("unit")
    if value_text is not None and unit:
        value_display = f"{value_text} {unit}".strip()
    else:
        value_display = raw.get("valueString") or _safe_get_display(raw, ["valueCodeableConcept", "text"])

    ref_low = _safe_get_display(raw, ["referenceRange", 0, "low", "value"])
    ref_high = _safe_get_display(raw, ["referenceRange", 0, "high", "value"])
    ref_text = None
    if ref_low or ref_high:
        ref_text = f"{ref_low or '?'} - {ref_high or '?'}"

    out_of_range = None
    try:
        if value_text is not None and ref_low is not None and ref_high is not None:
            numeric = float(value_text)
            low = float(ref_low)
            high = float(ref_high)
            if numeric < low:
                out_of_range = "low"
            elif numeric > high:
                out_of_range = "high"
    except (TypeError, ValueError):
        out_of_range = None

    return {
        "name": _safe_get_display(raw, ["code", "text"], ["code", "coding", 0, "display"]),
        "value": value_display,
        "reference_range": ref_text,
        "out_of_range": out_of_range,
        "effective_date": raw.get("effectiveDateTime"),
        "status": raw.get("status"),
        "category": _observation_category(raw),
    }


def _split_observations(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    labs: List[Dict[str, Any]] = []
    vitals: List[Dict[str, Any]] = []
    social_history: List[Dict[str, Any]] = []
    other: List[Dict[str, Any]] = []

    for row in rows:
        raw = _parse_raw(row.get("raw_resource"))
        entry = _extract_observation_entry(raw)
        if not entry.get("name"):
            continue
        category = entry.pop("category", "other")
        if category == "laboratory":
            labs.append(entry)
        elif category == "vital-signs":
            vitals.append(entry)
        elif category == "social-history":
            social_history.append(entry)
        else:
            other.append(entry)

    return {
        "laboratory_results": labs[:_MAX_LIST_ITEMS],
        "vital_signs": vitals[:_MAX_LIST_ITEMS],
        "social_history": social_history[:_MAX_LIST_ITEMS],
        "other_observations": other[:_MAX_LIST_ITEMS],
    }


def _extract_encounters(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        raw = _parse_raw(row.get("raw_resource"))
        encounter_type = (
            _safe_get_display(raw, ["type", 0, "text"], ["type", 0, "coding", 0, "display"])
            or _safe_get_display(raw, ["class", "display"], ["class", "code"])
        )
        items.append(
            {
                "type": encounter_type,
                "status": raw.get("status"),
                "class": _safe_get_display(raw, ["class", "display"], ["class", "code"]),
                "start_date": raw.get("period", {}).get("start"),
                "end_date": raw.get("period", {}).get("end"),
            }
        )
    return [item for item in items if any(item.values())][: _MAX_LIST_ITEMS]


def _collect_clinical_dates(structured: Dict[str, Any]) -> List[date]:
    dates: List[date] = []

    def add(value: Optional[str]) -> None:
        parsed = _parse_date(value)
        if parsed:
            dates.append(parsed)

    for condition in structured.get("conditions") or []:
        add(condition.get("onset_date"))
        add(condition.get("resolution_date"))
    for allergy in structured.get("allergies") or []:
        add(allergy.get("onset_date") if isinstance(allergy, dict) else None)
    for med in structured.get("medications") or []:
        add(med.get("start_date"))
        add(med.get("end_date"))
    for section in ("laboratory_results", "vital_signs", "social_history", "other_observations"):
        for obs in structured.get(section) or []:
            add(obs.get("effective_date"))
    for immunization in structured.get("immunizations") or []:
        add(immunization.get("date"))
    for procedure in structured.get("procedures") or []:
        add(procedure.get("date"))
    for encounter in structured.get("encounters") or []:
        add(encounter.get("start_date"))
        add(encounter.get("end_date"))

    return dates


def _build_data_recency(structured: Dict[str, Any]) -> Dict[str, Any]:
    dates = _collect_clinical_dates(structured)
    if not dates:
        return {
            "most_recent_clinical_date": None,
            "recency_note": "No dated clinical events were found in the export.",
        }

    most_recent = max(dates)
    age = (structured.get("demographics") or {}).get("age_years")
    years_old = (date.today() - most_recent).days / 365.25
    note = f"Most recent clinical date in the record is {most_recent.isoformat()}."
    if years_old >= 2:
        note += (
            f" This is approximately {years_old:.1f} years old relative to today, "
            "which may affect trial eligibility that depends on current disease status."
        )
    elif age is not None and years_old >= 1:
        note += " Some clinical categories may not reflect the patient's current status."

    return {
        "most_recent_clinical_date": most_recent.isoformat(),
        "days_since_most_recent": (date.today() - most_recent).days,
        "recency_note": note,
    }


def build_structured_json_from_export(
    export_data: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Build a deduplicated structured clinical profile from exported Fasten rows."""
    deduped_data, quality_issues, duplicate_count = deduplicate_export_data(export_data)

    patient_rows = deduped_data.get("fastenhealth_patient") or []
    medication_rows: List[Dict[str, Any]] = []
    for table_name in (
        "fastenhealth_medicationorder",
        "fastenhealth_medicationrequest",
        "fastenhealth_medicationstatement",
        "fastenhealth_medicationdispense",
    ):
        medication_rows.extend(deduped_data.get(table_name) or [])

    observation_split = _split_observations(deduped_data.get("fastenhealth_observation") or [])

    structured: Dict[str, Any] = {
        "demographics": _extract_demographics(patient_rows),
        "conditions": _extract_conditions(deduped_data.get("fastenhealth_condition") or []),
        "allergies": _extract_allergies(deduped_data.get("fastenhealth_allergyintolerance") or []),
        "medications": _extract_medications(medication_rows),
        "immunizations": _extract_immunizations(deduped_data.get("fastenhealth_immunization") or []),
        "procedures": _extract_procedures(deduped_data.get("fastenhealth_procedure") or []),
        "encounters": _extract_encounters(deduped_data.get("fastenhealth_encounter") or []),
        **observation_split,
    }

    if duplicate_count:
        quality_issues.append(
            f"Removed {duplicate_count} duplicate resource row(s) repeated across connections."
        )
    structured["data_quality_issues"] = quality_issues
    structured["data_recency"] = _build_data_recency(structured)
    structured["deduplication"] = {
        "duplicate_rows_removed": duplicate_count,
        "tables_in_source": sorted(export_data.keys()),
        "tables_after_deduplication": sorted(deduped_data.keys()),
    }
    return structured


def _openai_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return key


def _call_openai_text(system_prompt: str, user_content: str, *, max_tokens: int = _SUMMARY_MAX_TOKENS) -> str:
    import requests

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {_openai_api_key()}",
            "Content-Type": "application/json",
        },
        json={
            "model": _OPENAI_MODEL,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        },
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    try:
        from ..services.ai_common.usage_emitter import emit_llm_usage

        emit_llm_usage(
            product="trial_match",
            feature="trial_match.ehr_ingest",
            provider="openai",
            model=_OPENAI_MODEL,
            usage=payload.get("usage") or {},
            source_service="hekma-core",
        )
    except Exception:
        logger.debug("AI usage emit skipped", exc_info=True)
    return payload["choices"][0]["message"]["content"].strip()


def _call_openai_json(system_prompt: str, user_content: str) -> Dict[str, Any]:
    text = _call_openai_text(system_prompt, user_content, max_tokens=300)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _rule_based_disease_list(structured_json: Dict[str, Any]) -> List[str]:
    """
    Return confirmed condition names for trial matching.

    Includes active and unknown/unspecified conditions. Resolved-only names are
    appended after active ones so eligibility filters still see history.
    """
    active_or_unknown: List[str] = []
    resolved_only: List[str] = []
    seen: set[str] = set()

    for condition in structured_json.get("conditions") or []:
        if not isinstance(condition, dict):
            continue
        name = _clean_condition_name(str(condition.get("name") or "").strip())
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        status = str(condition.get("clinical_status") or "").lower()
        if status in _RESOLVED_CONDITION_CODES:
            resolved_only.append(name)
        else:
            # active / unknown / recurrence / relapse
            active_or_unknown.append(name)

    return active_or_unknown + resolved_only


def _rule_based_summary_text(structured_json: Dict[str, Any]) -> str:
    """Build a trial-screening paragraph without LLM."""
    parts: List[str] = []
    demo = structured_json.get("demographics") or {}
    demo_bits: List[str] = []
    if demo.get("name"):
        demo_bits.append(str(demo["name"]))
    if demo.get("sex"):
        demo_bits.append(str(demo["sex"]))
    if demo.get("birth_date"):
        demo_bits.append(f"DOB {demo['birth_date']}")
    if demo.get("age_years") is not None:
        demo_bits.append(f"age {demo['age_years']}")
    if demo.get("location"):
        demo_bits.append(f"location {demo['location']}")
    if demo_bits:
        parts.append("Demographics: " + ", ".join(demo_bits) + ".")

    active = [
        c for c in (structured_json.get("conditions") or [])
        if isinstance(c, dict)
        and str(c.get("clinical_status") or "").lower() in _ACTIVE_CONDITION_CODES.union({"unknown", ""})
    ]
    resolved = [
        c for c in (structured_json.get("conditions") or [])
        if isinstance(c, dict) and str(c.get("clinical_status") or "").lower() in _RESOLVED_CONDITION_CODES
    ]
    if active:
        active_bits = []
        for c in active[:12]:
            if not c.get("name"):
                continue
            bit = str(c["name"])
            if c.get("onset_date"):
                bit += f" (onset {str(c['onset_date'])[:10]})"
            elif c.get("onset_age_years") is not None:
                bit += f" (onset age {c['onset_age_years']})"
            active_bits.append(bit)
        if active_bits:
            parts.append("Active conditions include " + ", ".join(active_bits) + ".")
    if resolved:
        resolved_bits = []
        for c in resolved[:8]:
            if not c.get("name"):
                continue
            bit = str(c["name"])
            if c.get("resolution_date"):
                bit += f" (resolved {str(c['resolution_date'])[:10]})"
            resolved_bits.append(bit)
        if resolved_bits:
            parts.append("Resolved conditions include " + ", ".join(resolved_bits) + ".")

    allergies = structured_json.get("allergies") or []
    if allergies:
        allergy_text = ", ".join(
            f"{a.get('substance')} ({a.get('criticality') or a.get('severity') or 'unspecified severity'})"
            for a in allergies[:8]
            if isinstance(a, dict) and a.get("substance")
        )
        if allergy_text:
            parts.append(f"Allergies/intolerances include {allergy_text}.")

    meds = structured_json.get("medications") or []
    if meds:
        med_text = ", ".join(
            f"{m.get('name')} {m.get('dose') or ''} {m.get('route') or ''}".strip()
            for m in meds[:12]
            if isinstance(m, dict) and m.get("name")
        )
        parts.append(f"Medications include {med_text}.")

    labs = structured_json.get("laboratory_results") or []
    if labs:
        lab_text = ", ".join(
            f"{l.get('name')} {l.get('value')}"
            + (f" (ref {l.get('reference_range')}, {l.get('out_of_range')} )" if l.get("out_of_range") else "")
            for l in labs[:10]
            if isinstance(l, dict) and l.get("name")
        )
        parts.append(f"Laboratory results include {lab_text}.")

    vitals = structured_json.get("vital_signs") or []
    if vitals:
        parts.append(
            "Vital signs include "
            + ", ".join(f"{v.get('name')} {v.get('value')}" for v in vitals[:8] if v.get("name"))
            + "."
        )

    social = structured_json.get("social_history") or []
    if social:
        parts.append(
            "Social history includes "
            + ", ".join(f"{s.get('name')} {s.get('value')}" for s in social[:5] if s.get("name"))
            + "."
        )

    encounters = structured_json.get("encounters") or []
    if encounters:
        parts.append(
            "Encounter history includes "
            + ", ".join(
                f"{e.get('type') or e.get('class')} ({e.get('start_date')})"
                for e in encounters[:8]
                if isinstance(e, dict)
            )
            + "."
        )

    recency = structured_json.get("data_recency") or {}
    if recency.get("recency_note"):
        parts.append(str(recency["recency_note"]))

    quality = structured_json.get("data_quality_issues") or []
    if quality:
        parts.append("Data quality notes: " + "; ".join(str(item) for item in quality[:5]) + ".")

    return " ".join(parts).strip()


def generate_trial_patient_summary(
    export_data: Dict[str, List[Dict[str, Any]]],
    *,
    use_llm: bool = True,
    include_disease_llm: bool = False,
) -> TrialPatientSummary:
    """
    Build trial-matching summary fields from exported Fasten table data.

    Falls back to rule-based text when LLM is disabled or unavailable.
    """
    structured_json = build_structured_json_from_export(export_data)
    deduped_data, _, _ = deduplicate_export_data(export_data)
    llm_payload = {
        "data": _strip_metadata_from_data(deduped_data),
        "data_quality_issues": structured_json.get("data_quality_issues") or [],
        "data_recency": structured_json.get("data_recency") or {},
    }
    llm_enabled = use_llm and not _SKIP_AI

    if llm_enabled:
        try:
            summary_text = _call_openai_text(
                _TRIAL_SUMMARY_SYSTEM_PROMPT,
                json.dumps(llm_payload, ensure_ascii=False, default=str),
            )
            generated_by = "openai"
            model = _OPENAI_MODEL
        except Exception as exc:
            logger.warning("Trial summary LLM failed, using rule-based fallback: %s", exc)
            summary_text = _rule_based_summary_text(structured_json)
            generated_by = "rule_based"
            model = None
    else:
        summary_text = _rule_based_summary_text(structured_json)
        generated_by = "rule_based"
        model = None

    disease_list = _rule_based_disease_list(structured_json)
    if include_disease_llm and llm_enabled and summary_text:
        try:
            parsed = _call_openai_json(
                _DISEASE_LIST_SYSTEM_PROMPT,
                json.dumps(
                    {
                        "summary_text": summary_text,
                        "structured_json": structured_json,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )
            llm_diseases = parsed.get("disease_list") or []
            if isinstance(llm_diseases, list) and llm_diseases:
                disease_list = [str(item).strip() for item in llm_diseases if str(item).strip()]
                generated_by = "openai"
        except Exception as exc:
            logger.warning("Disease list LLM failed, using rule-based list: %s", exc)

    return TrialPatientSummary(
        summary_text=summary_text,
        structured_json=structured_json,
        disease_list=disease_list,
        generated_by=generated_by,
        model=model,
    )
