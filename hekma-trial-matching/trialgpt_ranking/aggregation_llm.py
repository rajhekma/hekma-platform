"""
Route trial-level aggregation to OpenAI or Anthropic based on llm_service.
"""

from __future__ import annotations

import json
import re

from services.llm_invoke import complete_workflow_text
from utils.matching_result_util import normalize_matching_results
from trialgpt_ranking.TrialGPT import convert_pred_to_prompt


def _parse_aggregation_json(text: str) -> dict:
    text = text.strip().strip("`").strip("json")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group())
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")
    return _normalize_aggregation_result(parsed)


def _normalize_aggregation_result(raw: dict) -> dict:
    r = raw.get("relevance_score_R", raw.get("relevance_score"))
    e = raw.get("eligibility_score_E", raw.get("eligibility_score"))
    return {
        "relevance_explanation": raw.get("relevance_explanation") or "",
        "relevance_score_R": float(r) if r is not None else 0.0,
        "eligibility_explanation": raw.get("eligibility_explanation") or "",
        "eligibility_score_E": float(e) if e is not None else 0.0,
    }


def trialgpt_aggregation(
    patient: str,
    trial_results: dict,
    trial_info: dict,
    model: str,
    llm_service: str = "openai",
) -> dict:
    normalized = normalize_matching_results(trial_results)
    system_prompt, user_prompt = convert_pred_to_prompt(patient, normalized, trial_info)

    text = complete_workflow_text(
        system_prompt,
        user_prompt,
        model=model,
        llm_service=llm_service,
        temperature=0,
        max_tokens=2048,
    )
    return _parse_aggregation_json(text)
