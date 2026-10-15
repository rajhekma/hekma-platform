"""
Map patient condition strings to official ICD-10-CM diagnosis titles (and codes).
"""

from __future__ import annotations

import json
from typing import Any

from services.llm_invoke import complete_json_object
from utils.llm_config import resolve_compose_llm_service, resolve_compose_model

ICD_NORMALIZE_SYSTEM_PROMPT = """You are a certified clinical coding specialist using ICD-10-CM (U.S. clinical modification).

Given a list of patient condition phrases, map EACH to the best matching ICD-10-CM diagnosis.

Rules:
1. Use the official ICD-10-CM diagnosis title (long description) exactly as used in coding manuals.
2. Provide a valid ICD-10-CM code (with dot, e.g. M32.10, K76.9, N80.9).
3. Map colloquial phrases to the correct disorder (e.g. "gallbladder issues" -> gallbladder disorder code).
4. Do NOT include symptoms, lab findings (leukocytosis, elevated enzymes), or procedures.
5. If specificity is unclear, use the appropriate "unspecified" ICD-10-CM code.
6. One entry per input condition; preserve order.

Return ONLY valid JSON:
{
  "diseases": [
    {
      "input": "original phrase",
      "icd10_code": "M32.10",
      "official_name": "Systemic lupus erythematosus, unspecified"
    }
  ]
}
"""


def normalize_conditions_to_icd10(
    condition_names: list[str],
    *,
    model: str | None = None,
    llm_service: str | None = None,
    patient_context: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return list of {input, icd10_code, official_name}.
    """
    names = [n.strip() for n in condition_names if n and str(n).strip()]
    if not names:
        return []

    model = resolve_compose_model(model)
    llm_service = resolve_compose_llm_service(llm_service)

    user_payload = {
        "conditions": names,
        "patient_context": patient_context or "",
    }
    parsed = complete_json_object(
        ICD_NORMALIZE_SYSTEM_PROMPT,
        json.dumps(user_payload, ensure_ascii=False),
        model=model,
        llm_service=llm_service,
        max_tokens=2048,
    )

    diseases = parsed.get("diseases", parsed if isinstance(parsed, list) else [])
    if not isinstance(diseases, list):
        raise ValueError("ICD normalization response missing 'diseases' array")

    out: list[dict[str, Any]] = []
    for item in diseases:
        if not isinstance(item, dict):
            continue
        official = str(item.get("official_name", "")).strip()
        code = str(item.get("icd10_code", "")).strip()
        if not official:
            continue
        out.append(
            {
                "input": str(item.get("input", "")).strip(),
                "icd10_code": code,
                "official_name": official,
            }
        )
    return out


def official_names_from_icd_entries(entries: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for entry in entries:
        official = entry.get("official_name", "")
        if not official:
            continue
        key = official.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(official)
    return names
