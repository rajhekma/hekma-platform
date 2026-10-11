"""
EHR Summary HTML Renderer
=========================
Converts an EHRSummaryResponse into a print-ready A4 HTML document styled
to match the clinical summary reference design.

The HTML uses:
  - Tailwind CSS (CDN)          — layout and typography
  - Google Fonts (Inter)        — body font
  - Material Symbols Outlined   — icons
  - @media print CSS            — hides UI chrome, preserves page breaks

Open the returned HTML in any browser and use
  File → Print → Save as PDF
to produce the final PDF.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from ..schemas.ehr_summary_schemas import EHRSummaryResponse, TimelineEvent

HEKMA_LOGO_URL = (
    "https://dev.hekma.ai/static/media/hekma-logo.dbf615e60a555519376dd75780f1f4e2.svg"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Matches SKIP_AI placeholder summaries — never show these to the user
_SKIP_AI_RE = re.compile(
    r"(summary unavailable|record imported on \d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
# Wrong patient name strings present in test FHIR data
_PATIENT_NAME_NOISE_RE = re.compile(
    r"\b(Test,?\s*APIPatient|Camila\s+Maria\s+Lopez|APIPatient)\b",
    re.IGNORECASE,
)


def _clean_summary(text: str) -> str:
    """Return None-safe summary with SKIP_AI placeholders and wrong names removed."""
    if not text:
        return ""
    if _SKIP_AI_RE.search(text):
        return ""
    return _PATIENT_NAME_NOISE_RE.sub("Patient", text)


def _esc(text: Any) -> str:
    return html.escape(str(text or ""))


def _trunc(text: Any, n: int) -> str:
    """Truncate at word boundary with ellipsis."""
    s = str(text or "").strip()
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return cut + "…"


def _fmt_date(raw: Optional[str]) -> str:
    if not raw:
        return "NA"
    try:
        d = date.fromisoformat(raw[:10])
        return d.strftime("%b %d, %Y")
    except Exception:
        return str(raw)[:10] if raw else "NA"


def _clinical_overview_text(summary: Optional[str]) -> str:
    """Return clinical overview without the leading demographics sentence."""
    text = _clean_summary(summary or "")
    if not text:
        return ""
    first, _, rest = text.partition(". ")
    if "year-old" in first.lower() or re.search(r"\bis a \d+", first, re.I):
        return rest.strip() or text
    return text


_ACTIVE_DIAGNOSIS_STATUSES = {"active", "recurrence", "relapse"}


def _extract_active_diagnoses(events: List[TimelineEvent]) -> List[str]:
    names: List[str] = []
    seen: set = set()
    for e in sorted(events, key=lambda x: x.date or "", reverse=True):
        rec = e.original_record or {}
        if _fhir_verification_status(rec) == "entered-in-error":
            continue
        if _fhir_clinical_status(rec) not in _ACTIVE_DIAGNOSIS_STATUSES:
            continue
        name = _fhir_code_text(rec)
        if not name or name.lower() in ("null", "not on file"):
            m = re.search(r"diagnosis of ([^,\.]+)", e.summary or "", re.I)
            name = m.group(1).strip() if m else ""
        key = name.lower().strip()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return names[:8]


def _extract_active_medications(events: List[TimelineEvent]) -> List[str]:
    med_lookup = _build_medication_name_lookup(events)
    names: List[str] = []
    seen: set = set()
    for e in sorted(events, key=lambda x: x.date or "", reverse=True):
        if not _is_active_medication_event(e):
            continue
        name = _resolve_medication_name(e, med_lookup)
        key = name.lower().strip()
        if not name or key in seen:
            continue
        seen.add(key)
        rec = e.original_record or {}
        dosage = ""
        di = rec.get("dosageInstruction") or []
        if di:
            dosage = (di[0].get("text") or "").strip()
        label = f"{name} ({dosage})" if dosage else name
        names.append(label)
    return names[:8]


def _extract_allergens(events: List[TimelineEvent]) -> List[str]:
    names: List[str] = []
    seen: set = set()
    for e in events:
        rec = e.original_record or {}
        substance = _fhir_allergy_substance(rec) or _fhir_code_text(rec)
        if not substance or substance.lower() in _ALLERGY_NOISE:
            continue
        key = substance.lower().strip()
        if key not in seen:
            seen.add(key)
            names.append(substance)
    return names[:8]


def _format_overview_paragraphs(text: str) -> str:
    """Render overview narrative as readable paragraphs."""
    text = text.strip()
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: List[str] = []
    buf: List[str] = []
    for i, sentence in enumerate(sentences):
        if not sentence.strip():
            continue
        buf.append(sentence.strip())
        if len(buf) >= 2 or i == len(sentences) - 1:
            chunks.append(" ".join(buf))
            buf = []
    if not chunks:
        chunks = [text]
    return "".join(
        f'<p style="font-size:13px;color:#1a1c1d;line-height:1.65;margin-bottom:10px;">{_esc(p)}</p>'
        for p in chunks
    )


def _render_rule_based_overview_narrative(timeline: List[TimelineEvent]) -> str:
    """Prose fallback when AI patient.summary is unavailable (no bullet lists)."""
    diagnoses = _extract_active_diagnoses(_events_for(timeline, "Diagnoses"))
    medications = _extract_active_medications(_events_for(timeline, "Medications"))
    allergies = _extract_allergens(_events_for(timeline, "Allergies"))
    enc_count = len(_events_for(timeline, "Encounters / Visits"))
    hosp_count = len(_events_for(timeline, "Hospitalizations"))
    labs_all = _events_for(timeline, "Laboratory Results")
    labs, vitals_from_labs = _split_lab_and_vital_events(labs_all)
    vitals_count = len(_events_for(timeline, "Vital Signs")) + len(vitals_from_labs)
    lab_count = len(labs)
    imaging_count = len(_events_for(timeline, "Imaging & Radiology"))

    parts: List[str] = []
    if diagnoses:
        parts.append(
            f"Active medical problems include {', '.join(diagnoses[:5])}."
        )
    if medications:
        med_names = [m.split(" (")[0] for m in medications[:5]]
        parts.append(
            f"Current medications include {', '.join(med_names)}."
        )
    if allergies:
        parts.append(
            f"Documented allergies and intolerances include {', '.join(allergies[:6])}."
        )
    elif timeline:
        parts.append("No known allergies are documented in the available records.")

    care_bits: List[str] = []
    if enc_count:
        care_bits.append(
            f"{enc_count} outpatient visit{'s' if enc_count != 1 else ''}"
        )
    if hosp_count:
        care_bits.append(
            f"{hosp_count} hospitalization record{'s' if hosp_count != 1 else ''}"
        )
    if care_bits:
        parts.append(
            f"Care utilization on file includes {' and '.join(care_bits)}."
        )

    diag_bits: List[str] = []
    if lab_count:
        diag_bits.append(f"{lab_count} laboratory result{'s' if lab_count != 1 else ''}")
    if vitals_count:
        diag_bits.append(f"{vitals_count} vital sign{'s' if vitals_count != 1 else ''}")
    if imaging_count:
        diag_bits.append(
            f"{imaging_count} imaging or radiology report{'s' if imaging_count != 1 else ''}"
        )
    if diag_bits:
        parts.append(
            f"Diagnostic records include {' and '.join(diag_bits)}."
        )

    if not parts:
        return ""
    return _format_overview_paragraphs(" ".join(parts))


def _render_clinical_overview(timeline: List[TimelineEvent], ai_summary: Optional[str] = None) -> str:
    """
    Clinical Overview — AI narrative from patient.summary (cached at generation time).
    Falls back to rule-based prose if AI summary is missing.
    Detailed lists appear in the dedicated sections below this overview.
    """
    narrative = _clinical_overview_text(ai_summary)
    if narrative:
        return _format_overview_paragraphs(narrative)
    return _render_rule_based_overview_narrative(timeline)


def _events_for(timeline: List[TimelineEvent], category: str) -> List[TimelineEvent]:
    return [e for e in timeline if e.category == category]


def _year_range(timeline: List[TimelineEvent], patient_dob: Optional[str] = None) -> tuple[str, str]:
    """Use only patient-relevant years (exclude practitioner/admin records)."""
    skip_cats = {"Other Health Events"}
    dates = [
        e.date[:4] for e in timeline
        if e.date and len(e.date) >= 4 and e.category not in skip_cats
    ]
    if not dates:
        # fallback: use patient DOB year as start
        if patient_dob and len(patient_dob) >= 4:
            return patient_dob[:4], str(datetime.now().year)
        return str(datetime.now().year - 10), str(datetime.now().year)
    return min(dates), str(datetime.now().year)


def _timeline_years(start_y: str, end_y: str) -> List[str]:
    """Return 6 evenly spaced year labels between start and end."""
    try:
        sy, ey = int(start_y), int(end_y)
        span = max(ey - sy, 1)
        step = max(span // 5, 1)
        years = [str(sy + i * step) for i in range(6)]
        years[-1] = str(ey)
        return years
    except Exception:
        return [start_y, end_y]


# ---------------------------------------------------------------------------
# FHIR original_record extractors
# ---------------------------------------------------------------------------

def _fhir_code_text(rec: Optional[Dict[str, Any]]) -> str:
    """Extract human-readable name from FHIR CodeableConcept.code or direct CodeableConcept."""
    if not rec:
        return ""
    # Support direct CodeableConcept (e.g. valueCodeableConcept, component.code)
    if "text" in rec or "coding" in rec:
        code = rec
    else:
        code = rec.get("code") or {}
    text = code.get("text") or ""
    if text and text.lower() != "null":
        return text
    codings = code.get("coding") or []
    for c in codings:
        display = c.get("display") or c.get("code") or ""
        if display and display.lower() != "null":
            return display
    return ""


def _fhir_clinical_status(rec: Optional[Dict[str, Any]]) -> str:
    """Extract clinical status code from FHIR Condition.clinicalStatus."""
    if not rec:
        return "unknown"
    cs = rec.get("clinicalStatus") or {}
    for c in (cs.get("coding") or []):
        code = (c.get("code") or "").lower()
        if code:
            return code
    return (cs.get("text") or "unknown").lower()


def _fhir_verification_status(rec: Optional[Dict[str, Any]]) -> str:
    """Extract verification status code from FHIR Condition.verificationStatus."""
    if not rec:
        return ""
    vs = rec.get("verificationStatus") or {}
    for c in (vs.get("coding") or []):
        code = (c.get("code") or "").lower()
        if code:
            return code
    return (vs.get("text") or "").lower()


def _fhir_medication_name(rec: Optional[Dict[str, Any]]) -> str:
    """Extract medication name from MedicationRequest/Medication original_record."""
    if not rec:
        return ""
    # medicationCodeableConcept (R4)
    med_cc = rec.get("medicationCodeableConcept") or {}
    name = med_cc.get("text") or ""
    if not name:
        for c in med_cc.get("coding") or []:
            name = c.get("display") or c.get("code") or ""
            if name:
                break
    # medicationReference.display (often populated for external references)
    if not name:
        name = ((rec.get("medicationReference") or {}).get("display") or "")
    # FHIR R5 medication.concept
    if not name:
        concept = (rec.get("medication") or {}).get("concept") or {}
        name = concept.get("text") or ""
        if not name:
            for c in concept.get("coding") or []:
                name = c.get("display") or c.get("code") or ""
                if name:
                    break
    # Medication resource itself (resourceType == Medication) — code field
    if not name and rec.get("resourceType") == "Medication":
        name = _fhir_code_text(rec)
    if not name:
        try:
            from ..services.clinical_fhir.identity import read_ctms_payload

            stamped = read_ctms_payload(rec)
            name = str(stamped.get("name") or stamped.get("medicationName") or "")
        except Exception:
            pass
    return name


_MEDICATION_RX_TYPES = {
    "medicationrequest", "medicationstatement", "medicationorder", "medicationdispense",
}
_INACTIVE_MED_STATUSES = {
    "stopped", "completed", "cancelled", "entered-in-error", "inactive",
    "not-taken", "on-hold", "intended", "draft", "unknown",
}


def _medication_resource_type(event: TimelineEvent) -> str:
    rec = event.original_record or {}
    rt = rec.get("resourceType") or event.resource_type or ""
    if rt:
        return rt.replace(" ", "").lower()
    table = (event.source_table or "").replace("fastenhealth_", "").lower()
    return table


def _medication_status_from_summary(summary: str) -> str:
    if not summary:
        return ""
    paren = re.search(r"\((active|stopped|completed|cancelled|on-hold|not-taken)\)", summary, re.I)
    if paren:
        return paren.group(1).lower()
    word = re.search(
        r"\b(status\s+)?(active|stopped|completed|cancelled|on-hold|not-taken)\b",
        summary, re.I,
    )
    return word.group(2).lower() if word else ""


def _medication_event_status(event: TimelineEvent) -> str:
    rec = event.original_record or {}
    status = (rec.get("status") or "").strip().lower()
    if status:
        return status
    return _medication_status_from_summary(event.summary or "")


def _is_prescription_medication_event(event: TimelineEvent) -> bool:
    rt = _medication_resource_type(event)
    if rt == "medication":
        return False
    if rt in _MEDICATION_RX_TYPES:
        return True
    return event.category == "Medications"


def _is_active_medication_event(event: TimelineEvent) -> bool:
    if not _is_prescription_medication_event(event):
        return False
    status = _medication_event_status(event)
    if status in _INACTIVE_MED_STATUSES:
        return False
    if status == "active":
        return True
    # No FHIR status — trust summary only when it explicitly says active
    if not status and re.search(r"\(active\)", event.summary or "", re.I):
        return True
    return False


def _build_medication_name_lookup(events: List[TimelineEvent]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for e in events:
        rec = e.original_record or {}
        if rec.get("resourceType") != "Medication":
            continue
        rid = rec.get("id") or ""
        name = _fhir_code_text(rec) or _fhir_medication_name(rec)
        if rid and name:
            lookup[f"Medication/{rid}"] = name
    return lookup


def _resolve_medication_name(
    event: TimelineEvent,
    med_lookup: Dict[str, str],
) -> str:
    rec = event.original_record or {}
    name = _fhir_medication_name(rec)
    if not name:
        ref = (rec.get("medicationReference") or {}).get("reference") or ""
        name = med_lookup.get(ref, "")
    if not name:
        m = re.search(
            r"(?:Medication|request for|medication[:\s]+)\s*([^,\.(]+)",
            event.summary or "",
            re.I,
        )
        if m:
            name = m.group(1).strip()
    return name


_ALLERGY_NOISE = {
    "allergy to substance (finding)", "patient not asked",
    "not on file", "allergy to substance", "no known allergy",
}


def _fhir_allergy_substance(rec: Optional[Dict[str, Any]]) -> str:
    """Extract allergen substance name from AllergyIntolerance original_record."""
    if not rec:
        return ""
    code = rec.get("code") or {}
    name = code.get("text") or ""
    if not name:
        for c in code.get("coding") or []:
            name = c.get("display") or c.get("code") or ""
            if name:
                break
    # Filter noise entries
    if name.lower() in _ALLERGY_NOISE:
        return ""
    # Try reaction substance as fallback
    if not name:
        for rxn in rec.get("reaction") or []:
            subst = rxn.get("substance") or {}
            name = subst.get("text") or ""
            if not name:
                for c in subst.get("coding") or []:
                    name = c.get("display") or c.get("code") or ""
                    if name:
                        break
            if name and name.lower() not in _ALLERGY_NOISE:
                break
            name = ""
    return name


def _fhir_allergy_category(rec: Optional[Dict[str, Any]]) -> str:
    """Return allergy category label: Food / Environmental / Drug / Other."""
    if not rec:
        return "Allergy"
    categories = rec.get("category") or []
    if isinstance(categories, list) and categories:
        cat = categories[0].lower()
        return {"food": "Food", "environment": "Environmental",
                "medication": "Drug", "biologic": "Biologic"}.get(cat, cat.title())
    return "Allergy"


def _fhir_allergy_severity(rec: Optional[Dict[str, Any]]) -> str:
    """Extract criticality/severity from AllergyIntolerance."""
    if not rec:
        return ""
    crit = rec.get("criticality") or ""
    if crit:
        return crit.upper().replace("-", " ")
    for rxn in rec.get("reaction") or []:
        sev = rxn.get("severity") or ""
        if sev:
            return sev.upper()
    return ""


def _fhir_allergy_reactions(rec: Optional[Dict[str, Any]]) -> str:
    """Extract reaction manifestation names (comma-separated)."""
    if not rec:
        return ""
    results = []
    for rxn in rec.get("reaction") or []:
        for mani in rxn.get("manifestation") or []:
            # FHIR R4: manifestation is CodeableConcept
            if isinstance(mani, dict):
                text = mani.get("text") or ""
                if not text:
                    for c in mani.get("coding") or []:
                        text = c.get("display") or ""
                        if text:
                            break
                if text:
                    results.append(text)
            # FHIR R5: manifestation is { concept: CodeableConcept }
            elif isinstance(mani, dict) and "concept" in mani:
                concept = mani["concept"]
                text = concept.get("text") or ""
                if text:
                    results.append(text)
    return ", ".join(results[:3])


_VITAL_NAME_HINTS = (
    "blood pressure",
    "systolic",
    "diastolic",
    "heart rate",
    "pulse",
    "temperature",
    "spo2",
    "oxygen saturation",
    "respiratory rate",
    "body weight",
    "body height",
    "bmi",
    "body mass index",
)


_SOCIAL_HISTORY_HINTS = (
    "tobacco",
    "smoking",
    "cigarette",
    "cigar",
    "nicotine",
    "pack years",
    "alcohol",
    "drinking",
    "substance",
    "illicit drug",
    "occupation",
    "employment",
    "social history",
)

_SURVEY_ASSESSMENT_HINTS = (
    "phq",
    "gad-7",
    "gad7",
    "depression",
    "anxiety",
    "audit-c",
    "audit c",
    "pain scale",
    "pain score",
    "pain severity",
    "fall risk",
    "morse fall",
    "functional assessment",
    "activities of daily living",
    "adl",
)


def _fhir_obs_component_value(rec: Dict[str, Any]) -> str:
    """Format Observation.component (e.g. systolic/diastolic BP) as '120 / 80 mmHg'."""
    parts: List[str] = []
    unit = ""
    for item in rec.get("component") or []:
        if not isinstance(item, dict):
            continue
        qty = item.get("valueQuantity") or {}
        val = qty.get("value")
        if val is not None and str(val) != "":
            parts.append(str(val))
            unit = unit or str(qty.get("unit") or qty.get("code") or "")
        else:
            comp_txt = str(item.get("valueString") or "").strip()
            if not comp_txt:
                comp_txt = _fhir_code_text(item.get("valueCodeableConcept"))
            if comp_txt:
                parts.append(comp_txt)
    if len(parts) >= 2:
        return f"{parts[0]} / {parts[1]} {unit}".strip()
    if parts:
        return f"{parts[0]} {unit}".strip()
    return ""


def _fhir_obs_name_value(rec: Optional[Dict[str, Any]]) -> tuple[str, str]:
    """Extract observation test name and value from Observation original_record."""
    if not rec:
        return "", ""
    name = _fhir_code_text(rec)
    vq = rec.get("valueQuantity") or {}
    val = ""
    if vq:
        num = vq.get("value")
        unit = vq.get("unit") or vq.get("code") or ""
        # Check for Fahrenheit extension in temperature
        f_val = None
        for ext in rec.get("extension") or []:
            if "temperature-in-fahrenheit" in str(ext.get("url") or ""):
                f_vq = ext.get("valueQuantity") or {}
                f_val = f_vq.get("value")
                break
        if f_val is not None and (unit.lower() in ("cel", "c", "degc") or "temp" in name.lower()):
            val = f"{f_val} °F ({num} °C)"
        elif num is not None and str(num) != "":
            clean_u = "°C" if unit == "Cel" else ("°F" if unit == "[degF]" else unit)
            if not clean_u and "a1c" in name.lower():
                clean_u = "%"
            val = f"{num} {clean_u}".strip()
    if not val:
        val = str(rec.get("valueString") or "").strip()
    if not val:
        val = _fhir_code_text(rec.get("valueCodeableConcept"))
    if not val and "valueBoolean" in rec and rec["valueBoolean"] is not None:
        val = "Yes" if rec["valueBoolean"] else "No"
    if not val:
        val = _fhir_obs_component_value(rec)
    return name, val


def _fhir_obs_reference_range(rec: Optional[Dict[str, Any]]) -> str:
    if not rec:
        return ""
    for ref in rec.get("referenceRange") or []:
        if not isinstance(ref, dict):
            continue
        text = (ref.get("text") or "").strip()
        if text:
            return text
        low_obj = ref.get("low") or {}
        high_obj = ref.get("high") or {}
        low = low_obj.get("value")
        high = high_obj.get("value")
        unit = (
            low_obj.get("unit")
            or high_obj.get("unit")
            or ref.get("unit")
            or (rec.get("valueQuantity") or {}).get("unit")
            or ""
        )
        if low is not None and high is not None:
            return f"{low} – {high} {unit}".strip()
        if low is not None:
            return f"> {low} {unit}".strip()
        if high is not None:
            return f"< {high} {unit}".strip()
    return ""


def _fhir_obs_interpretation(
    rec: Optional[Dict[str, Any]],
    val_str: Optional[str] = None,
) -> tuple[str, str]:
    """Return (label, badge_css_class) for observation interpretation / out-of-range flag."""
    if not rec:
        return "", ""

    interpretations = list(rec.get("interpretation") or [])
    for comp in rec.get("component") or []:
        if isinstance(comp, dict):
            interpretations.extend(comp.get("interpretation") or [])

    for interp in interpretations:
        if not isinstance(interp, dict):
            continue
        text = (interp.get("text") or "").strip()
        code = ""
        for c in interp.get("coding") or []:
            if isinstance(c, dict) and c.get("code"):
                code = str(c["code"]).upper().strip()
                break
        if not code and text:
            code = text.upper()

        if code in ("H", "HH", "HU", "HIGH", "CRITICAL HIGH"):
            label = "Critical High" if code in ("HH", "CRITICAL HIGH") else "High"
            return label, "bg-red-100 text-red-800"
        if code in ("L", "LL", "LU", "LOW", "CRITICAL LOW"):
            label = "Critical Low" if code in ("LL", "CRITICAL LOW") else "Low"
            return label, "bg-blue-100 text-blue-800"
        if code in ("A", "AA", "ABNORMAL", "CRITICAL ABNORMAL"):
            return "Abnormal", "bg-orange-100 text-orange-800"
        if code in ("POS", "POSITIVE", "DET", "DETECTED"):
            return "Positive", "bg-red-100 text-red-800"
        if code in ("NEG", "NEGATIVE", "ND", "NOT DETECTED"):
            return "Negative", "bg-green-100 text-green-800"
        if code in ("N", "NORMAL", "NORM"):
            return "Normal", "bg-green-50 text-green-700"

    # Numeric fallback vs referenceRange bounds
    if val_str:
        try:
            m = re.search(r"^([-+]?[0-9]*\.?[0-9]+)", val_str.strip())
            if m:
                num = float(m.group(1))
                for ref in rec.get("referenceRange") or []:
                    if not isinstance(ref, dict):
                        continue
                    low = (ref.get("low") or {}).get("value")
                    high = (ref.get("high") or {}).get("value")
                    if high is not None and num > float(high):
                        return "High", "bg-red-100 text-red-800"
                    if low is not None and num < float(low):
                        return "Low", "bg-blue-100 text-blue-800"
                    if low is not None and high is not None and float(low) <= num <= float(high):
                        return "Normal", "bg-green-50 text-green-700"
        except (ValueError, TypeError):
            pass

    return "", ""


def _fhir_obs_note(rec: Optional[Dict[str, Any]]) -> str:
    if not rec:
        return ""
    notes = []
    for n in rec.get("note") or []:
        if isinstance(n, dict) and n.get("text"):
            notes.append(str(n["text"]).strip())
        elif isinstance(n, str) and n.strip():
            notes.append(n.strip())
    return " · ".join(notes)


def _fhir_obs_performer(rec: Optional[Dict[str, Any]]) -> str:
    if not rec:
        return ""
    for p in rec.get("performer") or []:
        if isinstance(p, dict) and p.get("display"):
            return str(p["display"]).strip()
    return ""


def _observation_is_vital(rec: Optional[Dict[str, Any]]) -> bool:
    """True when an Observation FHIR resource is a vital sign, not a lab."""
    if not rec:
        return False
    for cat in rec.get("category") or []:
        if isinstance(cat, str) and "vital" in cat.lower():
            return True
        if not isinstance(cat, dict):
            continue
        for coding in cat.get("coding") or []:
            if isinstance(coding, dict):
                code = str(coding.get("code") or "").strip().lower().replace("_", "-")
                if code in ("vital-signs", "vitals"):
                    return True
        if "vital" in str(cat.get("text") or "").lower():
            return True
    name = (_fhir_code_text(rec) or "").lower()
    return any(hint in name for hint in _VITAL_NAME_HINTS)


def _observation_is_social_history(rec: Optional[Dict[str, Any]]) -> bool:
    """True when an Observation FHIR resource is social history (smoking, alcohol, etc.)."""
    if not rec:
        return False
    for cat in rec.get("category") or []:
        if isinstance(cat, str) and "social" in cat.lower():
            return True
        if not isinstance(cat, dict):
            continue
        for coding in cat.get("coding") or []:
            if isinstance(coding, dict):
                code = str(coding.get("code") or "").strip().lower().replace("_", "-")
                if code in ("social-history", "socialhistory"):
                    return True
        if "social" in str(cat.get("text") or "").lower():
            return True
    name = (_fhir_code_text(rec) or "").lower()
    return any(hint in name for hint in _SOCIAL_HISTORY_HINTS)


def _observation_is_survey(rec: Optional[Dict[str, Any]]) -> bool:
    """True when an Observation FHIR resource is a survey/assessment screener."""
    if not rec:
        return False
    for cat in rec.get("category") or []:
        if isinstance(cat, str) and ("survey" in cat.lower() or "assessment" in cat.lower() or "screening" in cat.lower()):
            return True
        if not isinstance(cat, dict):
            continue
        for coding in cat.get("coding") or []:
            if isinstance(coding, dict):
                code = str(coding.get("code") or "").strip().lower().replace("_", "-")
                if code in ("survey", "assessment", "screening"):
                    return True
        text = str(cat.get("text") or "").lower()
        if "survey" in text or "assessment" in text or "screening" in text:
            return True
    name = (_fhir_code_text(rec) or "").lower()
    return any(hint in name for hint in _SURVEY_ASSESSMENT_HINTS)


def _partition_observation_events(
    events: List[TimelineEvent],
) -> tuple[List[TimelineEvent], List[TimelineEvent], List[TimelineEvent], List[TimelineEvent]]:
    """Partition observation events into (labs, vitals, social_history, surveys).
    Ensures backwards compatibility on cache hits where all were stored under Laboratory Results."""
    labs: List[TimelineEvent] = []
    vitals: List[TimelineEvent] = []
    social: List[TimelineEvent] = []
    surveys: List[TimelineEvent] = []

    for e in events:
        rec = e.original_record or {}
        if e.category == "Vital Signs" or _observation_is_vital(rec):
            vitals.append(e)
        elif e.category == "Social History" or _observation_is_social_history(rec):
            social.append(e)
        elif e.category in ("Clinical Assessments & Surveys", "Surveys") or _observation_is_survey(rec):
            surveys.append(e)
        else:
            labs.append(e)
    return labs, vitals, social, surveys


def _split_lab_and_vital_events(
    events: List[TimelineEvent],
) -> tuple[List[TimelineEvent], List[TimelineEvent]]:
    """Split cached Laboratory Results into labs vs vitals (cache HIT safety)."""
    labs, vitals, _, _ = _partition_observation_events(events)
    return labs, vitals


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_diagnoses(events: List[TimelineEvent]) -> str:
    if not events:
        return '<p class="font-body-sm text-body-sm text-on-surface-variant italic">No diagnosis records found.</p>'

    status_styles = {
        "active":     ("bg-secondary-container text-on-secondary-container", "Active"),
        "resolved":   ("bg-surface-container text-on-surface-variant",       "Resolved"),
        "inactive":   ("bg-surface-container text-on-surface-variant",       "Inactive"),
        "unknown":    ("bg-yellow-100 text-yellow-800",                      "Unknown"),
        "recurrence": ("bg-orange-100 text-orange-800",                      "Recurrence"),
        "relapse":    ("bg-orange-100 text-orange-800",                      "Relapse"),
        "remission":  ("bg-green-100 text-green-800",                        "Remission"),
        "refuted":    ("bg-gray-100 text-gray-500",                          "Refuted"),
    }

    # Sort newest first; filter entered-in-error; deduplicate on condition name
    sorted_events = sorted(
        events,
        key=lambda e: e.date or "0000",
        reverse=True,
    )

    seen, items = set(), []
    for e in sorted_events:
        rec = e.original_record or {}

        # Skip data entry errors entirely
        if _fhir_verification_status(rec) == "entered-in-error":
            continue

        name = _fhir_code_text(rec)
        # Fallback: pull from summary using "diagnosis of X" / "recorded as 'X'" patterns
        if not name or name.lower() in ("null", "not on file"):
            import re as _re
            m = (_re.search(r"diagnosis of ([^,\.]+)", e.summary, _re.I) or
                 _re.search(r"recorded as '([^']+)'", e.summary, _re.I))
            name = m.group(1).strip() if m else _trunc(e.summary, 55)

        key = name.lower().strip()
        if key in seen or not key:
            continue
        seen.add(key)

        clinical_status = _fhir_clinical_status(rec)
        badge_class, badge_label = status_styles.get(
            clinical_status, ("bg-yellow-100 text-yellow-800", clinical_status.title() or "Unknown")
        )

        items.append(f"""
        <li class="p-sm bg-surface-container-low border border-outline-variant flex justify-between items-start rounded gap-sm">
          <div class="flex-1">
            <p class="text-[13px] font-semibold text-on-surface">{_esc(name)}</p>
            <p class="text-[11px] text-on-surface-variant mt-xs">Condition · {_fmt_date(e.date)}</p>
          </div>
          <span class="{badge_class} px-sm py-1 rounded text-[10px] font-bold uppercase tracking-widest whitespace-nowrap">{badge_label}</span>
        </li>""")

    if not items:
        return '<p class="font-body-sm text-body-sm text-on-surface-variant italic">No diagnosis records found.</p>'
    return f'<ul class="space-y-sm">{"".join(items)}</ul>'


def _render_allergies(events: List[TimelineEvent]) -> str:
    if not events:
        return '<p class="font-body-sm text-body-sm text-on-surface-variant italic">No allergy records found.</p>'

    cat_colors = {
        "Food":          ("bg-orange-50 text-orange-700 border-orange-200", "bg-orange-100 text-orange-800"),
        "Environmental": ("bg-green-50 text-green-700 border-green-200",  "bg-green-100 text-green-800"),
        "Drug":          ("bg-red-50 text-red-700 border-red-200",         "bg-red-100 text-red-800"),
        "Biologic":      ("bg-purple-50 text-purple-700 border-purple-200","bg-purple-100 text-purple-800"),
    }
    default_color = ("bg-gray-50 text-gray-700 border-gray-200", "bg-gray-100 text-gray-800")

    seen, items = set(), []
    for e in events:
        rec = e.original_record or {}
        substance = _fhir_allergy_substance(rec)
        if not substance:
            continue
        key = substance.lower()
        if key in seen:
            continue
        seen.add(key)

        category  = _fhir_allergy_category(rec)
        reactions = _fhir_allergy_reactions(rec)
        border_color, badge_color = cat_colors.get(category, default_color)

        reaction_html = (
            f'<span class="text-[11px] text-on-surface-variant ml-sm">· {_esc(reactions)}</span>'
            if reactions else ""
        )
        items.append(f"""
        <div class="flex items-center justify-between p-sm border-b border-outline-variant last:border-0">
          <div class="flex items-center gap-xs flex-wrap">
            <span class="text-[13px] font-bold text-on-surface">{_esc(substance)}</span>
            {reaction_html}
          </div>
          <div class="flex items-center gap-xs ml-sm whitespace-nowrap">
            <span class="px-xs py-0.5 rounded text-[10px] font-bold {badge_color}">{_esc(category)}</span>
          </div>
        </div>""")

    if not items:
        return '<p class="font-body-sm text-body-sm text-on-surface-variant italic">No specific allergens recorded.</p>'

    count_badge = f'<span class="text-[10px] text-on-surface-variant ml-sm">({len(items)} total)</span>'
    return f'<div class="grid grid-cols-1">{"".join(items)}</div>'


def _render_medications(events: List[TimelineEvent]) -> str:
    if not events:
        return '<p class="font-body-sm text-body-sm text-on-surface-variant italic">No medication records found.</p>'

    med_lookup = _build_medication_name_lookup(events)
    active_events = [e for e in events if _is_active_medication_event(e)]
    active_events.sort(key=lambda e: e.date or "", reverse=True)

    seen, items = set(), []
    for e in active_events:
        med_name = _resolve_medication_name(e, med_lookup)
        if not med_name:
            continue

        key = med_name.lower().strip()
        if key in seen:
            continue
        seen.add(key)

        rec = e.original_record or {}
        requester = ((rec.get("requester") or {}).get("display") or "")
        dosage = ""
        di = rec.get("dosageInstruction") or []
        if di:
            dosage = di[0].get("text") or ""

        sub_line = " · ".join(filter(None, [
            _fmt_date(e.date),
            _esc(requester) if requester else "",
            _esc(dosage) if dosage else "",
        ]))

        items.append(f"""
        <div class="flex gap-md items-start p-sm bg-surface-container-lowest border-l-4 border-secondary shadow-sm rounded">
          <span class="material-symbols-outlined text-secondary mt-xs">pill</span>
          <div class="flex-1">
            <p class="text-[13px] font-bold text-on-surface">{_esc(med_name)}</p>
            <p class="text-[11px] text-on-surface-variant mt-xs">{sub_line}</p>
          </div>
          <span class="bg-secondary-container text-on-secondary-container px-xs py-0.5 rounded text-[10px] font-bold uppercase whitespace-nowrap ml-sm">Active</span>
        </div>""")

    if not items:
        return '<p class="font-body-sm text-body-sm text-on-surface-variant italic">No active medications on file.</p>'
    return f'<div class="space-y-sm">{"".join(items)}</div>'


def _fhir_encounter_class(rec: Dict[str, Any]) -> str:
    """Return human-readable encounter class: Ambulatory, Inpatient, Emergency, etc."""
    cls = rec.get("class") or {}
    display = cls.get("display") or cls.get("code") or ""
    mapping = {
        "AMB": "Ambulatory", "ambulatory": "Ambulatory",
        "IMP": "Inpatient",  "inpatient":  "Inpatient",
        "EMER": "Emergency", "emergency":  "Emergency",
        "HH":  "Home Health","VR":         "Virtual",
        "OBSENC": "Observation",
    }
    return mapping.get(display, display.title() if display else "Visit")


def _fhir_encounter_provider(rec: Dict[str, Any]) -> str:
    """Return primary provider display name from Encounter.participant."""
    for p in rec.get("participant") or []:
        name = (p.get("individual") or {}).get("display") or ""
        if name:
            # Normalise "Barclay, Joseph B" → "Joseph B Barclay"
            parts = [x.strip() for x in name.split(",")]
            if len(parts) == 2:
                return f"{parts[1]} {parts[0]}"
            return name
    return ""


def _fhir_encounter_location(rec: Dict[str, Any]) -> str:
    """Return primary location display name."""
    for loc in rec.get("location") or []:
        name = (loc.get("location") or {}).get("display") or ""
        if name:
            return name
    return ""


def _render_encounters_table(events: List[TimelineEvent]) -> str:
    if not events:
        return '<p class="font-body-sm text-body-sm text-on-surface-variant italic">No encounter records found.</p>'

    # Sort newest first, deduplicate on (date, provider) to collapse Apr 25 2022 flood
    seen, rows = set(), []
    sorted_enc = sorted(events, key=lambda e: e.date or "0000", reverse=True)

    for e in sorted_enc:
        rec = e.original_record or {}
        provider  = _fhir_encounter_provider(rec)
        location  = _fhir_encounter_location(rec)
        enc_class = _fhir_encounter_class(rec)
        date_key  = (e.date or "")[:10]

        dedup_key = (date_key, provider.lower())
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Build a clean, meaningful description
        parts = []
        if enc_class and enc_class != "Visit":
            parts.append(enc_class)
        if provider:
            parts.append(f"with {provider}")
        if location:
            parts.append(f"at {location}")
        period = rec.get("period") or {}
        start, end = period.get("start") or "", period.get("end") or ""
        if start and end and start[:10] != end[:10]:
            parts.append(f"({start[:10]} → {end[:10]})")
        description = " · ".join(parts) if parts else "Clinical visit"

        status = (rec.get("status") or "").title()
        status_class = "bg-green-100 text-green-800" if status.lower() == "finished" else "bg-yellow-100 text-yellow-800"

        rows.append(f"""
        <tr class="hover:bg-surface-container-low transition-colors">
          <td class="p-sm text-[13px] font-medium text-on-surface whitespace-nowrap align-top">{_fmt_date(e.date)}</td>
          <td class="p-sm text-[13px] text-on-surface align-top">{_esc(description)}</td>
          <td class="p-sm align-top">
            <span class="text-[11px] font-bold px-xs py-0.5 rounded {status_class}">{_esc(status or 'Unknown')}</span>
          </td>
        </tr>""")

    return f"""
    <table class="w-full text-left border-collapse">
      <thead class="bg-surface-container border-y border-outline-variant">
        <tr>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Date</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Encounter Details</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Status</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-outline-variant">{"".join(rows)}</tbody>
    </table>"""


_LAB_NAME_NOISE = None  # initialised lazily


def _render_lab_results(events: List[TimelineEvent]) -> str:
    if not events:
        return '<p class="font-body-sm text-body-sm text-on-surface-variant italic">No laboratory records found.</p>'

    seen, rows = set(), []
    sorted_ev = sorted(events, key=lambda e: e.date or "0000", reverse=True)

    for e in sorted_ev:
        rec = e.original_record or {}
        if (rec.get("status") or "").lower() == "entered-in-error":
            continue

        test_name, value = _fhir_obs_name_value(rec)
        if not test_name:
            test_name = _fhir_code_text(rec) or _trunc(e.summary, 50)
        key = test_name.lower().strip()
        if key in ("narrative", "impression", "findings", "finding", "report") or key in seen or not key:
            continue
        seen.add(key)

        ref_range = _fhir_obs_reference_range(rec)
        flag_label, flag_class = _fhir_obs_interpretation(rec, value)
        performer = _fhir_obs_performer(rec)
        note = _fhir_obs_note(rec)
        status = (rec.get("status") or "").title()

        flag_html = (
            f'<span class="text-[10px] font-bold px-xs py-0.5 rounded {flag_class}">{_esc(flag_label)}</span>'
            if flag_label
            else (f'<span class="text-[10px] text-on-surface-variant">{_esc(status)}</span>' if status else "—")
        )

        details_parts = []
        if performer:
            details_parts.append(performer)
        if note:
            details_parts.append(_trunc(note, 40))
        details_text = " · ".join(details_parts) if details_parts else "—"

        rows.append(f"""
        <tr class="hover:bg-surface-container-low transition-colors">
          <td class="p-sm text-[13px] font-medium text-on-surface whitespace-nowrap align-top">{_fmt_date(e.date)}</td>
          <td class="p-sm text-[13px] font-semibold text-on-surface align-top">{_esc(test_name)}</td>
          <td class="p-sm text-[13px] font-bold text-secondary align-top whitespace-nowrap">{_esc(value) if value else "—"}</td>
          <td class="p-sm align-top whitespace-nowrap">{flag_html}</td>
          <td class="p-sm text-[12px] text-on-surface-variant align-top whitespace-nowrap">{_esc(ref_range) if ref_range else "—"}</td>
          <td class="p-sm text-[12px] text-on-surface-variant align-top">{_esc(details_text)}</td>
        </tr>""")

        if len(rows) >= 18:
            break

    if not rows:
        return '<p class="font-body-sm text-body-sm text-on-surface-variant italic">No laboratory records found.</p>'

    return f"""
    <table class="w-full text-left border-collapse">
      <thead class="bg-surface-container border-y border-outline-variant">
        <tr>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Date</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Test Name</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Result Value</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Status / Flag</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Reference Range</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Details / Facility</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-outline-variant">{"".join(rows)}</tbody>
    </table>"""


def _render_social_history(events: List[TimelineEvent]) -> str:
    """Render lifestyle / social history observations (smoking, alcohol, occupation)."""
    if not events:
        return ""

    seen, rows = set(), []
    sorted_ev = sorted(events, key=lambda e: e.date or "0000", reverse=True)

    for e in sorted_ev:
        rec = e.original_record or {}
        if (rec.get("status") or "").lower() == "entered-in-error":
            continue

        name, value = _fhir_obs_name_value(rec)
        if not name:
            name = _fhir_code_text(rec) or "Social History Observation"
        if not value:
            value = _clean_summary(e.summary or "")

        if value:
            value = re.sub(r"^Observation\s+[^:]*:\s*", "", value, flags=re.IGNORECASE).rstrip(".").strip()

        key = name.lower().strip()
        if key in seen or not key:
            continue
        seen.add(key)

        date_str = _fmt_date(e.date) if e.date else "Documented"

        rows.append(f"""
        <tr class="hover:bg-surface-container-low transition-colors">
          <td class="p-sm text-[13px] font-medium text-on-surface whitespace-nowrap align-top">{date_str}</td>
          <td class="p-sm text-[13px] font-semibold text-on-surface align-top">{_esc(name)}</td>
          <td class="p-sm text-[13px] font-bold text-secondary align-top">{_esc(value) if value else "—"}</td>
        </tr>""")

        if len(rows) >= 8:
            break

    if not rows:
        return ""

    return f"""
    <table class="w-full text-left border-collapse">
      <thead class="bg-surface-container border-y border-outline-variant">
        <tr>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Date</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Lifestyle / Factor</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Finding / Status</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-outline-variant">{"".join(rows)}</tbody>
    </table>"""


def _render_clinical_assessments(events: List[TimelineEvent]) -> str:
    """Render clinical assessment / screener observations (PHQ-9, GAD-7, pain scales)."""
    if not events:
        return ""

    seen, rows = set(), []
    sorted_ev = sorted(events, key=lambda e: e.date or "0000", reverse=True)

    for e in sorted_ev:
        rec = e.original_record or {}
        if (rec.get("status") or "").lower() == "entered-in-error":
            continue

        name, value = _fhir_obs_name_value(rec)
        if not name:
            name = _fhir_code_text(rec) or "Clinical Screener"
        if not value:
            value = _clean_summary(e.summary or "")

        key = name.lower().strip()
        if key in seen or not key:
            continue
        seen.add(key)

        flag_label, flag_class = _fhir_obs_interpretation(rec, value)
        flag_html = (
            f'<span class="text-[10px] font-bold px-xs py-0.5 rounded {flag_class}">{_esc(flag_label)}</span>'
            if flag_label
            else "—"
        )

        rows.append(f"""
        <tr class="hover:bg-surface-container-low transition-colors">
          <td class="p-sm text-[13px] font-medium text-on-surface whitespace-nowrap align-top">{_fmt_date(e.date)}</td>
          <td class="p-sm text-[13px] font-semibold text-on-surface align-top">{_esc(name)}</td>
          <td class="p-sm text-[13px] font-bold text-secondary align-top whitespace-nowrap">{_esc(value) if value else "—"}</td>
          <td class="p-sm align-top whitespace-nowrap">{flag_html}</td>
        </tr>""")

        if len(rows) >= 8:
            break

    if not rows:
        return ""

    return f"""
    <table class="w-full text-left border-collapse">
      <thead class="bg-surface-container border-y border-outline-variant">
        <tr>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Date</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Screener / Assessment</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Score / Result</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Interpretation</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-outline-variant">{"".join(rows)}</tbody>
    </table>"""


def _render_vital_signs(events: List[TimelineEvent]) -> str:
    """Vital signs cards; empty string hides the section when there are none."""
    if not events:
        return ""

    sorted_ev = sorted(events, key=lambda e: e.date or "0000", reverse=True)
    valid_entries = []
    for e in sorted_ev:
        rec = e.original_record or {}
        if (rec.get("status") or "").lower() == "entered-in-error":
            continue
        test_name, value = _fhir_obs_name_value(rec)
        if not test_name:
            test_name = _fhir_code_text(rec) or _trunc(e.summary, 50)
        v_key = test_name.lower().strip()
        if not v_key:
            continue
        valid_entries.append((e, rec, test_name, value, v_key))

    if not valid_entries:
        return ""

    # Phase 1: Keep latest reading of each unique vital type
    unique_vitals = {}
    other_readings = []
    for entry in valid_entries:
        v_key = entry[4]
        if v_key not in unique_vitals:
            unique_vitals[v_key] = entry
        else:
            other_readings.append(entry)

    selected = list(unique_vitals.values())

    # Phase 2: If we have room (< 6 cards), populate with other readings on distinct dates
    # prioritizing readings with abnormal interpretation flags first, then recent readings
    if len(selected) < 6:
        seen_dates = {(ent[4], (ent[0].date or "")[:10]) for ent in selected}
        abnormal_entries = []
        normal_entries = []
        for ent in other_readings:
            e, rec, t_name, val, v_key = ent
            flag_l, _ = _fhir_obs_interpretation(rec, val)
            d_key = (v_key, (e.date or "")[:10])
            if d_key not in seen_dates:
                seen_dates.add(d_key)
                if flag_l and flag_l.lower() in ("abnormal", "high", "low", "critical high", "critical low"):
                    abnormal_entries.append(ent)
                else:
                    normal_entries.append(ent)

        for ent in abnormal_entries + normal_entries:
            if len(selected) >= 6:
                break
            selected.append(ent)

    # Sort selected cards in clinical flowsheet order: BP, Pulse, Temp, SpO2, Weight, Height
    vital_order = {
        "blood pressure": 1,
        "pulse": 2,
        "heart rate": 2,
        "temperature": 3,
        "body temperature": 3,
        "spo2": 4,
        "oxygen saturation": 4,
        "respiratory rate": 5,
        "weight": 6,
        "body weight": 6,
        "height": 7,
        "body height": 7,
        "body mass index": 8,
        "bmi": 8,
    }
    selected.sort(key=lambda ent: (vital_order.get(ent[4], 50), -(int(ent[0].date.replace("-", "")[:8]) if ent[0].date and ent[0].date[:4].isdigit() else 0)))

    cards = []
    for e, rec, test_name, value, _ in selected:
        value_html = (
            f'<span class="font-bold text-secondary text-[14px]">{_esc(value)}</span>'
            if value else ""
        )
        flag_label, flag_class = _fhir_obs_interpretation(rec, value)
        flag_html = (
            f'<span class="text-[10px] font-bold px-xs py-0.5 rounded {flag_class}">{_esc(flag_label)}</span>'
            if flag_label
            else ""
        )

        clean_summary = _clean_summary(e.summary or "")
        # Don't duplicate "Observation <Name>: <Value>." if value is already shown
        if value and clean_summary:
            norm_val = re.sub(r"\s+", "", value).lower()
            norm_sum = re.sub(r"\s+", "", clean_summary).lower()
            if norm_val in norm_sum and norm_sum.startswith("observation"):
                clean_summary = ""

        cards.append(f"""
        <div class="border border-outline-variant p-md rounded bg-surface-container-lowest flex flex-col justify-between">
          <div>
            <div class="flex justify-between items-start mb-xs gap-sm">
              <div class="flex items-center gap-xs flex-wrap">
                <p class="text-[13px] font-semibold text-on-surface">{_esc(test_name)}</p>
                {flag_html}
              </div>
              <span class="text-[11px] text-on-surface-variant whitespace-nowrap">{_fmt_date(e.date)}</span>
            </div>
            <div class="my-xs">
              {value_html}
            </div>
          </div>
          {f'<p class="text-[11px] text-on-surface-variant leading-relaxed mt-xs">{_esc(clean_summary)}</p>' if clean_summary else ""}
        </div>""")

    if not cards:
        return ""
    return f'<div class="grid grid-cols-2 gap-gutter">{"".join(cards)}</div>'


def _render_imaging(events: List[TimelineEvent]) -> str:
    import re as _re
    if not events:
        return '<p class="font-body-sm text-body-sm text-on-surface-variant italic">No imaging or diagnostic records found.</p>'

    # Noise patient name strings to strip from summaries
    _NAME_NOISE = _re.compile(
        r"\b(Test,?\s*APIPatient|Camila\s+Maria\s+Lopez|APIPatient)\b",
        _re.IGNORECASE,
    )

    status_styles = {
        "final":            ("bg-green-100 text-green-800",  "Final"),
        "preliminary":      ("bg-yellow-100 text-yellow-800","Preliminary"),
        "cancelled":        ("bg-red-100 text-red-700",      "Cancelled"),
        "partial":          ("bg-blue-100 text-blue-800",    "Partial"),
        "registered":       ("bg-gray-100 text-gray-600",    "Registered"),
        "unknown":          ("bg-gray-100 text-gray-600",    "Unknown"),
    }

    # Sort newest first; filter entered-in-error; deduplicate by study name
    sorted_ev = sorted(events, key=lambda e: e.date or "0000", reverse=True)
    seen, rows = set(), []

    for e in sorted_ev:
        rec = e.original_record or {}
        status = (rec.get("status") or "unknown").lower()
        if status == "entered-in-error":
            continue

        study_name = _fhir_code_text(rec) or "Diagnostic Report"
        # Filter generic noise codes
        if study_name.lower() in ("lab", "laboratory", "report"):
            study_name = "Lab Report"

        key = study_name.lower().strip()
        if key in seen:
            continue
        seen.add(key)

        badge_class, badge_label = status_styles.get(status, ("bg-gray-100 text-gray-600", status.title()))

        # Build a clean description — never show SKIP_AI fallback text
        conclusion = (rec.get("conclusion") or "").strip()
        if not conclusion:
            cleaned = _clean_summary(e.summary or "")
            if cleaned:
                import re as _re2
                cleaned = _re2.sub(r"^Patient (had|underwent|had a)\s+", "", cleaned, flags=_re2.I)
                conclusion = _trunc(cleaned, 80)
        # Absolute fallback: show performer if available
        if not conclusion:
            for perf in (rec.get("performer") or []):
                disp = (perf.get("display") or "")
                if disp:
                    conclusion = f"Reported by {disp}"
                    break

        rows.append(f"""
        <tr class="hover:bg-surface-container-low transition-colors">
          <td class="p-sm text-[13px] font-medium text-on-surface whitespace-nowrap align-top">{_fmt_date(e.date)}</td>
          <td class="p-sm text-[13px] font-semibold text-on-surface align-top">{_esc(study_name)}</td>
          <td class="p-sm text-[13px] text-on-surface-variant align-top">{_esc(conclusion)}</td>
          <td class="p-sm align-top whitespace-nowrap">
            <span class="text-[11px] font-bold px-xs py-0.5 rounded {badge_class}">{badge_label}</span>
          </td>
        </tr>""")

    if not rows:
        return '<p class="font-body-sm text-body-sm text-on-surface-variant italic">No imaging or diagnostic records found.</p>'

    return f"""
    <table class="w-full text-left border-collapse">
      <thead class="bg-surface-container border-y border-outline-variant">
        <tr>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Date</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Study / Test</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Details</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Status</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-outline-variant">{"".join(rows)}</tbody>
    </table>"""


_DOC_TYPE_MAP = {
    "34117-2": "History & Physical Note",
    "51847-2": "Evaluation & Plan Note",
    "11488-4": "Consultation Note",
    "18842-5": "Discharge Summary",
    "34133-9": "Summarization of Episode Note",
    "11506-3": "Progress Note",
    "28570-0": "Procedure Note",
    "18748-4": "Diagnostic Imaging Report",
}
_NOISE_AUTHORS = {"unk", "unknown", "test", "apipatient", "fhir sandbox", ""}


def _render_clinical_notes(events: List[TimelineEvent]) -> str:
    if not events:
        return '<p class="text-[13px] text-on-surface-variant italic">No clinical note records found.</p>'

    doc_status_styles = {
        "current":    ("bg-green-100 text-green-800",  "Current"),
        "superseded": ("bg-gray-100 text-gray-600",    "Superseded"),
        "entered-in-error": ("bg-red-100 text-red-700","Error"),
    }

    today_year = datetime.utcnow().year
    seen, rows = set(), []
    # Sort: current status first, then newest date
    sorted_ev = sorted(
        events,
        key=lambda e: (0 if (e.original_record or {}).get("status") == "current" else 1,
                       -(int((e.date or "0000")[:4]))),
    )

    for e in sorted_ev:
        rec = e.original_record or {}
        status = (rec.get("status") or "unknown").lower()
        if status == "entered-in-error":
            continue

        # Use context.period.start as the clinical date (not import date)
        context = rec.get("context") or {}
        period = context.get("period") or {}
        clinical_date = period.get("start") or e.date or ""

        # Skip entries whose only date is a future/import-time year (2026 = import artifact)
        date_year = int(clinical_date[:4]) if clinical_date and len(clinical_date) >= 4 else 0
        if date_year >= today_year:
            clinical_date = ""  # Don't show misleading import date — show blank

        # Build document type label from LOINC codes
        doc_type = rec.get("type") or {}
        type_label = ""
        for c in (doc_type.get("coding") or []):
            code = c.get("code") or ""
            type_label = _DOC_TYPE_MAP.get(code, "") or c.get("display") or ""
            if type_label and type_label.lower() not in ("ccd document",):
                break
        if not type_label:
            type_label = doc_type.get("text") or ""
            if type_label.lower() == "ccd document":
                type_label = "Clinical Summary (CCD)"

        description = rec.get("description") or ""
        label = description if description and description.lower() not in ("physical",) else type_label or "Clinical Document"

        key = (label.lower(), (clinical_date or "")[:7])  # dedupe on label+month
        if key in seen:
            continue
        seen.add(key)

        # Author — strip noise values
        author = ""
        for a in (rec.get("author") or []):
            disp = (a.get("display") or "").strip()
            if disp.lower() not in _NOISE_AUTHORS:
                author = disp
                break

        badge_class, badge_text = doc_status_styles.get(status, ("bg-gray-100 text-gray-600", status.title()))
        date_display = _fmt_date(clinical_date) if clinical_date else "NA"

        rows.append(f"""
        <tr class="hover:bg-surface-container-low transition-colors">
          <td class="p-sm text-[13px] font-medium text-on-surface whitespace-nowrap align-top">{date_display}</td>
          <td class="p-sm text-[13px] text-on-surface align-top">{_esc(_trunc(label, 45))}</td>
          <td class="p-sm text-[12px] text-on-surface-variant align-top">{_esc(_trunc(author, 30)) if author else "—"}</td>
          <td class="p-sm align-top whitespace-nowrap">
            <span class="text-[11px] font-bold px-xs py-0.5 rounded {badge_class}">{badge_text}</span>
          </td>
        </tr>""")

        if len(rows) >= 8:
            break

    if not rows:
        return '<p class="text-[13px] text-on-surface-variant italic">No clinical note records found.</p>'

    return f"""
    <table class="w-full text-left border-collapse">
      <thead class="bg-surface-container border-y border-outline-variant">
        <tr>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Date</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Document Type</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Author</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Status</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-outline-variant">{"".join(rows)}</tbody>
    </table>"""


def _render_immunizations(events: List[TimelineEvent]) -> str:
    if not events:
        return ""
    seen, rows = set(), []
    sorted_ev = sorted(events, key=lambda e: e.date or "0000", reverse=True)
    for e in sorted_ev:
        rec = e.original_record or {}
        vaccine = _fhir_code_text(rec) or _clean_summary(e.summary or "")
        if not vaccine or vaccine in seen:
            continue
        seen.add(vaccine)
        status = (rec.get("status") or "").lower()
        status_html = ""
        if status == "not-done":
            status_html = '<span class="text-[10px] font-bold px-xs py-0.5 rounded bg-red-100 text-red-700 ml-sm">Not Done</span>'
        rows.append(f"""
        <tr class="hover:bg-surface-container-low">
          <td class="p-sm text-[13px] font-medium text-on-surface whitespace-nowrap">{_fmt_date(e.date)}</td>
          <td class="p-sm text-[13px] text-on-surface">{_esc(vaccine)}{status_html}</td>
        </tr>""")
    if not rows:
        return ""
    return f"""
    <table class="w-full text-left border-collapse">
      <thead class="bg-surface-container border-y border-outline-variant">
        <tr>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Date</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Vaccine</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-outline-variant">{"".join(rows)}</tbody>
    </table>"""


def _render_procedures(events: List[TimelineEvent]) -> str:
    if not events:
        return ""
    seen, rows = set(), []
    sorted_ev = sorted(events, key=lambda e: e.date or "0000", reverse=True)
    for e in sorted_ev:
        rec = e.original_record or {}
        proc_name = _fhir_code_text(rec) or _clean_summary(e.summary or "")
        if not proc_name or proc_name in seen:
            continue
        seen.add(proc_name)
        status = (rec.get("status") or "").lower()
        badge = ""
        if status in ("not-done", "stopped", "aborted"):
            badge = f'<span class="text-[10px] font-bold px-xs py-0.5 rounded bg-gray-100 text-gray-600 ml-sm">{status.title()}</span>'
        rows.append(f"""
        <tr class="hover:bg-surface-container-low">
          <td class="p-sm text-[13px] font-medium text-on-surface whitespace-nowrap align-top">{_fmt_date(e.date)}</td>
          <td class="p-sm text-[13px] text-on-surface align-top">{_esc(proc_name)}{badge}</td>
        </tr>""")
    if not rows:
        return ""
    return f"""
    <table class="w-full text-left border-collapse">
      <thead class="bg-surface-container border-y border-outline-variant">
        <tr>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Date</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Procedure</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-outline-variant">{"".join(rows)}</tbody>
    </table>"""


def _render_hospitalizations(events: List[TimelineEvent]) -> str:
    """Render inpatient/hospitalization encounters as a table."""
    if not events:
        return ""
    seen, rows = set(), []
    sorted_ev = sorted(events, key=lambda e: e.date or "0000", reverse=True)
    for e in sorted_ev:
        rec = e.original_record or {}
        period = rec.get("period") or {}
        start  = (period.get("start") or e.date or "")[:10]
        end    = (period.get("end") or "")[:10]

        dedup = (start, end)
        if dedup in seen:
            continue
        seen.add(dedup)

        provider = _fhir_encounter_provider(rec)
        location = _fhir_encounter_location(rec)
        reason   = ""
        for r in (rec.get("reasonCode") or []):
            reason = r.get("text") or ""
            if not reason:
                for c in r.get("coding") or []:
                    reason = c.get("display") or ""
                    if reason:
                        break
            if reason:
                break

        duration = ""
        if start and end and start != end:
            duration = f"{start} → {end}"
        elif start:
            duration = start

        detail = " · ".join(filter(None, [
            f"with {provider}" if provider else "",
            f"at {location}" if location else "",
            _trunc(reason, 35) if reason else "",
        ]))

        rows.append(f"""
        <tr class="hover:bg-surface-container-low transition-colors">
          <td class="p-sm text-[13px] font-medium text-on-surface whitespace-nowrap align-top">{_fmt_date(start)}</td>
          <td class="p-sm text-[13px] text-on-surface align-top">{_esc(detail) if detail else "Inpatient stay"}</td>
          <td class="p-sm text-[12px] text-on-surface-variant align-top whitespace-nowrap">{_esc(end[:10]) if end and end != start else "NA"}</td>
        </tr>""")

        if len(rows) >= 8:
            break

    if not rows:
        return ""
    return f"""
    <table class="w-full text-left border-collapse">
      <thead class="bg-surface-container border-y border-outline-variant">
        <tr>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Admission Date</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Details</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Discharge Date</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-outline-variant">{"".join(rows)}</tbody>
    </table>"""


def _render_other_health_events(events: List[TimelineEvent]) -> str:
    """Render a compact summary of Other Health Events (catch-all category)."""
    if not events:
        return ""
    # Group by resource type and show top entries per type
    from collections import defaultdict
    by_type: Dict[str, List[TimelineEvent]] = defaultdict(list)
    for e in events:
        rtype = (e.original_record or {}).get("resourceType") or e.resource_type or "Other"
        by_type[rtype].append(e)

    rows = []
    for rtype, evts in sorted(by_type.items()):
        evts_sorted = sorted(evts, key=lambda e: e.date or "0000", reverse=True)
        sample = evts_sorted[:2]
        for e in sample:
            rec = e.original_record or {}
            name = _fhir_code_text(rec)
            if not name or name.lower() in ("null",):
                clean = _clean_summary(e.summary or "")
                name  = _trunc(clean, 55) if clean else rtype
            rows.append(f"""
            <tr class="hover:bg-surface-container-low transition-colors">
              <td class="p-sm text-[13px] font-medium whitespace-nowrap align-top">{_fmt_date(e.date)}</td>
              <td class="p-sm text-[11px] text-on-surface-variant align-top whitespace-nowrap">{_esc(rtype)}</td>
              <td class="p-sm text-[13px] text-on-surface align-top">{_esc(_trunc(name, 60))}</td>
            </tr>""")
        if len(rows) >= 12:
            break

    total = len(events)
    note  = f'<p class="text-[11px] text-on-surface-variant mt-sm italic">{total} total events · showing a representative sample</p>' if total > 12 else ""
    return f"""
    <table class="w-full text-left border-collapse">
      <thead class="bg-surface-container border-y border-outline-variant">
        <tr>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant whitespace-nowrap">Date</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Resource Type</th>
          <th class="p-sm text-[11px] font-bold uppercase tracking-wide text-on-surface-variant">Event</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-outline-variant">{"".join(rows)}</tbody>
    </table>{note}"""


def _section(title: str, content: str, border_color: str = "#720076") -> str:
    """Wrap a rendered section — returns empty string if content is empty."""
    if not content or not content.strip():
        return ""
    return f"""
  <section style="margin-bottom:24px;">
    <div style="border-left:4px solid {border_color};padding-left:10px;margin-bottom:10px;">
      <h3 style="font-size:14px;font-weight:700;color:#1a1c1d;letter-spacing:0.01em;">{title}</h3>
    </div>
    {content}
  </section>"""


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_html(summary: EHRSummaryResponse) -> str:
    p = summary.patient
    tl = summary.timeline or []

    name      = _esc(p.name or "Unknown Patient")
    pid       = _esc(p.patient_id or "NA")
    overview_html = _render_clinical_overview(tl, p.summary)

    diagnoses      = _events_for(tl, "Diagnoses")
    allergies      = _events_for(tl, "Allergies")
    medications    = _events_for(tl, "Medications")
    encounters     = _events_for(tl, "Encounters / Visits")
    labs_all       = _events_for(tl, "Laboratory Results")
    labs, vitals_from_labs, social_from_labs, surveys_from_labs = _partition_observation_events(labs_all)
    vitals         = _events_for(tl, "Vital Signs") + vitals_from_labs
    social_hist    = _events_for(tl, "Social History") + social_from_labs
    surveys        = _events_for(tl, "Clinical Assessments & Surveys") + surveys_from_labs
    imaging        = _events_for(tl, "Imaging & Radiology")
    notes          = _events_for(tl, "Clinical Notes")
    immuniz        = _events_for(tl, "Immunizations")
    procedures     = _events_for(tl, "Procedures")
    hospitaliz     = _events_for(tl, "Hospitalizations")
    other_events   = _events_for(tl, "Other Health Events")

    start_y, end_y = _year_range(tl, patient_dob=p.birth_date)
    year_labels = _timeline_years(start_y, end_y)

    timeline_markers = "".join(
        f"""<div class="flex flex-col items-center">
          <div class="w-3 h-3 {'bg-primary ring-2 ring-primary ring-offset-2' if i == len(year_labels)-1 else 'bg-secondary'} rounded-full mb-1"></div>
          <span class="font-label-sm text-label-sm text-on-surface-variant {'font-bold' if i == len(year_labels)-1 else ''}">{y}</span>
          {'<div class="absolute -top-7 bg-primary-container text-on-primary-container px-2 py-1 rounded text-[10px] font-bold">Current</div>' if i == len(year_labels)-1 else ''}
        </div>"""
        for i, y in enumerate(year_labels)
    )

    # All sections rendered dynamically — only appear if data exists
    sec_encounters   = _section("Encounters / Visits",      _render_encounters_table(encounters),   "#720076")
    sec_hospitaliz   = _section("Hospitalizations",         _render_hospitalizations(hospitaliz),   "#720076")
    sec_labs         = _section("Laboratory Results",       _render_lab_results(labs),              "#4f54b1")
    sec_vitals       = _section("Vital Signs",              _render_vital_signs(vitals),            "#4f54b1")
    sec_social_hist  = _section("Social &amp; Behavioral History", _render_social_history(social_hist), "#4f54b1")
    sec_surveys      = _section("Clinical Assessments &amp; Screenings", _render_clinical_assessments(surveys), "#4f54b1")
    sec_imaging      = _section("Imaging &amp; Radiology",  _render_imaging(imaging),               "#4f54b1")
    sec_notes        = _section("Clinical Notes",           _render_clinical_notes(notes),          "#4f54b1")
    sec_immuniz      = _section("Immunizations",            _render_immunizations(immuniz),         "#52424f")
    sec_procedures   = _section("Procedures",               _render_procedures(procedures),         "#52424f")
    sec_other        = _section("Other Health Events",      _render_other_health_events(other_events), "#52424f")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Clinical Health Summary — {name}</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
<script>
  tailwind.config = {{
    darkMode: "class",
    theme: {{
      extend: {{
        colors: {{
          "background": "#f9f9fb", "on-surface": "#1a1c1d", "outline": "#857181",
          "on-secondary-fixed": "#03006d", "secondary-fixed-dim": "#bfc1ff",
          "on-error-container": "#93000a", "on-error": "#ffffff", "error": "#ba1a1a",
          "error-container": "#ffdad6", "on-surface-variant": "#52424f",
          "secondary-fixed": "#e1e0ff", "on-background": "#1a1c1d",
          "secondary": "#4f54b1", "surface-variant": "#e2e2e4",
          "on-secondary": "#ffffff", "surface-dim": "#d9dadc",
          "primary-fixed": "#ffd6f7", "primary-container": "#99019e",
          "secondary-container": "#989dff", "surface-bright": "#f9f9fb",
          "surface-container": "#edeef0", "surface-container-lowest": "#ffffff",
          "inverse-on-surface": "#f0f0f2", "inverse-primary": "#ffaaf7",
          "on-primary-container": "#ffb2f7", "surface-tint": "#a317a7",
          "inverse-surface": "#2f3132", "surface-container-high": "#e8e8ea",
          "surface": "#f9f9fb", "on-secondary-container": "#2b2f8c",
          "primary": "#720076", "on-primary": "#ffffff",
          "surface-container-low": "#f3f3f5",
          "surface-container-highest": "#e2e2e4",
          "outline-variant": "#d7c0d1",
        }},
        fontFamily: {{ "body-md": ["Inter"], "body-sm": ["Inter"], "label-md": ["Inter"],
                       "label-sm": ["Inter"], "title-lg": ["Inter"], "headline-md": ["Inter"],
                       "data-tabular": ["Inter"] }},
        fontSize: {{
          "body-sm":     ["14px", {{"lineHeight": "20px", "fontWeight": "400"}}],
          "body-md":     ["16px", {{"lineHeight": "24px", "fontWeight": "400"}}],
          "label-md":    ["13px", {{"lineHeight": "18px", "fontWeight": "600"}}],
          "label-sm":    ["11px", {{"lineHeight": "16px", "letterSpacing": "0.03em", "fontWeight": "700"}}],
          "title-lg":    ["18px", {{"lineHeight": "24px", "fontWeight": "600"}}],
          "headline-md": ["24px", {{"lineHeight": "32px", "fontWeight": "600"}}],
          "data-tabular":["14px", {{"lineHeight": "20px", "fontWeight": "500"}}],
        }},
        spacing: {{
          "xs": "4px", "sm": "8px", "md": "16px", "lg": "24px", "xl": "32px",
          "gutter": "20px",
        }},
      }},
    }},
  }};
</script>
<style>
  * {{ font-family: 'Inter', sans-serif; box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-size: 13px; color: #1a1c1d; line-height: 1.55; }}
  h1, h2, h3, h4 {{ font-family: 'Inter', sans-serif; }}
  table {{ font-family: 'Inter', sans-serif; font-size: 13px; }}
  th, td {{ font-family: 'Inter', sans-serif; }}
  p, span, li {{ font-family: 'Inter', sans-serif; }}
  @media print {{
    .no-print {{ display: none !important; }}
    .print-only-date {{ display: block !important; }}
    .page-break {{ page-break-after: always; }}
    body {{ background: white; }}
    .a4-page {{ margin: 0; box-shadow: none; }}
  }}
  .print-only-date {{ display: none; }}
  .a4-page {{
    width: 210mm; min-height: 297mm; padding: 20mm;
    margin: 20px auto; background: white;
    box-shadow: 0 0 10px rgba(0,0,0,0.1);
    position: relative; overflow: hidden;
  }}
  .material-symbols-outlined {{
    font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
    vertical-align: middle; font-size: 1.25rem;
  }}
</style>
<script>
  function _setPrintGeneratedDate() {{
    var el = document.getElementById("print-generated-date");
    if (!el) return;
    var now = new Date();
    el.textContent = "Generate Date: " + now.toLocaleDateString("en-US", {{
      year: "numeric", month: "short", day: "numeric"
    }});
  }}
  function printPdf() {{
    _setPrintGeneratedDate();
    window.print();
  }}
  window.addEventListener("beforeprint", _setPrintGeneratedDate);
</script>
</head>
<body class="bg-surface-container-low font-body-md text-on-surface antialiased">

<!-- Print Button -->
<div class="no-print fixed top-6 right-6 z-50">
  <button onclick="printPdf()"
    class="flex items-center gap-2 bg-secondary text-on-secondary px-lg py-sm rounded-xl shadow-lg hover:scale-105 transition-transform active:scale-95">
    <span class="material-symbols-outlined">download</span>
    <span class="font-label-md text-label-md">Save as PDF</span>
  </button>
</div>

<!-- ═══ PAGE 1 ═══ -->
<div class="a4-page page-break">
  <!-- Header -->
  <header class="flex justify-between items-center border-b-2 border-primary pb-md mb-lg relative z-10">
    <div class="flex flex-col items-start gap-xs">
      <img src="{HEKMA_LOGO_URL}" alt="Hekma" style="height:48px;width:auto;" class="shrink-0" />
      <p style="font-size:12px;color:#52424f;margin:0;">Patient Health Intelligence Platform</p>
    </div>
    <div class="text-right">
      <p style="font-size:16px;font-weight:700;color:#1a1c1d;">Clinical Health Summary</p>
      <p id="print-generated-date" class="print-only-date" style="font-size:11px;color:#52424f;margin-top:4px;"></p>
    </div>
  </header>

  <!-- Clinical Overview -->
  {f'''<section class="mb-md relative z-10" style="border:1px solid #d7c0d1;border-left:4px solid #720076;border-radius:6px;padding:12px 14px;background:#fdf8fd;">
    <p style="font-size:10px;font-weight:700;color:#52424f;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Clinical Overview</p>
    {overview_html}
  </section>''' if overview_html else ""}

  <!-- Health Timeline -->
  <section style="margin-bottom:24px;">
    <div style="border-left:4px solid #4f54b1;padding-left:10px;margin-bottom:10px;">
      <h3 style="font-size:14px;font-weight:700;color:#1a1c1d;">Longitudinal Health Timeline</h3>
    </div>
    <div style="position:relative;height:72px;background:#edeef0;border-radius:8px;padding:0 16px;display:flex;align-items:center;">
      <div style="position:absolute;height:2px;background:#d7c0d1;left:16px;right:16px;top:50%;"></div>
      <div style="display:flex;justify-content:space-between;width:100%;position:relative;z-index:2;">
        {timeline_markers}
      </div>
    </div>
  </section>

  <!-- Diagnoses + Medications (2 col) -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px;">
    <div>
      <div style="border-left:4px solid #720076;padding-left:10px;margin-bottom:10px;">
        <h3 style="font-size:14px;font-weight:700;color:#1a1c1d;">Active Diagnoses</h3>
      </div>
      {_render_diagnoses(diagnoses)}
    </div>
    <div>
      <div style="border-left:4px solid #4f54b1;padding-left:10px;margin-bottom:10px;">
        <h3 style="font-size:14px;font-weight:700;color:#1a1c1d;">Active Medications</h3>
      </div>
      {_render_medications(medications)}
    </div>
  </div>

  <!-- Allergies (full width) -->
  <section style="margin-bottom:24px;">
    <div style="border-left:4px solid #ba1a1a;padding-left:10px;margin-bottom:10px;display:flex;align-items:center;gap:8px;">
      <h3 style="font-size:14px;font-weight:700;color:#1a1c1d;">Known Allergies &amp; Intolerances</h3>
      <span style="font-size:10px;font-weight:700;background:#ba1a1a;color:#fff;padding:2px 6px;border-radius:4px;">{len(allergies)} on record</span>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
      <div>{_render_allergies(allergies[:len(allergies)//2 + len(allergies)%2])}</div>
      <div>{_render_allergies(allergies[len(allergies)//2 + len(allergies)%2:])}</div>
    </div>
  </section>

  <!-- Page 1 Footer -->
  <footer style="position:absolute;bottom:20mm;left:20mm;right:20mm;border-top:1px solid #d7c0d1;padding-top:8px;display:flex;justify-content:space-between;align-items:flex-end;">
    <p style="font-size:11px;color:#52424f;">{name} · ID: {pid}</p>
    <p style="font-size:11px;font-weight:700;color:#52424f;text-transform:uppercase;">Page 1 of 2</p>
    <p style="font-size:9px;color:#52424f;text-align:right;line-height:1.4;">HIPAA &amp; GDPR Compliant<br/>Confidential Patient Health Information</p>
  </footer>
</div>

<!-- ═══ PAGE 2 ═══ -->
<div class="a4-page">
  <!-- Page 2 Header -->
  <header style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #d7c0d1;padding-bottom:8px;margin-bottom:20px;">
    <div style="display:flex;align-items:center;gap:8px;">
      <img src="{HEKMA_LOGO_URL}" alt="Hekma" style="height:28px;width:auto;" />
    </div>
    <span style="font-size:12px;font-weight:600;color:#1a1c1d;">Patient Clinical Record · {name}</span>
  </header>

  {sec_encounters}
  {sec_hospitaliz}
  {sec_labs}
  {sec_vitals}
  {sec_social_hist}
  {sec_surveys}
  {sec_imaging}
  {sec_notes}
  {sec_immuniz}
  {sec_procedures}
  {sec_other}

  <!-- Data Integrity Notice -->
  <section style="margin-bottom:24px;border:1px solid #d7c0d1;border-radius:6px;padding:12px 14px;background:#f3f3f5;">
    <p style="font-size:10px;font-weight:700;color:#52424f;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">Data Integrity Notice</p>
    <p style="font-size:12px;color:#52424f;font-style:italic;line-height:1.5;">
      AI-generated summaries are derived solely from imported EHR records.
      No clinical conclusions, diagnoses, or recommendations have been added.
      All original source records are preserved and accessible.
    </p>
  </section>

  <!-- Page 2 Footer -->
  <footer class="absolute bottom-10 left-20 right-20 border-t border-outline-variant pt-md flex justify-between items-end text-on-surface-variant">
    <p class="font-label-sm text-label-sm">{name} · ID: {pid}</p>
    <p class="font-label-sm text-label-sm uppercase font-bold">Page 2 of 2</p>
    <p class="font-label-sm text-label-sm text-[9px] text-right leading-snug">HIPAA &amp; GDPR Compliant<br/>Confidential Patient Health Information</p>
  </footer>
</div>

</body>
</html>"""
