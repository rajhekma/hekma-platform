"""
EHR Summary Service
===================
Two-phase pipeline
------------------
Phase 1 (parallel)   — Fetch DB records from all fastenhealth_* tables concurrently.
                        Pure I/O; no rate-limit risk.
Phase 2 (hybrid)     — Per docs/EHR_SUMMARY_TOKEN_OPTIMIZATION.md:
                        Bucket 1: rule-based FHIR templates (~90%, 0 tokens)
                        Bucket 2: OpenAI for narrative + opaque records only
                        patient.summary: 1 LLM call (~1k tokens) unless SKIP_AI
                        EHR_SUMMARY_SKIP_AI=true disables ALL LLM (emergency only).

Why sequential OpenAI?
----------------------
With 25 tables × 2 batches each = 50 concurrent requests → instant 429 flood.
Even a semaphore-capped pool lets all threads queue up and fire back-to-back,
exhausting the per-minute quota in seconds.  A simple for-loop with a polite
sleep is the only reliable fix without a paid higher-tier key.

Log levels
----------
INFO  — phase milestones, cache HIT/MISS, per-table record counts, total time
DEBUG — per-batch OpenAI details, payload sizes, individual record fallbacks
WARNING — payload truncations, per-table query failures, 429/timeout retries
ERROR — OpenAI failures after all retries exhausted

Data-integrity guarantee
------------------------
* raw_resource is returned verbatim in every TimelineEvent.original_record.
* OpenAI is instructed only to condense — never to infer, diagnose, or interpret.
* Original DB rows are never written to.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from ..services.ai_common.usage_emitter import emit_llm_usage

from ..schemas.ehr_summary_schemas import (
    CategoryGroup,
    EHRSummaryResponse,
    OpenAIUsage,
    PatientInfo,
    TimelineEvent,
)
from .ehr_summary_cache_repo import (
    ensure_cache_table,
    get_cached_summary,
    store_cached_summary,
    strip_original_records,
)
from .ehr_summary_overlay import (
    merge_timeline,
    overlay_live_hekma_records,
    collect_hekma_overlay_events,
)
from .ehr_summary_repository import (
    get_ctms_patient_identity,
    get_patient_by_email,
    get_patient_by_id,
    get_patient_records_from_table,
    list_fastenhealth_tables,
    stub_patient_row,
)

logger = logging.getLogger(__name__)

try:
    ensure_cache_table()
except Exception as exc:  # pragma: no cover - import must not require a live DB
    logger.warning("ehr_summary_cache table not ready at import: %s", exc)

# ---------------------------------------------------------------------------
# Clinical category mapping
# ---------------------------------------------------------------------------
_CATEGORY_MAP: Dict[str, str] = {
    "encounter":            "Encounters / Visits",
    "condition":            "Diagnoses",
    "medicationorder":      "Medications",
    "medicationrequest":    "Medications",
    "medicationstatement":  "Medications",
    "medicationdispense":   "Medications",
    "medication":           "Medications",
    "procedure":            "Procedures",
    "observation":          "Laboratory Results",
    "diagnosticreport":     "Imaging & Radiology",
    "imagingstudy":         "Imaging & Radiology",
    "allergyintolerance":   "Allergies",
    "immunization":         "Immunizations",
    "documentreference":    "Clinical Notes",
    "clinicalimpression":   "Clinical Notes",
    "composition":          "Clinical Notes",
    "careplan":             "Hospitalizations",
    "episodeofcare":        "Hospitalizations",
    "hospitalization":      "Hospitalizations",
    "claim":                "Other Health Events",
    "explanationofbenefit": "Other Health Events",
    "coverage":             "Other Health Events",
    "device":               "Other Health Events",
    "devicerequest":        "Other Health Events",
    "goal":                 "Other Health Events",
    "careteam":             "Other Health Events",
    "servicerequest":       "Other Health Events",
    "appointment":          "Other Health Events",
    "appointmentresponse":  "Other Health Events",
    "slot":                 "Other Health Events",
    "schedule":             "Other Health Events",
    "practitioner":         "Other Health Events",
    "organization":         "Other Health Events",
    "location":             "Other Health Events",
    "relatedperson":        "Other Health Events",
}
_DEFAULT_CATEGORY = "Other Health Events"

# ---------------------------------------------------------------------------
# OpenAI throttle settings
# ---------------------------------------------------------------------------

# Records per batch sent to OpenAI in one request.
_OPENAI_BATCH_SIZE = int(os.getenv("EHR_SUMMARY_OPENAI_BATCH_SIZE", "15"))

# Set EHR_SUMMARY_SKIP_AI=true to bypass ALL OpenAI calls (emergency / quota exhausted).
# Default false = hybrid mode per docs/EHR_SUMMARY_TOKEN_OPTIMIZATION.md:
#   • per-event: rule-based for structured FHIR (~90%), AI for narrative/opaque only
#   • patient.summary: always 1 LLM call (~1k tokens)
_SKIP_AI = os.getenv("EHR_SUMMARY_SKIP_AI", "false").lower() in ("1", "true", "yes")

# Mandatory pause between consecutive OpenAI calls (even on success).
# At 1 s gap → ~55 RPM ceiling — safe for Tier 1 (60 RPM limit).
# Set to 0 to disable (only if you have Tier 3+ with 500+ RPM).
_OPENAI_INTER_CALL_DELAY = float(os.getenv("EHR_SUMMARY_OPENAI_INTER_CALL_DELAY", "1.5"))

# Retry settings for 429 / timeout errors.
_OPENAI_MAX_RETRIES = int(os.getenv("EHR_SUMMARY_OPENAI_MAX_RETRIES", "4"))
# Exponential backoff base: 15 s → 30 s → 60 s → 120 s
_OPENAI_RETRY_BASE_DELAY = float(os.getenv("EHR_SUMMARY_OPENAI_RETRY_BASE_DELAY", "15.0"))

# Resource types summarised from FHIR fields directly (0 OpenAI tokens).
_RULE_BASED_TYPES = {
    "condition", "medicationrequest", "medicationstatement", "medicationorder",
    "medicationdispense", "medication", "allergyintolerance", "immunization",
    "procedure", "diagnosticreport", "imagingstudy", "observation", "encounter",
    # Admin / secondary resources — never LLM (use title, name, status fields)
    "careplan", "episodeofcare", "goal", "claim", "explanationofbenefit",
    "coverage", "device", "devicerequest", "careteam", "servicerequest",
    "provenance", "list", "familymemberhistory", "practitioner", "organization",
    "location", "relatedperson", "appointment", "appointmentresponse",
}

# Per-event LLM is restricted to these narrative types only (doc bucket 2).
_AI_NARRATIVE_TYPES = {"documentreference", "composition", "clinicalimpression"}

# On 429 (quota exhausted), skip retries and remaining AI calls for this request.
_FAIL_FAST_ON_429 = os.getenv("EHR_SUMMARY_FAIL_FAST_ON_429", "true").lower() in ("1", "true", "yes")

# Placeholder text baked into cache during SKIP_AI or failed OpenAI runs.
_STALE_SUMMARY_RE = re.compile(
    r"record imported on \d{4}-\d{2}-\d{2}\.\s*Summary unavailable",
    re.IGNORECASE,
)
_PLACEHOLDER_TEXT_RE = re.compile(r"placeholder", re.IGNORECASE)

# Old rule-based patient.summary templates — force regeneration when cached.
_STALE_PATIENT_SUMMARY_RE = re.compile(
    r"Active diagnoses include|Active medical problems include|Known allergies:|"
    r"Diagnostic workup includes|Diagnostic records include|"
    r"Care utilization on file|Documented allergies and intolerances include",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# FHIR date field priority list
# ---------------------------------------------------------------------------
_DATE_FIELD_PATHS: List[Tuple[str, ...]] = [
    ("effectiveDateTime",),
    ("effectivePeriod", "start"),
    ("onsetDateTime",),
    ("onsetPeriod", "start"),
    ("performedDateTime",),
    ("performedPeriod", "start"),
    ("occurrenceDateTime",),
    ("authoredOn",),
    ("dateWritten",),
    ("recordedDate",),
    ("date",),
    ("started",),
    ("period", "start"),
    ("issued",),
    ("indexed",),
    ("created",),
    ("start",),
    ("timestamp",),
    ("birthDate",),
]

# ---------------------------------------------------------------------------
# OpenAI prompt (strictly condense-only)
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a clinical health record summarizer.

Your ONLY job is to produce brief, plain-language summaries of individual \
FHIR health records for patient self-review.

STRICT RULES — you MUST follow all of these without exception:
1. Use ONLY the information explicitly present in the record. Do NOT add, \
infer, interpret, diagnose, recommend, or speculate.
2. Do NOT add any clinical conclusions, treatment suggestions, risk \
assessments, or medical opinions.
3. Preserve all medical terms, numeric values, units, dates, and codes \
exactly as they appear in the source record.
4. If a field is missing or unclear, state what IS available; do not fill gaps.
5. Each summary must be 1–3 sentences maximum.
6. Return your answer as a JSON array with one object per input record: \
[{"record_id": "<id>", "summary": "<summary text>"}]
Do not include any text outside the JSON array.
"""

