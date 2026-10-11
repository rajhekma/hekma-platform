"""
Live overlay of manual + scan records onto a cached EHR summary.

EHR poll data stays in the PostgreSQL cache (no extra OpenAI cost).
Manual plus-button and document-scan rows are cheap to summarise from FHIR
fields, so every summary request re-reads them and merges them in.

"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from ..schemas.ehr_summary_schemas import (
    CategoryGroup,
    EHRSummaryResponse,
    TimelineEvent,
)
from .ehr_summary_cache_repo import strip_original_records
from .ehr_summary_repository import (
    fetch_active_adherence_medications,
    fetch_hekma_source_records,
)

logger = logging.getLogger(__name__)

_CATEGORY_ORDER = [
    "Encounters / Visits",
    "Diagnoses",
    "Medications",
    "Procedures",
    "Laboratory Results",
    "Vital Signs",
    "Social History",
    "Clinical Assessments & Surveys",
    "Imaging & Radiology",
    "Allergies",
    "Immunizations",
    "Clinical Notes",
    "Hospitalizations",
    "Other Health Events",
]

EventKey = Tuple[str, str]


def collect_hekma_overlay_events(
    patient_id: str, req_id: str = ""
) -> Tuple[List[TimelineEvent], Set[EventKey]]:
    """Build timeline events from manual/scan fastenhealth_* rows (incl. medicationrequest)."""
    return _collect_overlay_events(patient_id, req_id)


def refresh_patient_summary_from_timeline(
    response: EHRSummaryResponse,
    *,
    req_id: str = "",
    force_rule_based: bool = False,
) -> EHRSummaryResponse:
    """
    Rebuild patient.summary from the merged timeline (EHR + manual/scan FHIR).

    Uses rule-based overview when the cached summary must be refreshed without
    an extra OpenAI call (overlay on cache hit), or when force_rule_based=True.
    """
    if not response.timeline:
        return response
    from .ehr_summary_service import _SKIP_AI, _generate_patient_summary

    use_rule_based = force_rule_based or response.cache_hit or _SKIP_AI
    ai_state = {"disabled": True} if use_rule_based else None
    summary = _generate_patient_summary(
        patient_info=response.patient,
        all_events=[e.model_dump(mode="json") for e in response.timeline],
        req_id=req_id,
        ai_state=ai_state,
    )
    patient = response.patient.model_copy(update={"summary": summary})
    return response.model_copy(update={"patient": patient})


def overlay_live_hekma_records(
    response: EHRSummaryResponse,
    patient_id: str,
    include_records: bool,
    req_id: str = "",
) -> EHRSummaryResponse:
    """
    Merge current manual/scan records into *response* without calling OpenAI.

    Fail-open: any overlay error returns the original response unchanged.
    """
    try:
        overlay_events, retired_keys = _collect_overlay_events(patient_id, req_id)
        if not overlay_events and not retired_keys:
            logger.debug(
                "Hekma overlay unchanged | req_id=%s | patient_id=%s",
                req_id, patient_id,
            )
            return response
        merged, added = merge_timeline(response.timeline, overlay_events, retired_keys)

        merged.sort(key=lambda e: (e.date is None, e.date or ""))
        payload = response.model_dump(mode="json")
        payload["timeline"] = [e.model_dump(mode="json") for e in merged]
        payload["categories"] = [
            c.model_dump(mode="json") for c in _group_by_category(merged)
        ]
        payload["total_records_processed"] = len(merged)
        payload["openai_usage"] = response.openai_usage.model_dump()
        logger.info(
            "Hekma overlay applied | req_id=%s | patient_id=%s | added=%d | "
            "retired=%d | timeline=%d",
            req_id, patient_id, len(added), len(retired_keys), len(merged),
        )
        merged_response = EHRSummaryResponse.model_validate(payload)
        if response.cache_hit and (overlay_events or retired_keys or added):
            merged_response = refresh_patient_summary_from_timeline(
                merged_response, req_id=req_id, force_rule_based=True,
            )
        if not include_records:
            payload = merged_response.model_dump(mode="json")
            payload = strip_original_records(payload)
            merged_response = EHRSummaryResponse.model_validate(payload)
        return merged_response
    except Exception as exc:
        logger.warning(
            "Hekma overlay failed (serving cached EHR snapshot) | req_id=%s | "
            "patient_id=%s | error=%s",
            req_id, patient_id, exc,
        )
        return response


def merge_timeline(
    cached: List[TimelineEvent],
    overlay: List[TimelineEvent],
    retired_keys: Iterable[EventKey],
) -> Tuple[List[TimelineEvent], List[TimelineEvent]]:
    """
    Overlay wins on (source_table, resource_id). Retired keys are dropped.
    Returns (merged_events, newly_added_overlay_events).
    """
    overlay_by_key = {_event_key(ev): ev for ev in overlay}
    retired = set(retired_keys)
    cached_keys = {_event_key(ev) for ev in cached}

    merged: List[TimelineEvent] = []
    for ev in cached:
        key = _event_key(ev)
        if key in retired:
            continue
        if key in overlay_by_key:
            merged.append(overlay_by_key[key])
            continue
        merged.append(ev)

    added: List[TimelineEvent] = []
    for key, ev in overlay_by_key.items():
        if key in retired:
            continue
        if key not in cached_keys:
            merged.append(ev)
            added.append(ev)
    return merged, added


def _collect_overlay_events(
    patient_id: str, req_id: str
) -> Tuple[List[TimelineEvent], Set[EventKey]]:
    from .ehr_summary_service import (
        _build_rule_based_summary,
        _event_category,
        _extract_date,
        _minimal_event_summary,
        _parse_raw_resource,
        _table_to_resource_type,
    )

    fhir_by_table = fetch_hekma_source_records(patient_id)
    events: List[TimelineEvent] = []
    retired: Set[EventKey] = set()
    known_ids: Set[str] = set()

    linked_fhir_med_ids: Set[str] = set()
    for table_name, rows in fhir_by_table.items():
        resource_type = _table_to_resource_type(table_name)
        for row in rows:
            raw = _parse_raw_resource(row)
            record_id = str(row.get("resource_id") or row.get("id") or "")
            if record_id:
                known_ids.add(record_id)
            if table_name == "fastenhealth_medicationrequest" and record_id:
                linked_fhir_med_ids.add(record_id)
            key = (table_name, record_id)
            if _fhir_is_retired(raw):
                retired.add(key)
                continue
            events.append(
                _event_from_row(
                    row,
                    table_name=table_name,
                    resource_type=resource_type,
                    category=_event_category(table_name, raw),
                    parse_raw=_parse_raw_resource,
                    extract_date=_extract_date,
                    rule_summary=_build_rule_based_summary,
                    minimal_summary=_minimal_event_summary,
                )
            )

    events.extend(
        _collect_adherence_medication_events(
            patient_id,
            linked_fhir_med_ids=linked_fhir_med_ids,
            build_rule_summary=_build_rule_based_summary,
            extract_date=_extract_date,
            minimal_summary=_minimal_event_summary,
        )
    )

    return events, retired


def _collect_adherence_medication_events(
    patient_id: str,
    *,
    linked_fhir_med_ids: Set[str],
    build_rule_summary,
    extract_date,
    minimal_summary,
) -> List[TimelineEvent]:
    """Timeline events from Postgres ``medications`` when FHIR projection is missing."""
    from ..services.clinical_fhir.identity import stamp_ctms_payload, stamp_hekma_identifiers
    from ..services.clinical_fhir.mappers import MedicationRequestMapper
    from ..services.medications.fhir_dual_write import (
        infer_medication_clinical_source,
        medication_row_to_fhir_record,
    )

    mapper = MedicationRequestMapper()
    overlay: List[TimelineEvent] = []
    for med in fetch_active_adherence_medications(patient_id):
        hekma_id = str(med.get("hekma_id") or "").strip()
        if hekma_id and hekma_id in linked_fhir_med_ids:
            continue
        payload = medication_row_to_fhir_record(med)
        source = infer_medication_clinical_source(med)
        raw = mapper.to_fhir(str(patient_id), payload)
        raw = stamp_hekma_identifiers(
            raw,
            hekma_id=hekma_id or f"med-{med.get('id')}",
            fhir_id=hekma_id or f"med-{med.get('id')}",
            source=source,
        )
        raw = stamp_ctms_payload(raw, payload)
        date_str, date_precision = extract_date(raw)
        summary = build_rule_summary(raw, "MedicationRequest", date_str) or minimal_summary(
            "MedicationRequest",
            {"id": med.get("id"), "resource_id": str(med.get("id"))},
            raw,
        )
        overlay.append(
            TimelineEvent(
                event_id=str(uuid.uuid4()),
                category="Medications",
                resource_type="MedicationRequest",
                source_table="medications",
                resource_id=str(med.get("id") or ""),
                date=date_str,
                date_precision=date_precision,
                summary=summary,
                original_record=raw,
                db_row_id=int(med.get("id") or 0),
            )
        )
    return overlay


def _event_from_row(
    row: Dict[str, Any],
    *,
    table_name: str,
    resource_type: str,
    category: str,
    parse_raw,
    extract_date,
    rule_summary,
    minimal_summary,
) -> TimelineEvent:
    raw = parse_raw(row)
    date_str, date_precision = extract_date(raw)
    summary = rule_summary(raw, resource_type, date_str) or minimal_summary(
        resource_type, row, raw
    )
    try:
        db_row_id = int(row.get("id") or 0)
    except (TypeError, ValueError):
        db_row_id = 0
    return TimelineEvent(
        event_id=str(uuid.uuid4()),
        category=category,
        resource_type=resource_type,
        source_table=table_name,
        resource_id=str(row.get("resource_id") or row.get("id") or ""),
        date=date_str,
        date_precision=date_precision,
        summary=summary,
        original_record=raw,
        db_row_id=db_row_id,
    )


def _event_key(ev: TimelineEvent) -> EventKey:
    return (ev.source_table, ev.resource_id)


def _fhir_is_retired(raw: Dict[str, Any]) -> bool:
    if not isinstance(raw, dict):
        return False
    if str(raw.get("status") or "").lower() == "entered-in-error":
        return True
    vs = raw.get("verificationStatus") or {}
    if isinstance(vs, dict):
        for coding in vs.get("coding") or []:
            if isinstance(coding, dict) and str(coding.get("code") or "").lower() == "entered-in-error":
                return True
    return False


def _group_by_category(events: List[TimelineEvent]) -> List[CategoryGroup]:
    grouped: Dict[str, List[TimelineEvent]] = {}
    for ev in events:
        grouped.setdefault(ev.category, []).append(ev)
    result: List[CategoryGroup] = []
    seen: Set[str] = set()
    for cat in _CATEGORY_ORDER:
        if cat in grouped:
            result.append(
                CategoryGroup(category=cat, event_count=len(grouped[cat]), events=grouped[cat])
            )
            seen.add(cat)
    for cat, evs in grouped.items():
        if cat not in seen:
            result.append(CategoryGroup(category=cat, event_count=len(evs), events=evs))
    return result


def _append_recent_note(
    existing: Optional[str], added: List[TimelineEvent]
) -> Optional[str]:
    labels = []
    for ev in added:
        text = (ev.summary or "").rstrip(".")
        if text and text not in labels:
            labels.append(text)
        if len(labels) >= 8:
            break
    if not labels:
        return existing
    note = "Recently documented (manual or scan): " + "; ".join(labels) + "."
    base = (existing or "").rstrip()
    if note in base:
        return existing
    return f"{base} {note}".strip() if base else note
