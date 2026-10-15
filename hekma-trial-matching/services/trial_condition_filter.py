"""
Filter Fasten / FHIR condition rows down to trial-match diagnoses for P2T UI.

Excludes nursing/admin labels, screening Z-codes, SDOH, and rows without ICD-10-CM.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

_ICD10_CM_RE = re.compile(r"^[A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?$", re.IGNORECASE)

_NON_DIAGNOSIS_LABEL_RE = re.compile(
    r"(^discharge planning$|^safety adult|^pain\s*-\s*adult$|^infection\s*-\s*adult$|"
    r"^chronic conditions and co-morbidities$|^care plan$|^goal$|^screening$|"
    r"fall risk|health maintenance|overweight/obesity\s*\(|^homeless$|"
    r"^systemic blood pressure$)",
    re.IGNORECASE,
)

_SCREENING_NAME_RE = re.compile(
    r"(^encounter for screening\b|screening for\b|^\s*screening\b)",
    re.IGNORECASE,
)

# ICD-10-CM chapters/prefixes that are not primary trial conditions in the picker.
_EXCLUDED_ICD_PREFIXES = (
    "Z11",  # screening
    "Z12",
    "Z13",
    "Z01",  # encounter for exam
    "Z02",
    "Z91",  # noncompliance / personal risk factors
    "Z59",  # housing / homelessness
    "Z14",  # carrier status
    "Z15",  # genetic susceptibility (risk, not active disease)
)


def _normalize_icd(code: Optional[str]) -> str:
    return str(code or "").strip().upper()


def _icd_excluded(code: Optional[str]) -> bool:
    icd = _normalize_icd(code)
    if not icd or not _ICD10_CM_RE.match(icd):
        return True
    for prefix in _EXCLUDED_ICD_PREFIXES:
        if icd.startswith(prefix):
            return True
    return False


def _name_excluded(name: str) -> bool:
    text = (name or "").strip()
    if not text:
        return True
    if _NON_DIAGNOSIS_LABEL_RE.search(text):
        return True
    if _SCREENING_NAME_RE.search(text):
        return True
    return False


def is_trial_match_icd_entry(entry: Dict[str, Any]) -> bool:
    """True when this Fasten condition row is suitable for P2T disease selection."""
    name = str(entry.get("official_name") or entry.get("input") or "").strip()
    if _name_excluded(name):
        return False
    icd = entry.get("icd10_code")
    if _icd_excluded(icd):
        return False
    return True


def _dedupe_key(entry: Dict[str, Any]) -> str:
    icd = _normalize_icd(entry.get("icd10_code"))
    if icd:
        # Collapse migraine variants: G43.001, G43.0, G43 → same family
        parts = icd.split(".")
        base = parts[0]
        if len(base) >= 4 and base[0] in "CDEFGHIJKLMNOPQRSTUVW":
            return base[:4] if base.startswith("G43") else base[:3]
        return base[:3] if len(base) >= 3 else base
    return str(entry.get("official_name") or "").strip().lower()


def _pick_better(existing: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Prefer more specific ICD and human-readable (non-ALL-CAPS) labels."""
    e_icd = _normalize_icd(existing.get("icd10_code"))
    c_icd = _normalize_icd(candidate.get("icd10_code"))
    if len(c_icd) > len(e_icd):
        return candidate
    e_name = str(existing.get("official_name") or "")
    c_name = str(candidate.get("official_name") or "")
    if e_name.isupper() and not c_name.isupper():
        return candidate
    return existing


def filter_fasten_condition_entries(
    icd_entries: Sequence[Dict[str, Any]],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Return (disease_names, icd_entries) kept for trial matching UI.
    """
    merged: Dict[str, Dict[str, Any]] = {}
    for raw in icd_entries or []:
        if not isinstance(raw, dict):
            continue
        entry = dict(raw)
        if not is_trial_match_icd_entry(entry):
            continue
        key = _dedupe_key(entry)
        if key in merged:
            merged[key] = _pick_better(merged[key], entry)
        else:
            merged[key] = entry

    kept = list(merged.values())
    kept.sort(key=lambda e: str(e.get("official_name") or "").lower())
    names = [str(e["official_name"]) for e in kept if e.get("official_name")]
    return names, kept


def filter_trial_disease_names(names: Sequence[str]) -> List[str]:
    """Filter plain disease name lists (e.g. trial_gpt_ehr disease_list)."""
    out: List[str] = []
    seen: set[str] = set()
    for raw in names or []:
        name = str(raw or "").strip()
        if not name or _name_excluded(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out