_USER_PROMPT_TEMPLATE = """\
Summarize each of the following {resource_type} FHIR records.
Records (JSON):
{records_json}
"""

# FHIR fields that hold raw base64 binary content — strip before sending to OpenAI.
_BINARY_FIELDS = {"data", "content", "contentType", "hash", "url", "attachment"}
_MAX_PAYLOAD_CHARS = 200_000


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _get_openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return key


def _get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"


def _new_ai_state() -> Dict[str, Any]:
    return {
        "disabled": False,
        "patient_id": None,
        "request_id": None,
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "llm_calls": 0,
        },
    }


def _record_openai_usage(
    ai_state: Optional[Dict[str, Any]],
    usage: Dict[str, Any],
    *,
    feature: str = "patient_summary",
) -> None:
    if not ai_state or not usage:
        return
    tracker = ai_state.setdefault("usage", {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "llm_calls": 0,
    })
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion))
    tracker["prompt_tokens"] += prompt
    tracker["completion_tokens"] += completion
    tracker["total_tokens"] += total
    tracker["llm_calls"] += 1
    emit_llm_usage(
        patient_id=ai_state.get("patient_id"),
        product="patient_summary",
        feature=feature,
        provider="openai",
        model=_get_openai_model(),
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        source_service="hekma-core",
    )


def _usage_from_ai_state(ai_state: Optional[Dict[str, Any]]) -> OpenAIUsage:
    raw = (ai_state or {}).get("usage") or {}
    return OpenAIUsage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
        total_tokens=int(raw.get("total_tokens") or 0),
        llm_calls=int(raw.get("llm_calls") or 0),
    )


