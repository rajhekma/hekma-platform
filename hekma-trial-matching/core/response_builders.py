# core/response_builders.py
from .file_utils import load_json
import json
import logging
from datetime import datetime

from repositories.results_repo import fetch_job_results
from repositories.trialgpt_corpus_repo import fetch_locations_by_nct_ids
from utils.matching_result_util import (
    count_exclusion_stats,
    count_inclusion_stats,
    compute_eligible,
    criterion_pass_rate,
    normalize_criteria_dict,
    MATCH_STRONG_PCT,
)

logger = logging.getLogger(__name__)

_TERMINAL_JOB_STATUSES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})


def _results_envelope(job_id, job, flow_type="P2T"):
    """Status fields the UI needs to stop polling even when evaluations is empty."""
    job = job or {}
    envelope = {
        "job_id": job_id,
        "status": job.get("status") or "UNKNOWN",
        "compose_status": job.get("compose_status"),
        "retrieve_status": job.get("retrieve_status"),
        "evaluate_status": job.get("evaluate_status"),
        "rank_status": job.get("rank_status"),
        "error": job.get("error"),
        "error_stage": job.get("error_stage"),
        "total_count": 0,
        "evaluations": [],
        "done": (job.get("status") or "") in _TERMINAL_JOB_STATUSES,
    }
    if flow_type == "P2T":
        envelope["patient_id"] = job.get("query_id")
    else:
        envelope["nct_id"] = job.get("query_id")
    return envelope


def hydrate_trials(nct_ids, corpus_path):
    wanted = set(nct_ids)
    trial_map = {}

    with open(corpus_path) as f:
        for line in f:
            t = json.loads(line)
            if t["_id"] in wanted:
                trial_map[t["_id"]] = t

    return trial_map

def build_retrieval_response(job_id, retrieval_path, corpus_path):
    retrieval = load_json(retrieval_path, {})
    trial_map = hydrate_trials(sum(retrieval.values(), []), corpus_path)

    results = []
    for rank, nct in enumerate(trial_map, start=1):
        t = trial_map[nct]
        results.append({
            "trial_id": t["_id"],
            "nct_id": t["_id"],
            "retrieval_rank": rank,
            "retrieval_score": 1 / rank,
            "trial_title": t.get("title")
        })

    return {
        "job_id": job_id,
        "candidates": results,
        "total_count": len(results)
    }


def extract_trial_evaluation(matching_results, trial_id):
    """
    Extract evaluation details for a single trial from matching_results.json
    """

    # matching_results structure:
    # { patient_id: { label: { trial_id: evaluation } } }

    for patient_id, label_groups in matching_results.items():
        for label, trials in label_groups.items():
            if trial_id in trials:
                return trials[trial_id]

    return None

def format_final_matches(job_id, ranked_trials):
    """
    Format final ranked trial results for API response.

    ranked_trials: List of tuples -> [(trial_id, final_score), ...]
    """

    ranked_matches = []

    for idx, (trial_id, score) in enumerate(ranked_trials, start=1):
        ranked_matches.append({
            "trial_id": trial_id,
            "final_rank": idx,
            "final_score": score
        })

    return {
        "job_id": job_id,
        "total_evaluated": len(ranked_matches),
        "total_eligible": len(ranked_matches),
        "ranked_matches": ranked_matches
    }


def _normalize_phase_list(phase_value):
    if not phase_value:
        return []

    if isinstance(phase_value, list):
        return [str(item).strip() for item in phase_value if str(item).strip()]

    if isinstance(phase_value, str):
        return [part.strip() for part in phase_value.split(",") if part.strip()]

    normalized = str(phase_value).strip()
    return [normalized] if normalized else []


def _safe_json(value, field_name, candidate_id):
    try:
        if value is None:
            return {}

        if isinstance(value, dict):
            return value

        if isinstance(value, memoryview):
            value = value.tobytes().decode("utf-8")

        if isinstance(value, str):
            return json.loads(value)

        logger.warning(
            "Unexpected JSON type for %s (candidate=%s): %s",
            field_name,
            candidate_id,
            type(value),
        )
        return {}

    except Exception:
        logger.exception(
            "Failed parsing JSON field %s (candidate=%s)",
            field_name,
            candidate_id,
        )
        return {}


def _calculate_months(start_date, end_date):
    try:
        if not start_date or not end_date:
            return None

        start = datetime.strptime(start_date[:7], "%Y-%m")
        end = datetime.strptime(end_date[:7], "%Y-%m")

        return (end.year - start.year) * 12 + (end.month - start.month)

    except Exception:
        return None


