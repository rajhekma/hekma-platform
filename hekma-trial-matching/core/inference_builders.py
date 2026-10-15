import json

from nltk.tokenize import sent_tokenize
from repositories.inference_repo import fetch_nct_inference_data
from repositories.inference_repo import fetch_patient_inference_data

from trialgpt_ranking.rank_results import get_matching_score, get_agg_score
from utils.matching_result_util import (
    compute_eligible,
    normalize_criteria_dict,
    parse_criterion_result,
    criterion_pass_rate,
    MATCH_STRONG_PCT,
)
from utils.trial_criteria_util import (
    criteria_to_list,
    resolve_criterion_index,
    _coerce_index,
)


def _normalize_criteria_list(value):
    return criteria_to_list(value)


def _evidence_text(sentences, evidence_ids):
    if not isinstance(evidence_ids, list):
        return ""
    return " ".join(
        sentences[i] for i in evidence_ids if isinstance(i, int) and i < len(sentences)
    )


def _build_criterion_entries(results_dict, trial_criteria, sentences, criterion_type):
    entries = []
    positive_count = 0
    positive_label = "included" if criterion_type == "inclusion" else "excluded"

    for idx_str, raw in normalize_criteria_dict(results_dict).items():
        parsed = parse_criterion_result(raw)
        if not parsed:
            continue

        list_idx = resolve_criterion_index(idx_str, trial_criteria)
        criterion_text = (
            trial_criteria[list_idx] if 0 <= list_idx < len(trial_criteria) else ""
        )
        reasoning, evidence_ids, label = parsed
        if label == positive_label:
            positive_count += 1

        entries.append({
            "criterion_type": criterion_type,
            "criterion_index": _coerce_index(idx_str),
            "criterion_text": criterion_text,
            "eligible": label,
            "confidence": 0.0,
            "evidence": _evidence_text(sentences, evidence_ids),
            "reasoning": reasoning,
        })

    return entries, positive_count


def _build_user_match_breakdown(inclusion_list, exclusion_list):
    """
    Derive user-facing positive/negative match groups from existing criterion results.

    Positive (matched):
    - inclusion criteria with label "included"
    - exclusion criteria with label other than "excluded" (patient does not violate)

    Negative (not matched):
    - inclusion criteria with label other than "included"
    - exclusion criteria with label "excluded" (patient violates)
    """
    why_matched = []
    why_not_matched = []

    for item in inclusion_list:
        payload = {
            "criterion_type": item.get("criterion_type"),
            "criterion_index": item.get("criterion_index"),
            "criterion_text": item.get("criterion_text"),
            "status": item.get("eligible"),
            "confidence": item.get("confidence"),
            "reasoning": item.get("reasoning"),
            "evidence": item.get("evidence"),
        }
        if item.get("eligible") == "included":
            why_matched.append(payload)
        else:
            why_not_matched.append(payload)

    for item in exclusion_list:
        payload = {
            "criterion_type": item.get("criterion_type"),
            "criterion_index": item.get("criterion_index"),
            "criterion_text": item.get("criterion_text"),
            "status": item.get("eligible"),
            "confidence": item.get("confidence"),
            "reasoning": item.get("reasoning"),
            "evidence": item.get("evidence"),
        }
        if item.get("eligible") == "excluded":
            why_not_matched.append(payload)
        else:
            why_matched.append(payload)

    total = len(why_matched) + len(why_not_matched)
    matched_ratio = (len(why_matched) / total) if total > 0 else 0.0
    not_matched_ratio = (len(why_not_matched) / total) if total > 0 else 0.0

    return {
        "user_matched_count": len(why_matched),
        "user_not_matched_count": len(why_not_matched),
        "user_matched_score": round(matched_ratio, 3),
        "user_not_matched_score": round(not_matched_ratio, 3),
        "why_user_matched": why_matched,
        "why_user_not_matched": why_not_matched,
    }