def _lookup_patient_cache(
    patient_id: str,
    include_records: bool,
    req_id: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Always prefer cached data when available.
    Tries the requested shape first, then falls back to slim cache.
    """
    cached = get_cached_summary(patient_id, include_records=include_records)
    if cached:
        return cached
    if include_records:
        logger.debug(
            "Full cache miss — trying slim cache | req_id=%s | patient_id=%s",
            req_id, patient_id,
        )
        cached = get_cached_summary(patient_id, include_records=False)
    return cached


def _build_cache_hit_response(
    cached: Dict[str, Any],
    include_records: bool,
) -> EHRSummaryResponse:
    payload: Dict[str, Any] = dict(cached["data"])
    payload["cache_hit"] = True
    payload["cache_expires_at"] = cached["expires_at"]
    payload["openai_usage"] = OpenAIUsage().model_dump()
    if not include_records:
        payload = strip_original_records(payload)
    return EHRSummaryResponse.model_validate(payload)


# Patient overview LLM prompt (Clinical Overview / patient.summary)
_PATIENT_SUMMARY_PROMPT = """\
You are a clinical documentation assistant.

Given a patient's structured clinical data, generate a concise patient summary in one short paragraph (4–6 sentences).

Guidelines:
- Start with the patient's major active medical conditions.
- Summarize current medications by therapeutic purpose rather than listing every dose unless clinically important.
- Mention significant allergies (group similar environmental allergies together).
- Briefly summarize healthcare utilization only if notable.
- Mention important preventive care (recent immunizations) and recent procedures if clinically relevant.
- Keep the summary factual, concise, and easy for clinicians to read.
- Do not invent or infer information not present in the input.
- Avoid bullet points and section headings.
- Do not include patient name, age, gender, or other demographics.
- Write as one cohesive paragraph. For diagnoses, prefer opening with "The patient has a history of …"

Input:
{patient_data}"""


def _clean_allergy_label(name: str) -> str:
    label = re.sub(r"\s*\([^)]*\)", "", name).strip().lower()
    mapping = {
        "peanut": "peanuts",
        "shellfish (substance)": "shellfish",
        "tree pollen (substance)": "tree pollen",
        "grass pollen (substance)": "grass pollen",
        "house dust mite (organism)": "house dust mites",
        "mold (organism)": "mold",
    }
    return mapping.get(label, label)


def _summarize_medications_for_overview(med_names: List[str]) -> str:
    """Group medications by common therapeutic class for overview prose."""
    labels: List[str] = []
    seen: set = set()

    def add(label: str) -> None:
        key = label.lower()
        if key not in seen:
            seen.add(key)
            labels.append(label)

    for raw in med_names:
        m = raw.lower()
        if "oxycodone" in m or "percocet" in m:
            add("Percocet")
        elif "naproxen" in m:
            add("naproxen")
        elif any(k in m for k in (
            "drospirenone", "ethinyl", "camila", "jolivette", "seasonique",
            "errin", "contraceptive", "day pack", "medroxyprogesterone",
        )):
            add("hormonal contraceptives")
        elif "simvastatin" in m:
            add("simvastatin")
        elif "lisinopril" in m:
            add("lisinopril")
        elif "acetaminophen" in m and "oxycodone" not in m:
            add("acetaminophen")
        else:
            short = re.split(r"\s+\d", raw, maxsplit=1)[0].strip()
            add(short if len(short) <= 45 else short[:45])

    return ", ".join(labels[:6])


def _summarize_allergies_for_overview(allergy_names: List[str]) -> str:
    cleaned = [_clean_allergy_label(n) for n in allergy_names if n]
    seen: set = set()
    unique: List[str] = []
    for item in cleaned:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    if not unique:
        return ""
    if len(unique) <= 6:
        return ", ".join(unique)
    return ", ".join(unique[:8])


def _format_list_prose(items: List[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _summarize_vaccines_for_overview(immunizations: List[Dict[str, Optional[str]]]) -> str:
    labels: List[str] = []
    seen: set = set()
    for item in immunizations[:6]:
        raw = (item.get("vaccine") or "").lower()
        if "tdap" in raw or "diphtheria" in raw:
            label = "Tdap"
        elif "flu" in raw or "influenza" in raw:
            label = "influenza"
        elif "meningococcal" in raw or "mcv4" in raw:
            label = "meningococcal"
        else:
            label = item.get("vaccine") or ""
        key = label.lower()
        if label and key not in seen:
            seen.add(key)
            labels.append(label)
    return _format_list_prose(labels)


def _summarize_procedures_for_overview(procedures: List[Dict[str, Optional[str]]]) -> str:
    labels: List[str] = []
    seen: set = set()
    for item in procedures[:6]:
        name = (item.get("procedure") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        labels.append(name)
    return _format_list_prose(labels[:4])


def _build_narrative_patient_summary(
    active_diagnoses: List[str],
    active_meds: List[str],
    allergies: List[str],
    recent_immunizations: List[Dict[str, Optional[str]]],
    recent_procedures: List[Dict[str, Optional[str]]],
    visit_count: int,
    hosp_count: int,
    lab_count: int,
    imaging_count: int,
) -> str:
    """Rich prose overview (used as LLM fallback and when AI is unavailable)."""
    sentences: List[str] = []

    if active_diagnoses:
        sentences.append(
            f"The patient has a history of {_format_list_prose(active_diagnoses[:8])}."
        )

    med_summary = _summarize_medications_for_overview(active_meds)
    if med_summary:
        sentences.append(f"Current medications include {med_summary}.")

    allergy_summary = _summarize_allergies_for_overview(allergies)
    if allergy_summary:
        sentences.append(
            f"The patient has multiple documented allergies, including {allergy_summary}."
        )

    util_parts: List[str] = []
    if visit_count:
        util_parts.append(f"{visit_count} outpatient visit{'s' if visit_count != 1 else ''}")
    if hosp_count:
        util_parts.append(f"{hosp_count} hospitalization{'s' if hosp_count != 1 else ''}")
    if lab_count:
        util_parts.append(f"{lab_count} laboratory test{'s' if lab_count != 1 else ''}")
    if imaging_count:
        util_parts.append(f"{imaging_count} imaging stud{'ies' if imaging_count != 1 else 'y'}")
    if util_parts:
        sentences.append(
            "The patient has had significant healthcare utilization with "
            + ", ".join(util_parts) + "."
        )

    vax_summary = _summarize_vaccines_for_overview(recent_immunizations)
    proc_summary = _summarize_procedures_for_overview(recent_procedures)
    if vax_summary and proc_summary:
        sentences.append(
            f"Preventive care is up to date with {vax_summary} vaccinations, "
            f"and recent procedures include {proc_summary.lower()}."
        )
    elif vax_summary:
        sentences.append(f"Preventive care is up to date with {vax_summary} vaccinations.")
    elif proc_summary:
        sentences.append(f"Recent procedures include {proc_summary.lower()}.")

    return " ".join(sentences)


def _generate_patient_summary(
    patient_info: "PatientInfo",
    all_events: List[Dict],
    req_id: str = "",
    ai_state: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate a concise 6-7 sentence clinical overview of the patient.
    Extracts facts directly from FHIR original_record fields (never from AI summary text).
    Falls back to rule-based when SKIP_AI=true or OpenAI fails.
    Result is cached as part of the main EHRSummaryResponse — no extra LLM calls on cache hits.
    """
    import re as _re
    from collections import Counter

    _ALLERGY_NOISE = {
        "allergy to substance (finding)", "patient not asked",
        "not on file", "allergy to substance", "no known allergy",
    }

    def _code_text(rec: Dict) -> str:
        code = rec.get("code") or {}
        name = code.get("text") or ""
        if not name:
            for c in (code.get("coding") or []):
                name = c.get("display") or c.get("code") or ""
                if name:
                    break
        return name

    cat_counts: Counter = Counter()
    active_diagnoses, allergies, active_meds = [], [], []
    allergy_entries: List[Dict[str, str]] = []
    recent_immunizations: List[Dict[str, Optional[str]]] = []
    recent_procedures: List[Dict[str, Optional[str]]] = []

    def _vaccine_name(rec: Dict) -> str:
        vc = rec.get("vaccineCode") or {}
        name = vc.get("text") or ""
        if not name:
            for c in vc.get("coding") or []:
                name = c.get("display") or c.get("code") or ""
                if name:
                    break
        return name

    def _allergy_category(rec: Dict) -> str:
        categories = rec.get("category") or []
        if isinstance(categories, list) and categories:
            cat = str(categories[0]).lower()
            return {
                "food": "food",
                "environment": "environmental",
                "medication": "drug",
                "biologic": "biologic",
            }.get(cat, cat)
        return "other"

    for e in all_events:
        cat = e.get("category", "")
        cat_counts[cat] += 1
        rec = e.get("original_record") or {}

        if cat == "Diagnoses":
            # Skip entered-in-error
            vs = rec.get("verificationStatus") or {}
            vs_code = next((c.get("code","") for c in (vs.get("coding") or [])), "")
            if vs_code == "entered-in-error":
                continue
            # Only active conditions
            cs = rec.get("clinicalStatus") or {}
            cs_code = next((c.get("code","") for c in (cs.get("coding") or [])), "unknown")
            if cs_code not in ("active", "recurrence", "relapse"):
                continue
            name = _code_text(rec)
            if name and name.lower() not in ("null", "") and name not in active_diagnoses:
                active_diagnoses.append(name)

        elif cat == "Allergies":
            name = _code_text(rec)
            if not name or name.lower() in _ALLERGY_NOISE:
                continue
            if name not in allergies:
                allergies.append(name)
            allergy_entries.append({
                "substance": name,
                "category": _allergy_category(rec),
            })

        elif cat == "Immunizations":
            vaccine = _vaccine_name(rec)
            if vaccine:
                when = rec.get("occurrenceDateTime") or e.get("date") or ""
                recent_immunizations.append({
                    "vaccine": vaccine,
                    "date": when[:10] if when else None,
                })

        elif cat == "Procedures":
            if (rec.get("status") or "").lower() == "entered-in-error":
                continue
            proc_name = _code_text(rec)
            if proc_name:
                when = e.get("date") or ""
                recent_procedures.append({
                    "procedure": proc_name,
                    "date": when[:10] if when else None,
                })

        elif cat == "Medications":
            status = (rec.get("status") or "").lower()
            if not status:
                m = _re.search(
                    r"\((active|stopped|completed|cancelled)\)",
                    e.get("summary") or "",
                    _re.I,
                )
                if m:
                    status = m.group(1).lower()
            if status != "active":
                continue
            med_cc = rec.get("medicationCodeableConcept") or {}
            name = med_cc.get("text") or ""
            if not name:
                for c in (med_cc.get("coding") or []):
                    name = c.get("display") or ""
                    if name:
                        break
            if not name:
                name = (rec.get("medicationReference") or {}).get("display") or ""
            if not name:
                try:
                    from ..services.clinical_fhir.identity import read_ctms_payload

                    stamped = read_ctms_payload(rec)
                    name = str(stamped.get("name") or stamped.get("medicationName") or "")
                except Exception:
                    name = ""
            if name and name not in active_meds:
                active_meds.append(name)

    def _sort_by_date(items: List[Dict[str, Optional[str]]], key: str) -> List[Dict[str, Optional[str]]]:
        return sorted(items, key=lambda x: x.get("date") or "", reverse=True)

    recent_immunizations = _sort_by_date(recent_immunizations, "date")[:6]
    recent_procedures = _sort_by_date(recent_procedures, "date")[:6]

    visit_count = cat_counts.get("Encounters / Visits", 0)
    hosp_count = cat_counts.get("Hospitalizations", 0)
    lab_count = cat_counts.get("Laboratory Results", 0)
    imaging_count = cat_counts.get("Imaging & Radiology", 0)

    def _build_rule_based() -> str:
        return _build_narrative_patient_summary(
            active_diagnoses, active_meds, allergies,
            recent_immunizations, recent_procedures,
            visit_count, hosp_count, lab_count, imaging_count,
        )

    if _SKIP_AI or (ai_state and ai_state.get("disabled")):
        reason = "SKIP_AI=true" if _SKIP_AI else "OpenAI unavailable (429/quota)"
        logger.info("Patient summary (rule-based) | req_id=%s | reason=%s", req_id, reason)
        return _build_rule_based()

    # LLM-based summary — structured patient_data for the clinical overview prompt
    patient_data: Dict[str, Any] = {
        "active_diagnoses": active_diagnoses[:10],
        "active_medications": active_meds[:10],
        "allergies": allergy_entries[:12] or allergies[:12],
        "recent_immunizations": recent_immunizations,
        "recent_procedures": recent_procedures,
    }
    if visit_count or hosp_count:
        patient_data["healthcare_utilization"] = {
            "outpatient_visits": visit_count,
            "hospitalization_records": hosp_count,
        }
    if lab_count or imaging_count:
        patient_data["diagnostic_workup"] = {
            "laboratory_results": lab_count,
            "imaging_studies": imaging_count,
        }

    prompt = _PATIENT_SUMMARY_PROMPT.format(
        patient_data=json.dumps(patient_data, indent=2, default=str),
    )
    try:
        body = {
            "model": _get_openai_model(),
            "temperature": 0,
            "max_tokens": 350,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {_get_openai_key()}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        response_data = resp.json()
        _record_openai_usage(
            ai_state,
            response_data.get("usage") or {},
            feature="patient_summary.overview",
        )
        text = response_data["choices"][0]["message"]["content"].strip()
        usage = response_data.get("usage") or {}
        if _STALE_PATIENT_SUMMARY_RE.search(text):
            logger.warning(
                "Patient summary LLM returned template-like text | req_id=%s — using narrative fallback",
                req_id,
            )
            return _build_rule_based()
        logger.info(
            "Patient summary (LLM) | req_id=%s | chars=%d | tokens=%s+%s",
            req_id, len(text),
            usage.get("prompt_tokens", "?"), usage.get("completion_tokens", "?"),
        )
        return text
    except Exception as exc:
        logger.warning(
            "Patient summary LLM failed | req_id=%s | reason=%s — using rule-based fallback",
            req_id, exc,
        )
        return _build_rule_based()


def _sanitise_resource(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Strip binary/attachment fields recursively before sending to OpenAI."""
    if isinstance(raw, dict):
        return {k: _sanitise_resource(v) for k, v in raw.items() if k not in _BINARY_FIELDS}
    if isinstance(raw, list):
        return [_sanitise_resource(item) for item in raw]
    return raw


def _extract_date(raw_resource: Dict[str, Any]) -> Tuple[Optional[str], str]:
    for path in _DATE_FIELD_PATHS:
        node = raw_resource
        for key in path:
            if isinstance(node, dict):
                node = node.get(key)
            else:
                node = None
                break
        if isinstance(node, str) and node:
            return node, "full"
    return None, "unknown"


def _safe_str(value: Any) -> str:
    """Coerce FHIR primitive to a stripped string; never raises."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, dict):
        return _fhir_concept_text(value)
    return ""


def _fhir_code_text(rec: Dict[str, Any]) -> str:
    if not isinstance(rec, dict):
        return ""
    code = rec.get("code") or {}
    if not isinstance(code, dict):
        return _safe_str(code)
    text = _safe_str(code.get("text"))
    if text and text.lower() != "null":
        return text
    for c in code.get("coding") or []:
        if not isinstance(c, dict):
            continue
        display = _safe_str(c.get("display") or c.get("code"))
        if display and display.lower() != "null":
            return display
    return ""


def _fhir_concept_text(node: Optional[Any]) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        text = node.strip()
        return text if text.lower() != "null" else ""
    if not isinstance(node, dict):
        return _safe_str(node)
    text = _safe_str(node.get("text"))
    if text and text.lower() != "null":
        return text
    for c in node.get("coding") or []:
        if not isinstance(c, dict):
            continue
        display = _safe_str(c.get("display") or c.get("code"))
        if display and display.lower() != "null":
            return display
    return ""


def _fhir_status_code(rec: Dict[str, Any], field: str) -> str:
    node = rec.get(field) or {}
    if isinstance(node, str):
        return node.lower()
    if not isinstance(node, dict):
        return _safe_str(node).lower()
    for c in node.get("coding") or []:
        if not isinstance(c, dict):
            continue
        code = _safe_str(c.get("code")).lower()
        if code:
            return code
    return _safe_str(node.get("text")).lower()


def _fhir_medication_name(rec: Dict[str, Any]) -> str:
    name = _fhir_concept_text(rec.get("medicationCodeableConcept"))
    if name:
        return name
    name = _safe_str(((rec.get("medicationReference") or {}).get("display")))
    if name:
        return name
    concept = (rec.get("medication") or {}).get("concept") or {}
    name = _fhir_concept_text(concept)
    if name:
        return name
    if rec.get("resourceType") == "Medication":
        return _fhir_code_text(rec)
    try:
        from ..services.clinical_fhir.identity import read_ctms_payload

        stamped = read_ctms_payload(rec)
        return str(stamped.get("name") or stamped.get("medicationName") or "")
    except Exception:
        return ""


def _fhir_encounter_class(rec: Dict[str, Any]) -> str:
    cls = rec.get("class") or {}
    display = cls.get("display") or cls.get("code") or ""
    mapping = {
        "AMB": "Ambulatory", "ambulatory": "Ambulatory",
        "IMP": "Inpatient", "inpatient": "Inpatient",
        "EMER": "Emergency", "emergency": "Emergency",
        "HH": "Home Health", "VR": "Virtual", "OBSENC": "Observation",
    }
    return mapping.get(display, display.title() if display else "Visit")


def _fhir_encounter_provider(rec: Dict[str, Any]) -> str:
    for p in rec.get("participant") or []:
        name = (p.get("individual") or {}).get("display") or ""
        if name:
            parts = [x.strip() for x in name.split(",")]
            if len(parts) == 2:
                return f"{parts[1]} {parts[0]}"
            return name
    return ""


def _fhir_encounter_location(rec: Dict[str, Any]) -> str:
    for loc in rec.get("location") or []:
        name = (loc.get("location") or {}).get("display") or ""
        if name:
            return name
    return ""


def _fhir_observation_value(rec: Dict[str, Any]) -> str:
    vq = rec.get("valueQuantity") or {}
    if vq:
        num = vq.get("value")
        unit = vq.get("unit") or vq.get("code") or ""
        if num is not None and str(num) != "":
            return f"{num} {unit}".strip()
    text = (
        _safe_str(rec.get("valueString"))
        or _fhir_concept_text(rec.get("valueCodeableConcept"))
    )
    if text:
        return text
    if "valueBoolean" in rec and rec["valueBoolean"] is not None:
        return str(rec["valueBoolean"])
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
            comp_txt = _safe_str(item.get("valueString")) or _fhir_concept_text(item.get("valueCodeableConcept"))
            if comp_txt:
                parts.append(comp_txt)
    if len(parts) >= 2:
        return f"{parts[0]} / {parts[1]} {unit}".strip()
    if parts:
        return f"{parts[0]} {unit}".strip()
    return ""


def _fhir_observation_reference_range(rec: Dict[str, Any]) -> str:
    for ref in rec.get("referenceRange") or []:
        if not isinstance(ref, dict):
            continue
        text = _safe_str(ref.get("text"))
        if text:
            return text
        low = (ref.get("low") or {}).get("value")
        high = (ref.get("high") or {}).get("value")
        unit = (
            (ref.get("low") or {}).get("unit")
            or (ref.get("high") or {}).get("unit")
            or ref.get("unit")
            or (rec.get("valueQuantity") or {}).get("unit")
            or ""
        )
        if low is not None and high is not None:
            return f"{low} - {high} {unit}".strip()
        if low is not None:
            return f"> {low} {unit}".strip()
        if high is not None:
            return f"< {high} {unit}".strip()
    return ""


def _fhir_observation_interpretation_text(rec: Dict[str, Any]) -> str:
    for interp in rec.get("interpretation") or []:
        if not isinstance(interp, dict):
            continue
        text = interp.get("text") or _fhir_concept_text(interp)
        if text:
            return text
        for c in interp.get("coding") or []:
            code = (c.get("code") or "").upper()
            mapping = {
                "H": "High", "HH": "Critical High", "HU": "High",
                "L": "Low", "LL": "Critical Low", "LU": "Low",
                "A": "Abnormal", "AA": "Critical Abnormal",
                "N": "Normal", "POS": "Positive", "NEG": "Negative",
            }
            if code in mapping:
                return mapping[code]
    return ""


def _date_fragment(date_str: Optional[str]) -> str:
    return date_str[:10] if date_str and len(date_str) >= 10 else ""


def _fhir_human_name(raw: Dict[str, Any]) -> str:
    """Extract display name from FHIR HumanName[] (Practitioner, Patient, etc.)."""
    names = raw.get("name") or []
    if not names or not isinstance(names[0], dict):
        return ""
    n = names[0]
    text = _safe_str(n.get("text"))
    if text:
        return text
    given = " ".join(_safe_str(g) for g in (n.get("given") or []))
    family = _safe_str(n.get("family"))
    return f"{given} {family}".strip()


def _fhir_scalar_text(value: Any) -> str:
    """Coerce FHIR string, CodeableConcept, or Reference.display to plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        text = _fhir_concept_text(value)
        if text:
            return text
        return _safe_str(value.get("display"))
    return _safe_str(value)


def _fhir_any_label(raw: Dict[str, Any]) -> str:
    """Best-effort label from any common FHIR display field (no LLM)."""
    condition = raw.get("condition") or []
    first_condition = condition[0] if isinstance(condition, list) and condition else {}
    for extractor in (
        lambda: _fhir_code_text(raw),
        lambda: _fhir_medication_name(raw),
        lambda: _fhir_concept_text(raw.get("vaccineCode")),
        lambda: _fhir_scalar_text(raw.get("title")),
        lambda: _fhir_scalar_text(raw.get("description")),
        lambda: _fhir_human_name(raw),
        lambda: _fhir_concept_text(raw.get("type")),
        lambda: _fhir_concept_text(raw.get("relationship")),
        lambda: _fhir_concept_text(first_condition.get("code") if isinstance(first_condition, dict) else None),
        lambda: _fhir_concept_text((raw.get("category") or [{}])[0]
                                   if isinstance(raw.get("category"), list) and raw.get("category")
                                   else raw.get("category")),
        lambda: _fhir_concept_text(((raw.get("activity") or [{}])[0].get("detail") or {}).get("code")
                                   if raw.get("activity") else None),
        lambda: _fhir_scalar_text(((raw.get("participant") or [{}])[0].get("member") or {}).get("display")
                                  if raw.get("participant") else ""),
        lambda: _fhir_scalar_text(((raw.get("deviceName") or [{}])[0].get("name")
                                   if raw.get("deviceName") else "")),
        lambda: _fhir_scalar_text(((raw.get("identifier") or [{}])[0].get("value")
                                   if raw.get("identifier") else "")),
    ):
        try:
            label = extractor()
        except (AttributeError, TypeError, IndexError, KeyError):
            continue
        if label and label.lower() not in ("null", "") and not _is_placeholder_text(label):
            return label
    return ""


def _is_placeholder_text(text: str) -> bool:
    if not text or text.lower().strip() in ("null", "unknown", "n/a"):
        return True
    return bool(_PLACEHOLDER_TEXT_RE.search(text))


def _strip_html_text(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<(br|/p|/li|/div|/ul)[^>]*>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _fhir_careplan_narrative(raw: Dict[str, Any]) -> Tuple[str, str]:
    """Return (focus, condition) parsed from CarePlan.text.div."""
    text_node = raw.get("text") or {}
    div = text_node.get("div") if isinstance(text_node, dict) else ""
    if not div:
        return "", ""
    plain = _strip_html_text(div)
    focus = ""
    condition = ""
    m_focus = re.search(r"care plan for\s+([^.]+)", plain, re.IGNORECASE)
    if m_focus:
        focus = m_focus.group(1).strip()
    m_cond = re.search(r"meant to treat\s+([^.]+)", plain, re.IGNORECASE)
    if m_cond:
        condition = m_cond.group(1).strip()
    return focus, condition


def _fhir_careplan_category_label(raw: Dict[str, Any]) -> str:
    skip_labels = {"assess-plan", "assess plan", "longitudinal"}
    for cat in raw.get("category") or []:
        if not isinstance(cat, dict):
            continue
        label = _fhir_concept_text(cat)
        if not label or _is_placeholder_text(label):
            continue
        if label.lower().replace("-", " ") in skip_labels:
            continue
        return label
    return ""


def _fhir_careplan_activity_labels(raw: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    seen: set = set()
    for act in raw.get("activity") or []:
        if not isinstance(act, dict):
            continue
        label = _fhir_concept_text((act.get("detail") or {}).get("code"))
        if label and label not in seen:
            seen.add(label)
            labels.append(label)
    return labels


def _fhir_careplan_location(raw: Dict[str, Any]) -> str:
    for act in raw.get("activity") or []:
        if not isinstance(act, dict):
            continue
        display = _safe_str(((act.get("detail") or {}).get("location") or {}).get("display"))
        if display:
            return display
    return ""


def _build_careplan_summary(
    raw: Dict[str, Any],
    date_part: str = "",
) -> str:
    focus, condition = _fhir_careplan_narrative(raw)
    if not focus:
        focus = _fhir_careplan_category_label(raw)
    if not focus:
        title = _fhir_scalar_text(raw.get("title"))
        if not _is_placeholder_text(title):
            focus = title
    if not focus:
        activities = _fhir_careplan_activity_labels(raw)
        if activities:
            focus = activities[0]
    if not focus:
        desc = _fhir_scalar_text(raw.get("description"))
        if not _is_placeholder_text(desc):
            focus = desc
    if not focus:
        return ""

    headline = f"{focus} for {condition}" if condition else focus
    parts = [f"Care plan: {headline}"]

    activities = _fhir_careplan_activity_labels(raw)
    if activities:
        parts.append(f"activities: {', '.join(activities[:4])}")

    status = _safe_str(raw.get("status"))
    if status:
        parts.append(f"status {status}")

    location = _fhir_careplan_location(raw)
    if location:
        parts.append(f"at {location}")

    period = raw.get("period") or {}
    start = _date_fragment(period.get("start")) or date_part
    end = _date_fragment(period.get("end"))
    if start and end:
        parts.append(f"from {start} to {end}")
    elif start:
        parts.append(f"starting {start}")

    return ". ".join(parts) + "."


def _build_rule_based_summary(
    raw: Dict[str, Any],
    resource_type: str,
    date_str: Optional[str] = None,
) -> str:
    """Build a per-event summary from structured FHIR fields (0 OpenAI tokens)."""
    if not raw:
        return ""

    rt = resource_type.lower().replace(" ", "")
    date_part = _date_fragment(date_str)

    if rt == "condition":
        name = _fhir_code_text(raw)
        if not name:
            return ""
        status = _fhir_status_code(raw, "clinicalStatus") or "unknown"
        parts = [f"The patient has a {status} condition of {name}"]
        if date_part:
            parts.append(f"with onset on {date_part}")
        return ", ".join(parts) + "."

    if rt in {"medicationrequest", "medicationstatement", "medicationorder",
              "medicationdispense", "medication"}:
        name = _fhir_medication_name(raw)
        if not name:
            return ""
        status = raw.get("status") or "unknown"
        dosage = ""
        di = raw.get("dosageInstruction") or []
        if di:
            dosage = _safe_str(di[0].get("text"))
        parts = [f"Medication {name} ({status})"]
        if dosage:
            parts.append(f"dosage: {dosage}")
        if date_part:
            parts.append(f"as of {date_part}")
        return ". ".join(parts) + "."

    if rt == "allergyintolerance":
        name = _fhir_code_text(raw)
        if not name:
            return ""
        categories = raw.get("category") or []
        cat = categories[0].title() if categories else "Allergy"
        reactions = []
        for rxn in raw.get("reaction") or []:
            for mani in rxn.get("manifestation") or []:
                text = _fhir_concept_text(mani if isinstance(mani, dict) else None)
                if text:
                    reactions.append(text)
        parts = [f"{cat} allergy to {name}"]
        if reactions:
            parts.append(f"reactions: {', '.join(reactions[:3])}")
        return ". ".join(parts) + "."

    if rt == "immunization":
        name = _fhir_concept_text(raw.get("vaccineCode"))
        if not name:
            return ""
        when = _date_fragment(raw.get("occurrenceDateTime")) or date_part
        return f"Immunization: {name}" + (f" on {when}" if when else "") + "."

    if rt == "procedure":
        name = _fhir_code_text(raw)
        if not name:
            return ""
        status = raw.get("status") or ""
        when = _date_fragment(raw.get("performedDateTime")) or date_part
        parts = [f"Procedure: {name}"]
        if status:
            parts.append(f"status {status}")
        if when:
            parts.append(f"performed {when}")
        return ". ".join(parts) + "."

    if rt in {"diagnosticreport", "imagingstudy"}:
        name = _fhir_code_text(raw)
        if not name:
            return ""
        status = raw.get("status") or ""
        when = _date_fragment(raw.get("effectiveDateTime")) or date_part
        parts = [f"{resource_type}: {name}"]
        if status:
            parts.append(f"status {status}")
        if when:
            parts.append(f"effective {when}")
        return ". ".join(parts) + "."

    if rt == "observation":
        name = _fhir_code_text(raw)
        value = _fhir_observation_value(raw)
        if not name and not value:
            return ""
        obs_cat = _fhir_observation_category_code(raw)
        if obs_cat == "social-history":
            return f"Social History: {name} - {value}." if name and value else f"Social History: {name or value}."
        if obs_cat == "survey":
            return f"Clinical Assessment: {name}: {value}." if name and value else f"Assessment: {name or value}."
        interp = _fhir_observation_interpretation_text(raw)
        ref = _fhir_observation_reference_range(raw)
        details = []
        if interp and interp.lower() != "normal":
            details.append(interp)
        if ref:
            details.append(f"Ref: {ref}")
        detail_str = f" ({', '.join(details)})" if details else ""
        if name and value:
            return f"Observation {name}: {value}{detail_str}."
        return f"Observation: {name or value}{detail_str}."

    if rt == "encounter":
        enc_class = _fhir_encounter_class(raw)
        provider = _fhir_encounter_provider(raw)
        location = _fhir_encounter_location(raw)
        parts = [f"{enc_class} encounter"]
        if provider:
            parts.append(f"with {provider}")
        if location:
            parts.append(f"at {location}")
        if date_part:
            parts.append(f"on {date_part}")
        return " ".join(parts) + "."

    if rt == "careplan":
        return _build_careplan_summary(raw, date_part)

    if rt == "familymemberhistory":
        rel = _fhir_concept_text(raw.get("relationship"))
        cond = ""
        for item in raw.get("condition") or []:
            if isinstance(item, dict):
                cond = _fhir_concept_text(item.get("code"))
                if cond:
                    break
        if not rel and not cond:
            return ""
        parts = ["Family history"]
        if rel:
            parts.append(f"relationship: {rel}")
        if cond:
            parts.append(f"condition: {cond}")
        return ". ".join(parts) + "."

    if rt in _AI_NARRATIVE_TYPES:
        # Title-only fallback when SKIP_AI; narrative types normally use LLM.
        name = _fhir_any_label(raw)
        if not name:
            return ""
        status = raw.get("status") or ""
        parts = [f"{resource_type}: {name}"]
        if status:
            parts.append(f"status {status}")
        if date_part:
            parts.append(f"dated {date_part}")
        return ". ".join(parts) + "."

    # Generic fallback — title, name, code, etc. (never LLM for these)
    name = _fhir_any_label(raw)
    if not name:
        return ""
    status = raw.get("status") or ""
    parts = [f"{resource_type}: {name}"]
    if status:
        parts.append(f"status {status}")
    if date_part:
        parts.append(f"dated {date_part}")
    return ". ".join(parts) + "."


def _cache_has_stale_summaries(payload: Dict[str, Any]) -> bool:
    """True when cached data has placeholder or outdated rule-based patient summaries."""
    patient_summary = ((payload.get("patient") or {}).get("summary") or "")
    if _STALE_PATIENT_SUMMARY_RE.search(patient_summary):
        return True
    for ev in payload.get("timeline") or []:
        if _STALE_SUMMARY_RE.search(ev.get("summary") or ""):
            return True
    return False


def _minimal_event_summary(
    resource_type: str,
    row: Dict[str, Any],
    raw: Dict[str, Any],
) -> str:
    """Last-resort summary when rule-based extraction finds no FHIR label."""
    label = _fhir_any_label(raw)
    if label:
        return f"{resource_type}: {label}."
    ref = row.get("resource_id") or row.get("id") or "unknown"
    return f"{resource_type} record (ref {str(ref)[:16]})."


def _parse_raw_resource(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("raw_resource")
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    return raw if isinstance(raw, dict) else {}


def _summarise_table_hybrid(
    rows: List[Dict[str, Any]],
    resource_type: str,
    req_id: str = "",
    ai_state: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, str], int]:
    """
    Hybrid summarisation per docs/EHR_SUMMARY_TOKEN_OPTIMIZATION.md:
      Bucket 1 — RULE_BASED_TYPES → FHIR templates, never OpenAI
      Bucket 2 — AI_NARRATIVE_TYPES only → OpenAI for clinical note text
      All other types → rule-based only (no opaque-record AI leak)
    Returns ({record_id: summary_text}, ai_records_queued).
    """
    summaries: Dict[str, str] = {}
    ai_rows: List[Dict[str, Any]] = []
    rt = resource_type.lower().replace(" ", "")

    for row in rows:
        record_id = row.get("resource_id") or str(row["id"])
        raw = _parse_raw_resource(row)
        date_str, _ = _extract_date(raw)

        # Bucket 2 — narrative clinical notes only (skip if quota exhausted)
        ai_ok = not _SKIP_AI and not (ai_state and ai_state.get("disabled"))
        if ai_ok and rt in _AI_NARRATIVE_TYPES:
            ai_rows.append(row)
            continue

        # Everything else: rule-based only (never OpenAI)
        rule_summary = _build_rule_based_summary(raw, resource_type, date_str)
        if rule_summary:
            summaries[record_id] = rule_summary

    ai_summaries: Dict[str, str] = {}
    if ai_rows:
        ai_summaries = _summarise_records_sequential(
            ai_rows, resource_type, req_id, ai_state=ai_state,
        )
        summaries.update(ai_summaries)

    ai_queued = len(ai_rows)
    logger.info(
        "Hybrid summarise | req_id=%s | resource_type=%s | records=%d | "
        "rule_based=%d | ai_queued=%d | ai_returned=%d",
        req_id, resource_type, len(rows),
        len(summaries) - len(ai_summaries), ai_queued, len(ai_summaries),
    )
    return summaries, ai_queued


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


def _fhir_observation_category_code(raw: Dict[str, Any]) -> str:
    """Return observation category code: vital-signs, social-history, survey, laboratory, or empty."""
    for cat in raw.get("category") or []:
        if isinstance(cat, str):
            code = cat.strip().lower().replace("_", "-")
            if code in ("vital-signs", "vitals"):
                return "vital-signs"
            if code in ("social-history", "socialhistory"):
                return "social-history"
            if code in ("survey", "assessment", "screening"):
                return "survey"
            if code in ("laboratory", "lab"):
                return "laboratory"
            if code in ("imaging", "radiology"):
                return "imaging"
            if code in ("procedure", "exam", "therapy"):
                return "procedure"
        if not isinstance(cat, dict):
            continue
        for coding in cat.get("coding") or []:
            if isinstance(coding, dict):
                code = str(coding.get("code") or "").strip().lower().replace("_", "-")
                if code in ("vital-signs", "vitals"):
                    return "vital-signs"
                if code in ("social-history", "socialhistory"):
                    return "social-history"
                if code in ("survey", "assessment", "screening"):
                    return "survey"
                if code in ("laboratory", "lab"):
                    return "laboratory"
                if code in ("imaging", "radiology"):
                    return "imaging"
                if code in ("procedure", "exam", "therapy"):
                    return "procedure"
        text = str(cat.get("text") or "").strip().lower()
        if "vital" in text:
            return "vital-signs"
        if "social" in text:
            return "social-history"
        if "survey" in text or "assessment" in text or "screening" in text:
            return "survey"
        if "lab" in text:
            return "laboratory"
        if "imaging" in text or "radiology" in text:
            return "imaging"
        if "procedure" in text:
            return "procedure"

    name = (_fhir_code_text(raw) or "").lower()
    if any(hint in name for hint in _VITAL_NAME_HINTS):
        return "vital-signs"
    if any(hint in name for hint in _SOCIAL_HISTORY_HINTS):
        return "social-history"
    if any(hint in name for hint in _SURVEY_ASSESSMENT_HINTS):
        return "survey"
    return ""


def _event_category(table_name: str, raw: Optional[Dict[str, Any]] = None) -> str:
    """Map a fastenhealth_* row to a summary category; split observations."""
    base = _table_to_category(table_name)
    suffix = table_name.replace("fastenhealth_", "").lower()
    if suffix != "observation":
        return base
    code = _fhir_observation_category_code(raw or {})
    if code == "vital-signs":
        return "Vital Signs"
    if code == "social-history":
        return "Social History"
    if code in ("survey", "assessment"):
        return "Clinical Assessments & Surveys"
    if code in ("imaging", "radiology"):
        return "Imaging & Radiology"
    if code in ("procedure", "exam", "therapy"):
        return "Procedures"
    return "Laboratory Results"


def _table_to_resource_type(table_name: str) -> str:
    suffix = table_name.replace("fastenhealth_", "")
    return suffix.capitalize() if "_" not in suffix else suffix


def _table_to_category(table_name: str) -> str:
    suffix = table_name.replace("fastenhealth_", "").lower()
    return _CATEGORY_MAP.get(suffix, _DEFAULT_CATEGORY)


def _extract_patient_info(patient_row: Dict[str, Any]) -> PatientInfo:
    raw = patient_row.get("raw_resource") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}

    name_str: Optional[str] = None
    names = raw.get("name") or []
    if names:
        first_name = names[0]
        family = first_name.get("family", "")
        given = " ".join(first_name.get("given") or [])
        name_str = f"{given} {family}".strip() or None

    # Authorized Clinician Egress: If name contains surrogate tokens (e.g. GIVEN_, FAM_), reverse it
    if name_str and ("GIVEN_" in name_str or "FAM_" in name_str):
        try:
            from ..services.privacy.privacy_client import privacy_client
            restored = privacy_client.restore_text(
                name_str, purpose="patient_care", org_id=str(patient_row.get("patient_id") or "default")
            )
            if restored:
                name_str = restored
        except Exception as e:
            logger.debug("Clinician name egress restoral fallback: %s", e)

    return PatientInfo(
        patient_id=patient_row["patient_id"],
        hekma_mail_id=patient_row.get("hekma_mail_id"),
        name=name_str,
        birth_date=raw.get("birthDate"),
        gender=raw.get("gender"),
    )


# ---------------------------------------------------------------------------
# OpenAI — single sequential call with retry+backoff
# ---------------------------------------------------------------------------

def _call_openai_batch(
    records: List[Dict[str, Any]],
    resource_type: str,
    req_id: str = "",
    batch_num: int = 1,
    total_batches: int = 1,
    ai_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Send one batch to OpenAI with exponential-backoff retry.
    Called strictly sequentially — never from multiple threads simultaneously.
    Returns {record_id: summary_text}.  Never raises.
    """
    if ai_state and ai_state.get("disabled"):
        return {}

    batch_size = len(records)
    payload_list = [
        {
            "record_id": r["resource_id"] or str(r["id"]),
            "data": _sanitise_resource(r["raw_resource"] or {}),
        }
        for r in records
    ]

    records_json = json.dumps(payload_list, default=str)
    payload_chars = len(records_json)

    logger.debug(
        "OpenAI batch | req_id=%s | resource_type=%s | batch=%d/%d | "
        "records=%d | payload_chars=%d | model=%s",
        req_id, resource_type, batch_num, total_batches,
        batch_size, payload_chars, _get_openai_model(),
    )

    if payload_chars > _MAX_PAYLOAD_CHARS:
        logger.warning(
            "OpenAI payload truncated | req_id=%s | resource_type=%s | batch=%d | "
            "original_chars=%d | limit=%d",
            req_id, resource_type, batch_num, payload_chars, _MAX_PAYLOAD_CHARS,
        )
        records_json = records_json[:_MAX_PAYLOAD_CHARS] + "... [truncated]"

    body = {
        "model": _get_openai_model(),
        "temperature": 0,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_PROMPT_TEMPLATE.format(
                resource_type=resource_type,
                records_json=records_json,
            )},
        ],
    }

    last_exc: Exception = RuntimeError("No attempts made")

    for attempt in range(1, _OPENAI_MAX_RETRIES + 1):
        if attempt > 1:
            # Exponential backoff: 15 s, 30 s, 60 s …
            backoff = _OPENAI_RETRY_BASE_DELAY * (2 ** (attempt - 2))
            logger.warning(
                "OpenAI retry | req_id=%s | resource_type=%s | batch=%d/%d | "
                "attempt=%d/%d | backoff=%.0fs | reason=%s",
                req_id, resource_type, batch_num, total_batches,
                attempt, _OPENAI_MAX_RETRIES, backoff, last_exc,
            )
            time.sleep(backoff)

        t0 = time.perf_counter()
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {_get_openai_key()}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=120,
            )
            resp.raise_for_status()
            elapsed = time.perf_counter() - t0

            response_data = resp.json()
            usage = response_data.get("usage", {})
            _record_openai_usage(
                ai_state, usage, feature="patient_summary.narrative_batch"
            )
            text = (response_data["choices"][0]["message"]["content"] or "").strip()
            cleaned = text.replace("```json", "").replace("```", "").strip()
            items = json.loads(cleaned)
            summaries = {item["record_id"]: item["summary"] for item in items}

            logger.info(
                "OpenAI batch OK | req_id=%s | resource_type=%s | batch=%d/%d | "
                "attempt=%d | records=%d | summaries=%d | elapsed=%.2fs | "
                "tokens=%s+%s",
                req_id, resource_type, batch_num, total_batches, attempt,
                batch_size, len(summaries), elapsed,
                usage.get("prompt_tokens", "?"), usage.get("completion_tokens", "?"),
            )

            # Polite inter-call pause — keeps us under the per-minute RPM limit.
            if _OPENAI_INTER_CALL_DELAY > 0:
                logger.debug(
                    "OpenAI inter-call delay | req_id=%s | sleep=%.1fs",
                    req_id, _OPENAI_INTER_CALL_DELAY,
                )
                time.sleep(_OPENAI_INTER_CALL_DELAY)

            return summaries

        except requests.exceptions.Timeout as exc:
            elapsed = time.perf_counter() - t0
            last_exc = exc
            logger.warning(
                "OpenAI timeout | req_id=%s | resource_type=%s | batch=%d/%d | "
                "attempt=%d/%d | elapsed=%.2fs",
                req_id, resource_type, batch_num, total_batches,
                attempt, _OPENAI_MAX_RETRIES, elapsed,
            )

        except requests.exceptions.HTTPError as exc:
            elapsed = time.perf_counter() - t0
            last_exc = exc
            status = exc.response.status_code if exc.response is not None else "?"

            if status == 429:
                if _FAIL_FAST_ON_429 and ai_state is not None:
                    ai_state["disabled"] = True
                    logger.warning(
                        "OpenAI 429 — quota/rate limit; disabling further AI for this request | "
                        "req_id=%s | resource_type=%s | batch=%d/%d",
                        req_id, resource_type, batch_num, total_batches,
                    )
                    return {}

                retry_after: Optional[float] = None
                if exc.response is not None:
                    hdr = exc.response.headers.get("Retry-After")
                    if hdr:
                        try:
                            retry_after = float(hdr)
                        except ValueError:
                            pass

                logger.warning(
                    "OpenAI rate limited (429) | req_id=%s | resource_type=%s | "
                    "batch=%d/%d | attempt=%d/%d | retry_after=%s | elapsed=%.2fs",
                    req_id, resource_type, batch_num, total_batches,
                    attempt, _OPENAI_MAX_RETRIES,
                    f"{retry_after:.0f}s" if retry_after else "not specified",
                    elapsed,
                )
                # Honour OpenAI's Retry-After header if present.
                if retry_after and attempt < _OPENAI_MAX_RETRIES:
                    logger.info(
                        "Honouring Retry-After | req_id=%s | sleeping=%.0fs",
                        req_id, retry_after,
                    )
                    time.sleep(retry_after)
            else:
                # Non-retriable (400, 401, 403 …)
                logger.error(
                    "OpenAI HTTP error (non-retriable) | req_id=%s | resource_type=%s | "
                    "batch=%d/%d | status=%s | elapsed=%.2fs | error=%s",
                    req_id, resource_type, batch_num, total_batches,
                    status, elapsed, exc,
                )
                return {}

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            last_exc = exc
            logger.error(
                "OpenAI unexpected error | req_id=%s | resource_type=%s | "
                "batch=%d/%d | attempt=%d/%d | elapsed=%.2fs | error=%s",
                req_id, resource_type, batch_num, total_batches,
                attempt, _OPENAI_MAX_RETRIES, elapsed, exc,
            )
            return {}

    logger.error(
        "OpenAI batch EXHAUSTED | req_id=%s | resource_type=%s | batch=%d/%d | "
        "attempts=%d | last_error=%s — using fallback summaries",
        req_id, resource_type, batch_num, total_batches, _OPENAI_MAX_RETRIES, last_exc,
    )
    return {}


