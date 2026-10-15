
import os
import sys
import json
import logging

# Import the core modules from the parent directory
# We need to add the parent directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from trialgpt_retrieval.keyword_generation import generate_keywords_for_text
from trialgpt_retrieval.hybrid_fusion_retrieval import run_retrieval
from trialgpt_matching.run_matching import run_matching_process
from trialgpt_ranking.run_aggregation import run_aggregation_process
from trialgpt_ranking.rank_results import get_matching_score, get_agg_score # We might need to call rank script as subprocess or import logic
from utils.matching_result_util import compute_ranking_score
from core.job_manager import JobManager

from repositories.retrieval_results_repo import insert_retrieval_results
from services.rag_retrieval_service import retrieve_trial_ids_for_patient
from config.trial_gpt_ehr_config import get_trial_gpt_ehr_config
from repositories.trial_gpt_ehr_repo import (
    fetch_structured_profile as fetch_trial_gpt_ehr_profile,
    fetch_summary_text as fetch_trial_gpt_ehr_summary,
)

from repositories.trialgpt_corpus_repo import (
    fetch_all_trials,
    fetch_trials_by_location,
    fetch_trials_by_location_and_diseases,
    fetch_trials_by_ids,
    filter_nct_ids_by_location_and_diseases,
    fetch_nct_ids_by_location_and_diseases,
)

from repositories.matching_results_repo import insert_matching_result
from repositories.aggregation_results_repo import insert_aggregation_result
from repositories.final_ranking_repo import insert_final_ranking
from utils.llm_config import (
    DEFAULT_WORKFLOW_LLM_SERVICE,
    DEFAULT_WORKFLOW_MODEL,
    resolve_workflow_llm_service,
    resolve_workflow_model,
)
from utils.trial_criteria_util import criteria_to_matching_text
from utils.eval_corpus_util import (
    load_nct_ids_from_corpus_jsonl,
    merge_retrieval_nct_ids,
    resolve_eval_corpus_jsonl_path,
)

logger = logging.getLogger("workflow.p2t")

_TERMINAL_JOB_STATUSES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})


def _complete_p2t_with_no_trials(job_manager: JobManager, job_id: str, reason: str) -> None:
    """Mark evaluate+rank done when there is nothing to match so the UI can stop polling."""
    logger.info("[%s][P2T] Completing with zero evaluations | reason=%s", job_id, reason)
    job_manager.update_stage(job_id, "evaluate", "COMPLETED")
    job_manager.update_stage(job_id, "rank", "COMPLETED")
    print(f"[{job_id}] Workflow Complete. No matching trials.")


def _fail_p2t_job(job_id: str, exc: Exception) -> None:
    """Record a terminal FAILED state so /results stops looking like an in-progress empty job."""
    logger.exception("[%s][P2T] Workflow failed: %s", job_id, exc)
    try:
        from repositories.matching_jobs_repo import get_job, fail_job

        job_row = get_job(job_id) or {}
        jm = JobManager()
        failed_stage = None
        for col, name in (
            ("compose_status", "compose"),
            ("retrieve_status", "retrieve"),
            ("evaluate_status", "evaluate"),
            ("rank_status", "rank"),
        ):
            if job_row.get(col) in ("RUNNING", "FAILED"):
                if job_row.get(col) == "RUNNING":
                    jm.update_stage(job_id, name, "FAILED")
                failed_stage = failed_stage or name
        if job_row.get("error") and job_row.get("status") in _TERMINAL_JOB_STATUSES:
            return
        fail_job(
            job_id,
            str(exc)[:500],
            failed_stage or job_row.get("error_stage"),
        )
    except Exception:
        logger.exception("[%s][P2T] Failed to mark job FAILED", job_id)