def build_nct_inference_response(job_id, nct_id):

    data = fetch_nct_inference_data(job_id, nct_id)

    if not data:
        return {
            "job_id": job_id,
            "trial_id": nct_id,
            "failed": True,
            "error": "Inference data not found",
        }

    inclusion_results = data["inclusion_results"] or {}
    exclusion_results = data["exclusion_results"] or {}

    trial_row = data["trial_row"]
    patient_row = data["patient_row"]

    if not trial_row or not patient_row:
        return {
            "job_id": job_id,
            "trial_id": nct_id,
            "failed": True,
            "error": "Trial or patient data missing",
        }

    trial_inclusion = _normalize_criteria_list(trial_row["inclusion_criteria"])
    trial_exclusion = _normalize_criteria_list(trial_row["exclusion_criteria"])

    patient_summary = patient_row["summary_text"]
    sentences = sent_tokenize(patient_summary)

    inclusion_list, inclusion_met = _build_criterion_entries(
        inclusion_results, trial_inclusion, sentences, "inclusion"
    )
    exclusion_list, exclusion_violated = _build_criterion_entries(
        exclusion_results, trial_exclusion, sentences, "exclusion"
    )

    inclusion_norm = normalize_criteria_dict(inclusion_results)
    exclusion_norm = normalize_criteria_dict(exclusion_results)
    eligible = compute_eligible(inclusion_norm, exclusion_norm)
    criteria_match_pct = round(criterion_pass_rate(inclusion_norm, exclusion_norm), 1)

    relevance_score_R = float(data["relevance_score"] or 0.0)
    eligibility_score_E = float(data["eligibility_score"] or 0.0)

    matching_score = get_matching_score({
        "inclusion": inclusion_norm,
        "exclusion": exclusion_norm,
    })

    agg_score = get_agg_score({
        "relevance_score_R": relevance_score_R,
        "eligibility_score_E": eligibility_score_E,
    })

    _final_score = matching_score + agg_score

    total_inclusion = len(inclusion_norm)
    total_exclusion = len(exclusion_norm)
    avg_confidence = 0.0

    exclusion_not_met = total_exclusion - exclusion_violated
    total_criteria = total_inclusion + total_exclusion
    passed_criteria = inclusion_met + exclusion_not_met
    not_matched_criteria = total_criteria - passed_criteria

    match_percentage = (
        (passed_criteria / total_criteria)
        if total_criteria > 0 else 0
    )

    user_match_breakdown = _build_user_match_breakdown(inclusion_list, exclusion_list)

    return {
        "job_id": job_id,
        "trial_id": nct_id,
        "eligible": eligible,
        "criteria_match_pct": criteria_match_pct,
        "meets_strong_match": criteria_match_pct >= MATCH_STRONG_PCT,
        "strong_match_threshold_pct": MATCH_STRONG_PCT,
        "eligibility_score": match_percentage,
        "avg_confidence": round(avg_confidence, 3),
        "relevance_score": match_percentage,
        "eligibility_score_raw": eligibility_score_E,
        "relevance_explanation": data["relevance_explanation"],
        "eligibility_explanation": data["eligibility_explanation"],
        "inclusion_met": f"{inclusion_met}/{total_inclusion}",
        "exclusion_violated": f"{exclusion_violated}/{total_exclusion}",
        "exclusion_not_met": f"{exclusion_not_met}/{total_exclusion}",
        "matched_count": passed_criteria,
        "not_matched_count": not_matched_criteria,
        "matched_count_breakdown": {
            "inclusion_met_count": inclusion_met,
            "exclusion_not_met_count": exclusion_not_met,
        },
        "not_matched_count_breakdown": {
            "inclusion_not_met_count": total_inclusion - inclusion_met,
            "exclusion_failed_count": exclusion_violated,
        },
        "inclusion_criteria": inclusion_list,
        "exclusion_criteria": exclusion_list,
        "user_match_breakdown": user_match_breakdown,
        "failed": False,
        "error": None,
    }