def build_job_results_response(job_id, flow_type="P2T", job=None):

    logger.info("[RESULT_BUILDER] Building response for job_id=%s", job_id)
    envelope = _results_envelope(job_id, job, flow_type=flow_type)

    try:
        rows = fetch_job_results(job_id)

        if not rows:
            logger.info(
                "[RESULT_BUILDER] No rows found for job_id=%s | status=%s",
                job_id,
                envelope.get("status"),
            )
            return envelope

        logger.info(
            "[RESULT_BUILDER] %s rows fetched for job_id=%s",
            len(rows),
            job_id,
        )

        query_id = rows[0]["query_id"]
        parameters = rows[0]["parameters"]

        if isinstance(parameters, str):
            parameters = json.loads(parameters)
        if not isinstance(parameters, dict):
            parameters = {}

        selected_regions = parameters.get("selected_region", []) or []

        if isinstance(selected_regions, str):
            selected_regions = [selected_regions]

        selected_regions_set = {
            str(r).strip().lower() for r in selected_regions if r and str(r).strip()
        }

        trial_ids = []

        if flow_type == "P2T":
            trial_ids = [row["candidate_id"] for row in rows]

        location_map = fetch_locations_by_nct_ids(trial_ids)

        evaluations = []

        for idx, row in enumerate(rows, start=1):
            try:
                candidate_id = row["candidate_id"]
                rank_position = row["rank_position"]

                inclusion_results = row["inclusion_results"]
                exclusion_results = row["exclusion_results"]

                inclusion_dict = normalize_criteria_dict(
                    _safe_json(inclusion_results, "inclusion_results", candidate_id)
                )
                exclusion_dict = normalize_criteria_dict(
                    _safe_json(exclusion_results, "exclusion_results", candidate_id)
                )

                inclusion_met, total_inclusion = count_inclusion_stats(inclusion_dict)
                exclusion_violated, total_exclusion = count_exclusion_stats(
                    exclusion_dict
                )

                eligible = compute_eligible(inclusion_dict, exclusion_dict)
                criterion_match_rate = criterion_pass_rate(
                    inclusion_dict, exclusion_dict
                )
                ranking_score = float(row.get("final_score") or 0.0)
                relevance_score_r = float(
                    row.get("relevance_score_R") or row.get("relevance_score_r") or 0.0
                )
                eligibility_score_e = float(
                    row.get("eligibility_score_E") or row.get("eligibility_score_e") or 0.0
                )
                avg_confidence = 0.0

                entry = {
                    "rank": rank_position,
                    "eligible": eligible,
                    "meets_strong_match": criterion_match_rate >= MATCH_STRONG_PCT,
                    "strong_match_threshold_pct": MATCH_STRONG_PCT,
                    "ranking_score": ranking_score,
                    "relevance_score_R": relevance_score_r,
                    "eligibility_score_E": eligibility_score_e,
                    "criterion_match_rate": criterion_match_rate,
                    "criteria_match_pct": round(criterion_match_rate, 1),
                    "eligibility_score": ranking_score,
                    "avg_confidence": round(avg_confidence, 3),
                    "inclusion_met": f"{inclusion_met}/{total_inclusion}",
                    "exclusion_violated": f"{exclusion_violated}/{total_exclusion}",
                    "failed": False,
                    "error": None,
                }

                if flow_type == "P2T":
                    entry["trial_id"] = candidate_id

                    trial_data = location_map.get(candidate_id, {})

                    trial_locations = trial_data.get("locations") or []
                    trial_detailed = trial_data.get("locations_detailed") or []

                    enrollment = _safe_json(
                        trial_data.get("enrollment"), "enrollment", candidate_id
                    )

                    title = trial_data.get("title")
                    overall_status = trial_data.get("overall_status")

                    start_date = trial_data.get("start_date")
                    completion_date = trial_data.get("completion_date")

                    duration_months = _calculate_months(start_date, completion_date)

                    matched_locations = [
                        loc
                        for loc in trial_locations
                        if loc and str(loc).strip().lower() in selected_regions_set
                    ]

                    matched_detailed = []

                    for d in trial_detailed:
                        key = ", ".join(
                            filter(
                                None,
                                [
                                    d.get("city"),
                                    d.get("state"),
                                    d.get("country"),
                                ],
                            )
                        ).strip().lower()

                        if key in selected_regions_set:
                            matched_detailed.append(d)

                    entry["locations"] = matched_locations
                    entry["locations_detailed"] = matched_detailed or []

                    entry["trial_title"] = title
                    entry["phase"] = _normalize_phase_list(
                        trial_data.get("phase")
                    )
                    entry["enrollment"] = enrollment
                    entry["overall_status"] = overall_status
                    entry["study_duration_months"] = duration_months
                else:
                    entry["patient_id"] = candidate_id

                evaluations.append(entry)

            except Exception:
                logger.exception(
                    "[RESULT_BUILDER] Failed processing row index=%s",
                    idx,
                )
                raise

        logger.info(
            "[RESULT_BUILDER] Completed job_id=%s with %s evaluations",
            job_id,
            len(evaluations),
        )

        envelope["parameters"] = parameters
        envelope["evaluations"] = evaluations
        envelope["total_count"] = len(evaluations)
        if flow_type == "P2T":
            envelope["patient_id"] = query_id
        else:
            envelope["nct_id"] = query_id
        return envelope

    except Exception:
        logger.exception(
            "[RESULT_BUILDER] Fatal error building response for job_id=%s",
            job_id,
        )
        raise
