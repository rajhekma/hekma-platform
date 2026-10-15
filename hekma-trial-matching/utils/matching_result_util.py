"""
Normalize TrialGPT matching criterion results (3-tuple standard; accept legacy 4-tuple).
"""

from __future__ import annotations

from typing import Any


def parse_criterion_result(result: Any) -> list | None:
    """
    Standard TrialGPT tuple: [reasoning, sentence_ids, label].
    Legacy Claude tuple: [evidence, sentence_ids, reasoning, label].
    """
    if not isinstance(result, list) or len(result) < 3:
        return None

    if len(result) == 3:
        reasoning, evidence_ids, label = result[0], result[1], result[2]
        return [reasoning, evidence_ids, str(label).strip()]

    # Legacy Claude: [evidence, sentence_ids, reasoning, label]
    return [result[-2], result[1], str(result[-1]).strip()]


def normalize_criteria_dict(criteria_dict: dict | None) -> dict:
    if not isinstance(criteria_dict, dict):
        return {}
    out = {}
    for key, value in criteria_dict.items():
        normalized = parse_criterion_result(value)
        if normalized is not None:
            out[str(key)] = normalized
    return out


def normalize_matching_results(results: dict | None) -> dict:
    if not isinstance(results, dict):
        return {"inclusion": {}, "exclusion": {}}
    return {
        "inclusion": normalize_criteria_dict(results.get("inclusion")),
        "exclusion": normalize_criteria_dict(results.get("exclusion")),
    }


def get_label(result: Any) -> str | None:
    parsed = parse_criterion_result(result)
    return parsed[2] if parsed else None


def count_inclusion_stats(inclusion_dict: dict) -> tuple[int, int]:
    total = len(inclusion_dict)
    met = 0
    for value in inclusion_dict.values():
        if get_label(value) == "included":
            met += 1
    return met, total


def count_exclusion_stats(exclusion_dict: dict) -> tuple[int, int]:
    total = len(exclusion_dict)
    violated = 0
    for value in exclusion_dict.values():
        if get_label(value) == "excluded":
            violated += 1
    return violated, total


def compute_eligible(inclusion_dict: dict, exclusion_dict: dict) -> bool:
    inclusion_met, total_inclusion = count_inclusion_stats(inclusion_dict)
    exclusion_violated, _ = count_exclusion_stats(exclusion_dict)
    if total_inclusion == 0:
        return False
    return inclusion_met == total_inclusion and exclusion_violated == 0


def criterion_pass_rate(inclusion_dict: dict, exclusion_dict: dict) -> float:
    inclusion_met, total_inclusion = count_inclusion_stats(inclusion_dict)
    exclusion_violated, total_exclusion = count_exclusion_stats(exclusion_dict)
    total_criteria = total_inclusion + total_exclusion
    if total_criteria == 0:
        return 0.0
    passed = inclusion_met + (total_exclusion - exclusion_violated)
    return (passed / total_criteria) * 100.0


# Minimum criteria-match percentage to flag a candidate as a "strong" match in the
# API response. Kept separate from the strict `eligible` flag (which still requires
# ALL inclusion criteria met and zero exclusion violations).
import os as _os

try:
    MATCH_STRONG_PCT = float(_os.getenv("MATCH_STRONG_PCT", "80"))
except (TypeError, ValueError):
    MATCH_STRONG_PCT = 80.0


def inclusion_confirmation_rate(inclusion_dict: dict) -> float:
    """Fraction (0..1) of inclusion criteria explicitly confirmed 'included'.

    Unlike criterion_pass_rate this ignores exclusion criteria and does not credit
    'not enough information', so it reflects positively-confirmed inclusion only.
    """
    inclusion_met, total_inclusion = count_inclusion_stats(inclusion_dict)
    if total_inclusion == 0:
        return 0.0
    return inclusion_met / total_inclusion


def compute_ranking_score(
    inclusion_dict: dict,
    exclusion_dict: dict,
    relevance_R: float = 0.0,
    eligibility_E: float = 0.0,
) -> float:
    """
    Composite ranking score that primarily reflects how well a candidate matches the
    trial criteria, so the strongest matches surface at the top.

    Design (higher is better):
      * base   = criteria pass-rate (0..1) — dominant term
      * bonus  = inclusion confirmation rate (0..0.5) — rewards explicitly-met inclusions
                 over merely "not enough information"
      * penalty= each violated exclusion is a hard negative (-0.5)
      * tiebreak = aggregation relevance+eligibility, scaled small (~ -0.1..0.2)

    This replaces the legacy get_matching_score + get_agg_score sum, whose flat -1
    penalties made ranking insensitive to how many criteria actually matched.
    """
    pass_rate = criterion_pass_rate(inclusion_dict, exclusion_dict) / 100.0
    incl_conf = inclusion_confirmation_rate(inclusion_dict)
    exclusion_violated, _ = count_exclusion_stats(exclusion_dict)

    try:
        agg = (float(relevance_R or 0.0) + float(eligibility_E or 0.0)) / 200.0
    except (TypeError, ValueError):
        agg = 0.0

    return pass_rate + 0.5 * incl_conf - 0.5 * exclusion_violated + 0.1 * agg