def run_patient_workflow(
    job_id,
    patient_data,
    corpus="sigir",
    model=None,
    llm_service=None,
):
    """Run P2T; always leave the job COMPLETED or FAILED so the UI can stop polling."""
    from services.ai_usage import llm_usage_scope

    hekma_pid = str(
        (patient_data or {}).get("hekma_patient_id")
        or (patient_data or {}).get("patient_id")
        or ""
    )
    with llm_usage_scope(
        patient_id=hekma_pid,
        product="trial_match",
        job_id=str(job_id),
        source_service="hekma-trialgpt",
    ):
        try:
            _run_patient_workflow_impl(
                job_id,
                patient_data,
                corpus=corpus,
                model=model,
                llm_service=llm_service,
            )
        except Exception as exc:
            _fail_p2t_job(job_id, exc)
            raise


def _run_patient_workflow_impl(
    job_id,
    patient_data,
    corpus="sigir",
    model=None,
    llm_service=None,
):
    model = resolve_workflow_model(model)
    llm_service = resolve_workflow_llm_service(llm_service)
    """
    Orchestrates the patient-to-trials workflow (DB-driven persistence).
    """


    job_dir = os.path.join(parent_dir, "jobs", job_id)
    input_dir = os.path.join(job_dir, "input")
    results_dir = os.path.join(job_dir, "results")

    job_manager = JobManager()

    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)

    print(f"[{job_id}] Starting Patient-to-Trials Workflow")

    patient_id = patient_data.get("patient_id")
    selected_region = patient_data.get("selected_region")
    #selected_region_details = patient_data.get("selected_region_details") or []
    

    # Normalize region to list
    if selected_region:
        if isinstance(selected_region, str):
            selected_region = [selected_region]
        elif not isinstance(selected_region, list):
            raise ValueError("selected_region must be string or list")    
    selected_disease = patient_data.get("selected_disease")
    if selected_disease:
        if isinstance(selected_disease, str):
            selected_disease = [selected_disease]
        elif not isinstance(selected_disease, list):
            raise ValueError("selected_disease must be string or list")
    retrieval_mode = (patient_data.get("retrieval_mode") or "rag").lower()
    debug_enabled = bool(patient_data.get("debug", False))
    logger.info(
        "[%s][P2T] Start workflow retrieval_mode=%s corpus=%s model=%s debug=%s",
        job_id, retrieval_mode, corpus, model, debug_enabled
    )

    # P2T always reads trial_gpt_ehr (Fasten EHR path); no eligible_patients fallback.
    config = get_trial_gpt_ehr_config()
    patient_text = fetch_trial_gpt_ehr_summary(
        subject_id=patient_id,
        llm=config.p2t_preferred_llm,
    )
    if not patient_text:
        raise ValueError(
            f"No ready summary_text in trial_gpt_ehr for patient_id={patient_id} "
            f"(llm={config.p2t_preferred_llm})"
        )
    logger.info(
        "[%s][P2T] Loaded patient summary | source=trial_gpt_ehr | llm_preferred=%s",
        job_id,
        config.p2t_preferred_llm,
    )

    # Keyword Generation
    job_manager.update_stage(job_id, "compose", "RUNNING")

    try:
        keywords = generate_keywords_for_text(
            patient_text, model=model, llm_service=llm_service
        )
        if debug_enabled:
            logger.info(
                "[%s][P2T][DEBUG] Generated keyword keys=%s",
                job_id,
                list((keywords or {}).keys()),
            )

        queries = [{"_id": patient_id, "text": patient_text}]
        id2queries = {patient_id: {"turbo": keywords}}

        job_manager.update_stage(job_id, "compose", "COMPLETED")

    except Exception:
        logger.exception("[%s][P2T] Compose failed", job_id)
        job_manager.update_stage(job_id, "compose", "FAILED")
        raise

    # Retrieval 
    job_manager.update_stage(job_id, "retrieve", "RUNNING")

    try:
        eval_corpus_path = resolve_eval_corpus_jsonl_path(corpus)
        pin_nct_ids = (
            load_nct_ids_from_corpus_jsonl(eval_corpus_path)
            if eval_corpus_path
            else []
        )

        if retrieval_mode == "rag":
            raw_profile = fetch_trial_gpt_ehr_profile(
                subject_id=patient_id,
                llm=config.p2t_preferred_llm,
            ) or {}
            if not isinstance(raw_profile, dict):
                raw_profile = {}

            # When the caller asks for disease/region filters, oversample RAG so we
            # still have enough candidates after the hard intersection below.
            has_filters = bool(selected_region or selected_disease)
            rag_top_k = 80 if has_filters else 20

            rag_ncts: list[str] = []
            if not pin_nct_ids:
                rag_ncts = retrieve_trial_ids_for_patient(
                    patient_id=patient_id,
                    raw_profile=raw_profile,
                    top_k=rag_top_k,
                    threshold=0.1,
                    debug=debug_enabled,
                )
                logger.info(
                    "[%s][P2T] RAG retrieval returned %s candidates (top_k=%s filters=%s)",
                    job_id,
                    len(rag_ncts),
                    rag_top_k,
                    has_filters,
                )
            else:
                logger.info(
                    "[%s][P2T] Eval corpus %s -> %s pinned NCTs (open RAG skipped)",
                    job_id,
                    eval_corpus_path,
                    len(pin_nct_ids),
                )

            merged_ncts = merge_retrieval_nct_ids(pin_nct_ids, rag_ncts)

            # Hard-enforce selected disease/region on RAG candidates (RAG itself is
            # semantic-only and previously ignored these request filters).
            if has_filters:
                before = len(merged_ncts)
                filtered = filter_nct_ids_by_location_and_diseases(
                    merged_ncts,
                    locations=selected_region,
                    diseases=selected_disease,
                )
                dropped = before - len(filtered)
                logger.info(
                    "[%s][P2T] RAG filter region=%s disease=%s kept=%s dropped=%s",
                    job_id,
                    selected_region,
                    selected_disease,
                    len(filtered),
                    dropped,
                )

                # Backfill from DB-filtered trials when RAG recall under the hard
                # filters is thin, so the job still returns useful candidates.
                target_k = 20
                if len(filtered) < target_k:
                    backfill = fetch_nct_ids_by_location_and_diseases(
                        locations=selected_region,
                        diseases=selected_disease,
                        limit=target_k * 3,
                    )
                    seen = set(filtered)
                    for nct in backfill:
                        if nct not in seen:
                            filtered.append(nct)
                            seen.add(nct)
                        if len(filtered) >= target_k:
                            break
                    logger.info(
                        "[%s][P2T] RAG filter backfill -> %s candidates",
                        job_id,
                        len(filtered),
                    )

                merged_ncts = filtered[:target_k]

            qid2nctids = {patient_id: merged_ncts}
            logger.info(
                "[%s][P2T] Retrieval candidate count=%s",
                job_id,
                len(merged_ncts),
            )
            if not merged_ncts:
                insert_retrieval_results(
                    job_id=job_id,
                    flow_type="P2T",
                    qid2nctids=qid2nctids,
                )
                job_manager.update_stage(job_id, "retrieve", "COMPLETED")
                _complete_p2t_with_no_trials(
                    job_manager, job_id, "no_retrieval_candidates"
                )
                return
        else:
            if pin_nct_ids:
                qid2nctids = {patient_id: pin_nct_ids}
                logger.info(
                    "[%s][P2T] Eval corpus pin (legacy mode): %s NCTs",
                    job_id,
                    len(pin_nct_ids),
                )
            else:
                qid2nctids = run_retrieval(
                    q_type="turbo",
                    k=20,
                    bm25_wt=1,
                    medcpt_wt=0,
                    queries=queries,
                    id2queries=id2queries,
                    N=20,
                    region=selected_region,
                    disease=selected_disease,
                )
            if debug_enabled:
                logger.info(
                    "[%s][P2T][DEBUG] Legacy filters region=%s disease=%s",
                    job_id, selected_region, selected_disease
                )
            retrieved_count = len(qid2nctids.get(patient_id, [])) if isinstance(qid2nctids, dict) else 0
            logger.info("[%s][P2T] Legacy retrieval returned %s candidates", job_id, retrieved_count)
            if retrieved_count == 0:
                insert_retrieval_results(
                    job_id=job_id,
                    flow_type="P2T",
                    qid2nctids=qid2nctids,
                )
                job_manager.update_stage(job_id, "retrieve", "COMPLETED")
                _complete_p2t_with_no_trials(
                    job_manager, job_id, "no_legacy_retrieval_candidates"
                )
                return

        insert_retrieval_results(
            job_id=job_id,
            flow_type="P2T",
            qid2nctids=qid2nctids
        )

        job_manager.update_stage(job_id, "retrieve", "COMPLETED")

    except Exception:
        job_manager.update_stage(job_id, "retrieve", "FAILED")
        raise

    # Prepare Matching Input (Temporary JSON)
    if retrieval_mode == "rag":
        # Hydrate by the (already region/disease-filtered) RAG candidate IDs.
        rag_ids = []
        for _, nct_list in qid2nctids.items():
            rag_ids.extend(nct_list or [])
        all_trials = fetch_trials_by_ids(list(set(rag_ids)))
        logger.info("[%s][P2T] Hydrated %s trials from DB by RAG IDs", job_id, len(all_trials))
    else:
        if selected_region and selected_disease:
            all_trials = fetch_trials_by_location_and_diseases(
                selected_region,
                selected_disease
            )
        elif selected_region:
            all_trials = fetch_trials_by_location(selected_region)
        else:
            all_trials = fetch_all_trials()
        logger.info("[%s][P2T] Hydrated %s trials from legacy filter path", job_id, len(all_trials))

    trial_map = {t["nct_id"]: t for t in all_trials}
    if debug_enabled:
        logger.info("[%s][P2T][DEBUG] Trial map built with %s keys", job_id, len(trial_map))

    matching_input = []

    for qid, nct_list in qid2nctids.items():
        candidates = []
        dropped_missing = 0
        for nct in nct_list:
            if nct not in trial_map:
                dropped_missing += 1
                continue
            db_trial = trial_map[nct]

            adapted_trial = {
                "_id": db_trial["nct_id"],
                "NCTID": db_trial["nct_id"],
                "brief_title": db_trial.get("title", ""),
                "title": db_trial.get("title", ""),
                "brief_summary": db_trial.get("text", ""),
                "text": db_trial.get("text", ""),

                "inclusion_criteria": criteria_to_matching_text(
                    db_trial.get("inclusion_criteria")
                ),
                "exclusion_criteria": criteria_to_matching_text(
                    db_trial.get("exclusion_criteria")
                ),

                "diseases_list": db_trial.get("diseases", []) or [],
                "drugs_list": db_trial.get("drugs", []) or [],
            }                
            candidates.append(adapted_trial)
        matching_input.append({
            "patient_id": qid,
            "patient": patient_text,
            "candidates": candidates
        })
        if debug_enabled:
            logger.info(
                "[%s][P2T][DEBUG] qid=%s candidates_kept=%s dropped_missing=%s",
                job_id, qid, len(candidates), dropped_missing
            )

    matching_input_file = os.path.join(results_dir, "retrieved_trials_formatted.json")

    with open(matching_input_file, "w") as f:
        json.dump(matching_input, f, indent=4)
    logger.info("[%s][P2T] Matching input prepared for %s query rows", job_id, len(matching_input))

    hydrated_count = sum(len(row.get("candidates") or []) for row in matching_input)
    if hydrated_count == 0:
        _complete_p2t_with_no_trials(job_manager, job_id, "no_hydrated_trials")
        return

    #  Matching
    job_manager.update_stage(job_id, "evaluate", "RUNNING")

    matching_output = os.path.join(results_dir, "matching_results.json")

    try:
        run_matching_process(
            matching_input_file, matching_output, model, llm_service
        )
        matching_results = json.load(open(matching_output))
        job_manager.update_stage(job_id, "evaluate", "COMPLETED")
        logger.info("[%s][P2T] Matching stage completed", job_id)
    except Exception:
        job_manager.update_stage(job_id, "evaluate", "FAILED")
        raise

    # ----------------------------------------------------
    # Persist Matching Results to DB
    # ----------------------------------------------------
    logger.info("[%s][P2T] Matching result patient rows=%s", job_id, len(matching_results))

    for pid, label2trial2results in matching_results.items():
        for label, trial2results in label2trial2results.items():
            for trial_id, results in trial2results.items():

                insert_matching_result(
                    job_id=job_id,
                    flow_type="P2T",
                    query_id=pid,
                    candidate_id=trial_id,
                    inclusion_results=results.get("inclusion"),
                    exclusion_results=results.get("exclusion")
                )

    # Aggregation
    job_manager.update_stage(job_id, "rank", "RUNNING")

    agg_output = os.path.join(results_dir, "aggregation_results.json")

    try:
        run_aggregation_process(
            corpus,
            model,
            matching_output,
            agg_output,
            llm_service=llm_service,
            matching_input_path=matching_input_file,
            reset_output=True,
        )
        logger.info("[%s][P2T] Aggregation stage completed", job_id)
    except Exception:
        job_manager.update_stage(job_id, "rank", "FAILED")
        raise

    # ----------------------------------------------------
    # Persist Aggregation Results to DB
    # ----------------------------------------------------
    if os.path.exists(agg_output):
        agg_results = json.load(open(agg_output))
    else:
        agg_results = {}
        logger.info("[%s][P2T] Aggregation output missing; defaulting to empty results", job_id)

    agg_persisted = 0
    for pid, trial_dict in agg_results.items():
        for trial_id, assessment in trial_dict.items():
            if not isinstance(assessment, dict):
                continue

            insert_aggregation_result(
                job_id=job_id,
                flow_type="P2T",
                query_id=pid,
                candidate_id=trial_id,
                relevance_score=assessment.get("relevance_score_R"),
                eligibility_score=assessment.get("eligibility_score_E"),
                relevance_explanation=assessment.get("relevance_explanation"),
                eligibility_explanation=assessment.get("eligibility_explanation")
            )
            agg_persisted += 1

    logger.info(
        "[%s][P2T] Aggregation rows persisted=%s (file patients=%s)",
        job_id,
        agg_persisted,
        len(agg_results),
    )
    if agg_persisted == 0 and matching_results:
        logger.warning(
            "[%s][P2T] No aggregation scores persisted; rankings will be matching-only.",
            job_id,
        )

    # Final Ranking 
    for pid, label2trial2results in matching_results.items():

        trial2score = {}

        for label, trial2results in label2trial2results.items():
            for trial_id, results in trial2results.items():

                relevance = 0.0
                eligibility = 0.0
                if pid in agg_results and trial_id in agg_results[pid]:
                    assessment = agg_results[pid][trial_id]
                    relevance = assessment.get("relevance_score_R", 0.0)
                    eligibility = assessment.get("eligibility_score_E", 0.0)

                # Rank primarily by criteria fit so the best-matching trials surface
                # at the top (legacy flat -1 penalties made ranking insensitive to how
                # many criteria actually matched).
                trial2score[trial_id] = compute_ranking_score(
                    results.get("inclusion", {}),
                    results.get("exclusion", {}),
                    relevance_R=relevance,
                    eligibility_E=eligibility,
                )

        sorted_trials = sorted(trial2score.items(), key=lambda x: -x[1])

        rank_position = 1
        for trial, score in sorted_trials:
            insert_final_ranking(
                job_id=job_id,
                flow_type="P2T",
                query_id=pid,
                candidate_id=trial,
                final_score=score,
                rank_position=rank_position
            )
            rank_position += 1

    job_manager.update_stage(job_id, "rank", "COMPLETED")
    logger.info("[%s][P2T] Ranking completed and results persisted", job_id)

    print(f"[{job_id}] Workflow Complete. Results stored in DB.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python patient_to_trials.py <job_id> <patient_text> "
            "[corpus] [model] [llm_service]"
        )
        sys.exit(1)

    job_id = sys.argv[1]
    patient_text = sys.argv[2]
    corpus = sys.argv[3] if len(sys.argv) > 3 else "sigir"
    model = sys.argv[4] if len(sys.argv) > 4 else DEFAULT_WORKFLOW_MODEL
    llm_service = sys.argv[5] if len(sys.argv) > 5 else DEFAULT_WORKFLOW_LLM_SERVICE

    patient_data = {
        "patient_id": job_id,
        "text": patient_text,
    }

    run_patient_workflow(job_id, patient_data, corpus, model, llm_service)
