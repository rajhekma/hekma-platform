"""
Reclassify allergy-like OCR “diagnoses” into the allergies module only.

Smart scan often puts allergy Rx / “Allergic Rhinitis” under conditions[]
(MedicalCondition). The correct CTMS home is Allergies — not a duplicate
diagnosis row. We move those items out of conditions[] into allergies[].

Legacy rows already in MedicalCondition are still backfilled into Allergies
on allergies list / EHR AllergyIntolerance (idempotent), without deleting
old diagnosis rows here.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def is_allergy_like_condition(item: Dict[str, Any]) -> bool:
    """True when a diagnosis/condition row is really an allergy (common OCR misfire)."""
    category = str(item.get("category") or "").strip().lower()
    name = str(
        item.get("conditionName") or item.get("Condition") or item.get("name") or ""
    ).strip().lower()
    notes = str(item.get("notes") or "").strip().lower()
    blob = f"{category} {name} {notes}"
    return "allerg" in blob


def _condition_to_allergy(
    item: Dict[str, Any], *, fallback_date: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Map one allergy-like condition object into an allergies[] payload."""
    substance = (
        item.get("conditionName") or item.get("Condition") or item.get("name") or ""
    ).strip()
    if not substance or substance.lower() == "uncertain":
        return None
    severity = str(item.get("severity") or "").strip().lower()
    criticality = "high" if severity in ("high", "severe", "moderate") else "low"
    category = str(item.get("category") or "environment").strip().lower()
    if category in ("allergy", "allergies"):
        category = "environment"
    if category not in ("food", "medication", "environment", "biologic"):
        category = "environment"
    onset = (item.get("startDate") or fallback_date or "").strip() or None
    notes = (item.get("notes") or "").strip()
    return {
        "substance": substance,
        "criticality": criticality,
        "category": category,
        "status": (item.get("clinicalStatus") or item.get("status") or "active"),
        "reaction": notes,
        "onsetDate": onset,
        "notes": notes,
        "confidence": item.get("confidence"),
    }


def promote_allergy_like_conditions(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """
    Move allergy-like items from conditions[] into allergies[] (allergy-only).

    Non-allergy conditions are left in conditions[]. Existing allergies[] entries
    are kept; moved substances are merged without duplicating by substance name.
    """
    conditions = extracted.get("conditions") or []
    if not conditions:
        return extracted

    kept_conditions: List[Any] = []
    moved: List[Dict[str, Any]] = []
    fallback_date = extracted.get("date")
    if isinstance(fallback_date, str):
        fallback_date = fallback_date.strip() or None
    else:
        fallback_date = None

    for item in conditions:
        if isinstance(item, dict) and is_allergy_like_condition(item):
            allergy = _condition_to_allergy(item, fallback_date=fallback_date)
            if allergy:
                moved.append(allergy)
                continue
        kept_conditions.append(item)

    if not moved:
        return extracted

    existing = list(extracted.get("allergies") or [])
    seen = {
        str(a.get("substance") or "").strip().lower()
        for a in existing
        if isinstance(a, dict)
    }
    merged = list(existing)
    for allergy in moved:
        key = allergy["substance"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(allergy)

    out = dict(extracted)
    out["conditions"] = kept_conditions
    out["allergies"] = merged
    logger.info(
        "Reclassified allergy-like conditions → allergies only "
        "moved=%s remaining_conditions=%s allergies=%s",
        len(moved),
        len(kept_conditions),
        len(merged),
    )
    return out


def sync_allergy_like_conditions_to_allergies(patient_id: str) -> int:
    """
    Backfill Allergies from legacy allergy-like MedicalCondition / diagnosis rows.

    Idempotent: skips substances that already exist. Does not delete diagnosis rows.
    Returns number of Allergies rows created.
    """
    from ..clinical_fhir.hekma_clinical_store import HekmaClinicalStore
    from ..clinical_fhir.models import ClinicalSource
    from .exceptions import RecordAlreadyExistsError

    store = HekmaClinicalStore()
    conditions = store.list_for_patient(patient_id, "diagnosis", limit=500, offset=0)
    created = 0
    for row in conditions:
        if not is_allergy_like_condition(row):
            continue
        substance = (row.get("conditionName") or "").strip()
        if not substance:
            continue
        if store.find_duplicate(patient_id, "allergies", {"substance": substance}):
            continue
        notes = (row.get("notes") or "").strip()
        start = row.get("startDate")
        if hasattr(start, "strftime"):
            start = start.strftime("%Y-%m-%d")
        source = (
            ClinicalSource.SCAN
            if str(row.get("source") or "").lower() == ClinicalSource.SCAN.value
            else ClinicalSource.MANUAL
        )
        try:
            store.create(
                patient_id,
                "allergies",
                {
                    "substance": substance,
                    "criticality": "low",
                    "category": "environment",
                    "status": row.get("status") or "active",
                    "onsetDate": str(start) if start else None,
                    "notes": notes,
                    "reaction": notes,
                    "source": "ocr_scan_backfill",
                },
                source,
            )
        except RecordAlreadyExistsError:
            continue
        created += 1
    if created:
        logger.info(
            "Backfilled %s allergy rows from diagnosis patient_id=%s",
            created,
            patient_id,
        )
    return created