# trial_to_patient flow
def build_patient_inference_response(job_id, patient_id):

    data = fetch_patient_inference_data(job_id, patient_id)

    if not data:
        return {
            "job_id": job_id,
            "patient_id": patient_id,
            "failed": True,
            "error": "Inference data not found",
        }

    nct_id = data["nct_id"]
    inclusion_results = data["inclusion_results"] or {}
    exclusion_results = data["exclusion_results"] or {}

    trial_row = data["trial_row"]
    patient_row = data["patient_row"]

    if not trial_row or not patient_row:
        return {
            "job_id": job_id,
            "patient_id": patient_id,
            "failed": True,
            "error": "Trial or patient data missing",
        }

    trial_inclusion = _normalize_criteria_list(trial_row["inclusion_criteria"])
    trial_exclusion = _normalize_criteria_list(trial_row["exclusion_criteria"])

    patient_summary = patient_row["summary_text"]
    sentences = sent_tokenize(patient_summary)

    inclusion_list, inclusion_met = _build_criterion_entries(
        inclusion_results, trial_inclusion, sentences, "inclusion"
    )
    exclusion_list, exclusion_violated = _build_criterion_entries(
        exclusion_results, trial_exclusion, sentences, "exclusion"
    )

    inclusion_norm = normalize_criteria_dict(inclusion_results)
    exclusion_norm = normalize_criteria_dict(exclusion_results)
    total_inclusion = len(inclusion_norm)
    total_exclusion = len(exclusion_norm)
    eligible = compute_eligible(inclusion_norm, exclusion_norm)
    criteria_match_pct = round(criterion_pass_rate(inclusion_norm, exclusion_norm), 1)

    relevance_score_R = float(data["relevance_score"] or 0.0)
    eligibility_score_E = float(data["eligibility_score"] or 0.0)

    matching_score = get_matching_score({
        "inclusion": inclusion_norm,
        "exclusion": exclusion_norm,
    })

    agg_score = get_agg_score({
        "relevance_score_R": relevance_score_R,
        "eligibility_score_E": eligibility_score_E,
    })

    final_score = matching_score + agg_score

    avg_confidence = 0.0
    exclusion_not_met = total_exclusion - exclusion_violated
    total_criteria = total_inclusion + total_exclusion
    passed_criteria = inclusion_met + exclusion_not_met
    not_matched_criteria = total_criteria - passed_criteria
    user_match_breakdown = _build_user_match_breakdown(inclusion_list, exclusion_list)

    return {
        "job_id": job_id,
        "nct_id": nct_id,
        "patient_id": patient_id,
        "eligible": eligible,
        "criteria_match_pct": criteria_match_pct,
        "meets_strong_match": criteria_match_pct >= MATCH_STRONG_PCT,
        "strong_match_threshold_pct": MATCH_STRONG_PCT,
        "eligibility_score": final_score,
        "avg_confidence": round(avg_confidence, 3),
        "relevance_score": relevance_score_R,
        "eligibility_score_raw": eligibility_score_E,
        "relevance_explanation": data["relevance_explanation"],
        "eligibility_explanation": data["eligibility_explanation"],
        "inclusion_met": f"{inclusion_met}/{total_inclusion}",
        "exclusion_violated": f"{exclusion_violated}/{total_exclusion}",
        "exclusion_not_met": f"{exclusion_not_met}/{total_exclusion}",
        "matched_count": passed_criteria,
        "not_matched_count": not_matched_criteria,
        "matched_count_breakdown": {
            "inclusion_met_count": inclusion_met,
            "exclusion_not_met_count": exclusion_not_met,
        },
        "not_matched_count_breakdown": {
            "inclusion_not_met_count": total_inclusion - inclusion_met,
            "exclusion_failed_count": exclusion_violated,
        },
        "inclusion_criteria": inclusion_list,
        "exclusion_criteria": exclusion_list,
        "user_match_breakdown": user_match_breakdown,
        "failed": False,
        "error": None,
    }
