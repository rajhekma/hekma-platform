"""
Build disease_list for compose_summary_block (ICD-10-CM official titles).
"""

from __future__ import annotations

from typing import Any

from services.icd_disease_service import (
    normalize_conditions_to_icd10,
    official_names_from_icd_entries,
)


def _split_condition_text(text: str) -> list[str]:
    if not text or not str(text).strip():
        return []
    parts = []
    for chunk in str(text).split(","):
        value = chunk.strip()
        if value:
            parts.append(value)
    return parts


def derive_condition_phrases_from_blocks(structured_json: dict) -> list[str]:
    if not isinstance(structured_json, dict):
        return []
    conditions = structured_json.get("conditions")
    return _split_condition_text(conditions) if conditions else []


def derive_disease_list_from_blocks(structured_json: dict) -> list[str]:
    """Legacy: raw condition phrases without ICD normalization."""
    return derive_condition_phrases_from_blocks(structured_json)


def build_icd_official_disease_list(
    source_blocks: dict,
    *,
    model: str | None = None,
    llm_service: str | None = None,
    patient_context: str | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Returns (disease_list official ICD titles, _icd_diseases detail records).
    """
    phrases = derive_condition_phrases_from_blocks(source_blocks)
    entries = normalize_conditions_to_icd10(
        phrases,
        model=model,
        llm_service=llm_service,
        patient_context=patient_context,
    )
    return official_names_from_icd_entries(entries), entries


def attach_icd_diseases_metadata(
    structured_json: dict,
    icd_entries: list[dict[str, Any]],
) -> dict:
    out = dict(structured_json or {})
    out["_icd_diseases"] = icd_entries
    return out