def _summarise_records_sequential(
    rows: List[Dict[str, Any]],
    resource_type: str,
    req_id: str = "",
    ai_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Split rows into batches and call OpenAI for each batch IN SEQUENCE.
    No threads.  Returns {record_id: summary_text}.
    When EHR_SUMMARY_SKIP_AI=true, returns {} immediately (callers use fallbacks).
    """
    if _SKIP_AI or (ai_state and ai_state.get("disabled")):
        logger.info(
            "OpenAI skipped | req_id=%s | resource_type=%s | records=%d",
            req_id, resource_type, len(rows),
        )
        return {}

    batches = [rows[i: i + _OPENAI_BATCH_SIZE] for i in range(0, len(rows), _OPENAI_BATCH_SIZE)]
    total_batches = len(batches)

    logger.info(
        "OpenAI summarise | req_id=%s | resource_type=%s | records=%d | batches=%d",
        req_id, resource_type, len(rows), total_batches,
    )

    t0 = time.perf_counter()
    summaries: Dict[str, str] = {}
    for idx, batch in enumerate(batches):
        if ai_state and ai_state.get("disabled"):
            logger.info(
                "OpenAI batches aborted (quota disabled) | req_id=%s | resource_type=%s | "
                "completed=%d/%d",
                req_id, resource_type, idx, total_batches,
            )
            break
        result = _call_openai_batch(
            batch, resource_type, req_id,
            batch_num=idx + 1, total_batches=total_batches,
            ai_state=ai_state,
        )
        summaries.update(result)

    logger.info(
        "OpenAI summarise done | req_id=%s | resource_type=%s | "
        "summaries=%d/%d | elapsed=%.2fs",
        req_id, resource_type, len(summaries), len(rows),
        time.perf_counter() - t0,
    )
    return summaries


# ---------------------------------------------------------------------------
# Core service
# ---------------------------------------------------------------------------

class EHRSummaryService:

    def generate(
        self,
        patient_id: Optional[str] = None,
        email: Optional[str] = None,
        force_refresh: bool = False,
        req_id: str = "",
        include_records: bool = False,
        cache_only: bool = False,
    ) -> EHRSummaryResponse:  # noqa: E501

        if not patient_id and not email:
            raise ValueError("Provide at least one of patient_id or email.")

        req_id = req_id or str(uuid.uuid4())[:8]
        t_total = time.perf_counter()

        logger.info(
            "EHR summary generate start | req_id=%s | patient_id=%s | email=%s | "
            "force_refresh=%s | skip_ai=%s | include_records=%s | cache_only=%s",
            req_id, patient_id, email, force_refresh, _SKIP_AI, include_records, cache_only,
        )

        # ── Phase 0: Resolve patient ─────────────────────────────────────────
        t1 = time.perf_counter()
        patient_row = self._resolve_patient(patient_id, email)
        if not patient_row:
            logger.warning(
                "Patient not found | req_id=%s | patient_id=%s | email=%s",
                req_id, patient_id, email,
            )
            raise LookupError("Patient not found.")

        resolved_pid = patient_row["patient_id"]
        patient_info = _extract_patient_info(patient_row)

        logger.info(
            "Patient resolved | req_id=%s | patient_id=%s | name=%s | gender=%s | dob=%s | elapsed=%.3fs",
            req_id, resolved_pid,
            patient_info.name, patient_info.gender, patient_info.birth_date,
            time.perf_counter() - t1,
        )

        # ── Phase 1: Cache read (always first unless force_refresh) ────────
        if not force_refresh:
            t2 = time.perf_counter()
            logger.debug("Checking cache | req_id=%s | patient_id=%s", req_id, resolved_pid)
            cached = _lookup_patient_cache(resolved_pid, include_records, req_id=req_id)
            cache_elapsed = time.perf_counter() - t2

            if cached:
                if _cache_has_stale_summaries(cached["data"]):
                    logger.warning(
                        "Cache HIT rejected — stale placeholder summaries detected | "
                        "req_id=%s | patient_id=%s | generated_at=%s — regenerating",
                        req_id, resolved_pid, cached["generated_at"],
                    )
                else:
                    logger.info(
                        "Cache HIT | req_id=%s | patient_id=%s | records=%d | "
                        "generated_at=%s | expires_at=%s | age=%.0fs | ttl_remaining=%.0fs | lookup=%.3fs",
                        req_id, resolved_pid,
                        cached["record_count"],
                        cached["generated_at"],
                        cached["expires_at"],
                        (datetime.utcnow() - datetime.fromisoformat(cached["generated_at"])).total_seconds(),
                        (datetime.fromisoformat(cached["expires_at"]) - datetime.utcnow()).total_seconds(),
                        cache_elapsed,
                    )
                    response = _build_cache_hit_response(cached, include_records)
                    response = overlay_live_hekma_records(
                        response, resolved_pid, include_records, req_id=req_id,
                    )
                    logger.info(
                        "EHR summary complete (cache HIT) | req_id=%s | patient_id=%s | "
                        "include_records=%s | openai_tokens=0 | total_elapsed=%.3fs",
                        req_id, resolved_pid, include_records, time.perf_counter() - t_total,
                    )
                    return response

            if cache_only:
                logger.info(
                    "Cache-only request with no valid cache | req_id=%s | patient_id=%s | lookup=%.3fs",
                    req_id, resolved_pid, cache_elapsed,
                )
                raise LookupError(
                    "No cached EHR summary found for this patient. "
                    "Call POST /api/patients/ehr-summary first, or pass force_refresh=true."
                )

            logger.info(
                "Cache MISS | req_id=%s | patient_id=%s | cache_lookup=%.3fs — generating fresh summary",
                req_id, resolved_pid, cache_elapsed,
            )
        else:
            logger.info(
                "Cache bypassed (force_refresh=True) | req_id=%s | patient_id=%s",
                req_id, resolved_pid,
            )

        # Record the moment generation begins so that store_cached_summary can
        # detect a mid-flight invalidation: if a Fasten ingest soft-deletes the
        # cache (bumping updated_at) after this point, the conditional upsert
        # WHERE guard will block the stale write.
        generation_start = datetime.now(timezone.utc)
        ai_state: Dict[str, Any] = _new_ai_state()
        ai_state["patient_id"] = resolved_pid
        ai_state["request_id"] = req_id

        # ── Phase 2: Discover tables ─────────────────────────────────────────
        t3 = time.perf_counter()
        tables = list_fastenhealth_tables()
        logger.info(
            "Tables discovered | req_id=%s | patient_id=%s | count=%d | elapsed=%.3fs",
            req_id, resolved_pid, len(tables), time.perf_counter() - t3,
        )

        # ── Phase 3: Parallel DB fetch (no OpenAI here) ──────────────────────
        t4 = time.perf_counter()
        logger.info(
            "DB fetch phase start | req_id=%s | patient_id=%s | tables=%d | workers=%d",
            req_id, resolved_pid, len(tables), min(len(tables), 10) or 1,
        )

        # Collect (table_name, rows) pairs; skip tables with 0 rows.
        table_data: List[Tuple[str, List[Dict[str, Any]]]] = []

        def _fetch_table(tbl: str) -> Tuple[str, List[Dict[str, Any]]]:
            rows = get_patient_records_from_table(resolved_pid, tbl)
            return tbl, rows

        max_db_workers = min(len(tables), 10) or 1
        with ThreadPoolExecutor(max_workers=max_db_workers) as pool:
            fetch_futures = {pool.submit(_fetch_table, t): t for t in tables}
            for future in as_completed(fetch_futures):
                tbl = fetch_futures[future]
                try:
                    tbl_name, rows = future.result()
                    if rows:
                        table_data.append((tbl_name, rows))
                        logger.debug(
                            "DB fetch collected | req_id=%s | table=%s | rows=%d",
                            req_id, tbl_name, len(rows),
                        )
                    else:
                        logger.debug(
                            "DB fetch empty | req_id=%s | table=%s | skipped",
                            req_id, tbl,
                        )
                except Exception as exc:
                    logger.warning(
                        "DB fetch failed | req_id=%s | table=%s | error=%s",
                        req_id, tbl, exc,
                    )

        total_db_rows = sum(len(r) for _, r in table_data)
        logger.info(
            "DB fetch phase complete | req_id=%s | patient_id=%s | tables_with_data=%d | "
            "total_rows=%d | elapsed=%.2fs",
            req_id, resolved_pid, len(table_data), total_db_rows,
            time.perf_counter() - t4,
        )

        # ── Phase 4: Hybrid summarisation + event building ───────────────────
        t5 = time.perf_counter()
        logger.info(
            "Summarise phase start | req_id=%s | patient_id=%s | tables=%d | "
            "skip_ai=%s | inter_call_delay=%.1fs | retry_base=%.0fs",
            req_id, resolved_pid, len(table_data),
            _SKIP_AI, _OPENAI_INTER_CALL_DELAY, _OPENAI_RETRY_BASE_DELAY,
        )

        all_events: List[TimelineEvent] = []
        total_ai_records = 0

        for table_name, rows in table_data:
            resource_type = _table_to_resource_type(table_name)
            t_tbl = time.perf_counter()

            summary_map, ai_queued = _summarise_table_hybrid(
                rows, resource_type, req_id, ai_state=ai_state,
            )
            total_ai_records += ai_queued

            logger.info(
                "Table progress | req_id=%s | table=%s | rows=%d | "
                "summaries=%d | table_elapsed=%.2fs",
                req_id, table_name, len(rows),
                len(summary_map), time.perf_counter() - t_tbl,
            )

            # Build timeline events for this table.
            fallback_count = 0
            for row in rows:
                record_id = row.get("resource_id") or str(row["id"])
                raw = _parse_raw_resource(row)

                date_str, date_precision = _extract_date(raw)
                ai_summary = summary_map.get(record_id, "")

                if not ai_summary:
                    fallback_count += 1
                    ai_summary = _build_rule_based_summary(raw, resource_type, date_str)
                if not ai_summary:
                    ai_summary = _minimal_event_summary(resource_type, row, raw)
                    logger.debug(
                        "Minimal summary fallback | req_id=%s | table=%s | record_id=%s",
                        req_id, table_name, record_id,
                    )

                all_events.append(TimelineEvent(
                    event_id=str(uuid.uuid4()),
                    category=_event_category(table_name, raw),
                    resource_type=resource_type,
                    source_table=table_name,
                    resource_id=record_id,
                    date=date_str,
                    date_precision=date_precision,
                    summary=ai_summary,
                    original_record=raw,
                    db_row_id=row["id"],
                ))

            if fallback_count:
                logger.info(
                    "Fallback summaries used | req_id=%s | table=%s | fallbacks=%d/%d",
                    req_id, table_name, fallback_count, len(rows),
                )

        estimated_ai_batches = (
            -(-total_ai_records // _OPENAI_BATCH_SIZE) if total_ai_records else 0
        )
        logger.info(
            "Summarise phase complete | req_id=%s | patient_id=%s | total_events=%d | "
            "ai_records=%d | est_ai_batches=%d | patient_overview_llm=%s | "
            "openai_disabled=%s | elapsed=%.2fs",
            req_id, resolved_pid, len(all_events),
            total_ai_records, estimated_ai_batches,
            "yes" if not _SKIP_AI and not ai_state.get("disabled") else "no",
            ai_state.get("disabled", False),
            time.perf_counter() - t5,
        )

        # ── Phase 5: Sort + group ────────────────────────────────────────────
        overlay_events, retired_keys = collect_hekma_overlay_events(resolved_pid, req_id)
        if overlay_events or retired_keys:
            all_events, _ = merge_timeline(all_events, overlay_events, retired_keys)
            logger.info(
                "Hekma records merged before patient overview | req_id=%s | patient_id=%s | "
                "overlay_events=%d | retired=%d | timeline=%d",
                req_id,
                resolved_pid,
                len(overlay_events),
                len(retired_keys),
                len(all_events),
            )

        all_events.sort(key=lambda e: (e.date is None, e.date or ""))
        categories = self._group_by_category(all_events)
        cat_summary = {c.category: c.event_count for c in categories}
        logger.info(
            "Category grouping | req_id=%s | patient_id=%s | categories=%s",
            req_id, resolved_pid, cat_summary,
        )

        # ── Phase 5b: Patient overview summary ──────────────────────────────
        patient_info.summary = _generate_patient_summary(
            patient_info=patient_info,
            all_events=[e.model_dump(mode="json") for e in all_events],
            req_id=req_id,
            ai_state=ai_state,
        )

        # ── Phase 6: Build response ──────────────────────────────────────────
        openai_usage = _usage_from_ai_state(ai_state)
        response = EHRSummaryResponse(
            patient=patient_info,
            generated_at=datetime.now(timezone.utc).isoformat(),
            total_records_processed=len(all_events),
            timeline=all_events,
            categories=categories,
            cache_hit=False,
            openai_usage=openai_usage,
        )

        # ── Phase 7: Persist to cache (guarded against mid-flight invalidation) ─
        t7 = time.perf_counter()
        stored = store_cached_summary(
            patient_id=resolved_pid,
            summary_dict=response.model_dump(mode="json"),
            record_count=len(all_events),
            generation_start=generation_start,
        )
        if stored:
            logger.debug(
                "Cache store OK | req_id=%s | patient_id=%s | elapsed=%.3fs",
                req_id, resolved_pid, time.perf_counter() - t7,
            )
        else:
            logger.warning(
                "Cache store skipped | req_id=%s | patient_id=%s | "
                "Cache was invalidated mid-flight (new EHR ingest?) — "
                "response returned to caller but NOT cached; next request will regenerate.",
                req_id, resolved_pid,
            )

        logger.info(
            "EHR summary complete (fresh) | req_id=%s | patient_id=%s | "
            "total_records=%d | openai_tokens=%d (prompt=%d completion=%d) | "
            "llm_calls=%d | total_elapsed=%.2fs",
            req_id, resolved_pid, len(all_events),
            openai_usage.total_tokens,
            openai_usage.prompt_tokens,
            openai_usage.completion_tokens,
            openai_usage.llm_calls,
            time.perf_counter() - t_total,
        )
        if not include_records:
            response = EHRSummaryResponse.model_validate(
                strip_original_records(response.model_dump(mode="json"))
            )
        response = overlay_live_hekma_records(
            response, resolved_pid, include_records, req_id=req_id,
        )
        return response

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_patient(
        self, patient_id: Optional[str], email: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Resolve by current patient_id only. Email never replaces a given id."""
        from ..ehr_apis.ctms_patient_ids import resolve_chart_patient_id

        chart_id = resolve_chart_patient_id(patient_id, email)
        if not chart_id:
            return None

        row = get_patient_by_id(chart_id)
        if row:
            return row

        ctms = get_ctms_patient_identity(chart_id, None)
        resolved_id = chart_id
        if ctms and ctms.get("patientId") is not None:
            resolved_id = str(ctms.get("patientId"))
        if not resolved_id:
            return None

        logger.info(
            "Patient resolved without Fasten EHR row | patient_id=%s | ctms=%s",
            resolved_id,
            bool(ctms),
        )
        return stub_patient_row(
            resolved_id,
            email=(ctms or {}).get("email") or email,
            first_name=(ctms or {}).get("firstName"),
            last_name=(ctms or {}).get("lastName"),
        )

    def _group_by_category(self, events: List[TimelineEvent]) -> List[CategoryGroup]:
        grouped: Dict[str, List[TimelineEvent]] = {}
        for ev in events:
            grouped.setdefault(ev.category, []).append(ev)

        ORDER = [
            "Encounters / Visits", "Diagnoses", "Medications", "Procedures",
            "Laboratory Results", "Vital Signs", "Social History",
            "Clinical Assessments & Surveys", "Imaging & Radiology", "Allergies",
            "Immunizations", "Clinical Notes", "Hospitalizations", "Other Health Events",
        ]

        result: List[CategoryGroup] = []
        seen: set = set()
        for cat in ORDER:
            if cat in grouped:
                result.append(CategoryGroup(
                    category=cat,
                    event_count=len(grouped[cat]),
                    events=grouped[cat],
                ))
                seen.add(cat)
        for cat, evs in grouped.items():
            if cat not in seen:
                result.append(CategoryGroup(category=cat, event_count=len(evs), events=evs))
        return result
