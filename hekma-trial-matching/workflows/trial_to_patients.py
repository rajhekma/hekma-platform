
import os
import sys
import json
import numpy as np
import logging
import uuid
from rank_bm25 import BM25Okapi
from nltk import word_tokenize

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from trialgpt_matching.run_matching import run_matching_process
from trialgpt_ranking.run_aggregation import run_aggregation_process
from trialgpt_ranking.rank_results import get_matching_score, get_agg_score
from utils.matching_result_util import compute_ranking_score
from core.job_manager import JobManager
from repositories.matching_jobs_repo import get_job, fail_job
from repositories.trialgpt_corpus_repo import fetch_trial_by_id
from repositories.compose_repo import fetch_all_compose_summaries
from repositories.compose_repo import fetch_compose_summaries_map
from repositories.compose_repo import fetch_compose_summaries_by_ids
from repositories.retrieval_results_repo import insert_retrieval_results
from repositories.matching_results_repo import insert_matching_result
from repositories.aggregation_results_repo import insert_aggregation_result
from repositories.final_ranking_repo import insert_final_ranking
from services.rag_retrieval_service import retrieve_patient_ids_for_trial
from utils.llm_config import (
	DEFAULT_WORKFLOW_LLM_SERVICE,
	DEFAULT_WORKFLOW_MODEL,
	resolve_workflow_llm_service,
	resolve_workflow_model,
)
from utils.trial_criteria_util import criteria_to_matching_text

logger = logging.getLogger("workflow.t2p")

def _normalize_patient_id(value):
	if value is None:
		return None
	text = str(value).strip()
	try:
		return str(uuid.UUID(text))
	except Exception:
		return text


def run_trial_to_patients_workflow(
	job_id,
	nct_id,
	corpus="sigir",
	model=None,
	llm_service=None,
	retrieval_mode="rag",
	debug=False,
):
	model = resolve_workflow_model(model)
	llm_service = resolve_workflow_llm_service(llm_service)
	"""
	Trial-to-patients: same stages and DB persistence as trailgpt — trial from
	trialgpt_corpus, patient pool from compose BM25, then matching / aggregation /
	ranking written to Postgres. Temp JSON under jobs/<id>/results/ only as plumbing.
	"""

	job_dir = os.path.join(parent_dir, "jobs", job_id)
	input_dir = os.path.join(job_dir, "input")
	results_dir = os.path.join(job_dir, "results")

	job_manager = JobManager(base_dir=os.path.join(parent_dir, "jobs"))

	os.makedirs(input_dir, exist_ok=True)
	os.makedirs(results_dir, exist_ok=True)

	print(f"[{job_id}] Starting Trial-to-Patients Workflow for {nct_id}")
	logger.info(
		"[%s][T2P] Start workflow nct_id=%s retrieval_mode=%s corpus=%s model=%s llm_service=%s debug=%s",
		job_id, nct_id, retrieval_mode, corpus, model, llm_service, bool(debug)
	)

	job_manager.update_stage(job_id, "compose", "RUNNING")

	trial_obj = fetch_trial_by_id(nct_id)

	if not trial_obj:
		job_manager.update_stage(job_id, "compose", "FAILED")
		raise Exception(f"Trial {nct_id} not found in DB")

	trial_obj = dict(trial_obj)
	trial_text = f"{trial_obj.get('title', '')} {trial_obj.get('text', '')}"
	trial_obj["NCTID"] = trial_obj["nct_id"]

	adapted_trial = {
		"_id": trial_obj.get("nct_id"),
		"NCTID": trial_obj.get("nct_id"),
		"brief_title": trial_obj.get("title", ""),
		"title": trial_obj.get("title", ""),
		"brief_summary": trial_obj.get("text", ""),
		"text": trial_obj.get("text", ""),
		"inclusion_criteria": criteria_to_matching_text(trial_obj.get("inclusion_criteria")),
		"exclusion_criteria": criteria_to_matching_text(trial_obj.get("exclusion_criteria")),
		"diseases_list": trial_obj.get("diseases", []) or [],
		"drugs_list": trial_obj.get("drugs", []) or [],
	}

	job_manager.update_stage(job_id, "compose", "COMPLETED")

	job_manager.update_stage(job_id, "retrieve", "RUNNING")

	job_record = job_manager.get_job(job_id)
	parameters = job_record.get("parameters") or {}
	if isinstance(parameters, str):
		parameters = json.loads(parameters)
	prospective_count = parameters.get("prospective_patient_count", 10)
	rag_threshold = float(parameters.get("rag_threshold", 0.1))
	if debug:
		logger.info(
			"[%s][T2P][DEBUG] retrieval inputs prospective_patient_count=%s rag_threshold=%.3f",
			job_id, prospective_count, rag_threshold
		)

	if (retrieval_mode or "rag").lower() == "rag":
		# RAG retrieval over patient vector collection.
		rag_trial = {
			"title": trial_obj.get("title", ""),
			"text": trial_obj.get("text", ""),
			"inclusion_criteria": criteria_to_matching_text(trial_obj.get("inclusion_criteria")),
			"exclusion_criteria": criteria_to_matching_text(trial_obj.get("exclusion_criteria")),
			"diseases": trial_obj.get("diseases", []) or [],
			"drugs": trial_obj.get("drugs", []) or [],
		}
		if debug:
			logger.info(
				"[%s][T2P][DEBUG] rag_trial fields title_len=%s text_len=%s diseases=%s drugs=%s",
				job_id,
				len(rag_trial.get("title", "")),
				len(rag_trial.get("text", "")),
				len(rag_trial.get("diseases", []) or []),
				len(rag_trial.get("drugs", []) or []),
			)
		ranked_patient_ids = retrieve_patient_ids_for_trial(
			trial=rag_trial,
			top_k=prospective_count,
			threshold=rag_threshold,
			debug=bool(debug),
		)
		logger.info("[%s][T2P] RAG retrieval returned %s patient candidates", job_id, len(ranked_patient_ids))
		# Hydrate summaries for ONLY the retrieved candidates. Scanning the whole
		# trialgpt_eligible_patients table (fetch_compose_summaries_map) times out at
		# ~30k rows and previously left the job stuck in RUNNING.
		patient_map_raw = fetch_compose_summaries_by_ids(ranked_patient_ids)
		patient_map = {}
		for k, v in (patient_map_raw or {}).items():
			nk = _normalize_patient_id(k)
			if nk and v:
				patient_map[nk] = v
		top_patients = [
			{
				"patient_id": _normalize_patient_id(pid),
				"text": patient_map.get(_normalize_patient_id(pid), ""),
			}
			for pid in ranked_patient_ids
			if patient_map.get(_normalize_patient_id(pid))
		]
		if debug:
			missing_ids = [
				_normalize_patient_id(pid)
				for pid in ranked_patient_ids
				if not patient_map.get(_normalize_patient_id(pid))
			]
			logger.info(
				"[%s][T2P][DEBUG] RAG hydrated summaries kept=%s requested=%s missing=%s",
				job_id, len(top_patients), len(ranked_patient_ids), len(missing_ids)
			)
			if missing_ids:
				logger.info(
					"[%s][T2P][DEBUG] Missing compose summaries for first_ids=%s",
					job_id, missing_ids[:5]
				)
	else:
		patients = fetch_all_compose_summaries()

		if not patients:
			job_manager.update_stage(job_id, "retrieve", "COMPLETED")
			return

		patient_ids = [p["patient_id"] for p in patients]
		patient_texts = [p["summary_text"] for p in patients]

		tokenized_patients = [
			word_tokenize(text.lower()) for text in patient_texts
		]

		bm25 = BM25Okapi(tokenized_patients)

		trial_tokens = word_tokenize(trial_text.lower())
		scores = bm25.get_scores(trial_tokens)

		ranked_indices = np.argsort(scores)[::-1][:prospective_count]

		top_patients = [
			{
				"patient_id": patient_ids[idx],
				"text": patient_texts[idx],
			}
			for idx in ranked_indices
		]
		logger.info("[%s][T2P] Legacy retrieval returned %s patient candidates", job_id, len(top_patients))
		if debug:
			logger.info("[%s][T2P][DEBUG] Legacy prospective_patient_count=%s", job_id, prospective_count)

	qid2patients = {
		nct_id: [p["patient_id"] for p in top_patients],
	}
	if debug:
		logger.info(
			"[%s][T2P][DEBUG] Persisting retrieval mapping nct_id=%s patient_ids=%s",
			job_id, nct_id, len(qid2patients.get(nct_id, []))
		)

	insert_retrieval_results(
		job_id=job_id,
		flow_type="T2P",
		qid2nctids=qid2patients,
	)

	job_manager.update_stage(job_id, "retrieve", "COMPLETED")

	matching_input = []

	for p in top_patients:
		matching_input.append({
			"patient_id": p["patient_id"],
			"patient": p["text"],
			"candidates": [adapted_trial],
		})
	if debug:
		logger.info(
			"[%s][T2P][DEBUG] top_patients=%s adapted_trial_id=%s",
			job_id, len(top_patients), adapted_trial.get("_id")
		)

	matching_input_file = os.path.join(results_dir, "matching_input.json")

	with open(matching_input_file, "w") as f:
		json.dump(matching_input, f, indent=4)
	logger.info("[%s][T2P] Matching input prepared with %s query rows", job_id, len(matching_input))

	job_manager.update_stage(job_id, "evaluate", "RUNNING")

	matching_output = os.path.join(results_dir, "matching_results.json")

	try:
		run_matching_process(matching_input_file, matching_output, model, llm_service)
		job_manager.update_stage(job_id, "evaluate", "COMPLETED")
		logger.info("[%s][T2P] Matching stage completed", job_id)
	except Exception:
		job_manager.update_stage(job_id, "evaluate", "FAILED")
		raise

	if os.path.exists(matching_output):
		matching_results = json.load(open(matching_output))
		if debug:
			logger.info("[%s][T2P][DEBUG] matching_result patient rows=%s", job_id, len(matching_results))
	else:
		matching_results = {}
		logger.info("[%s][T2P] Matching output missing; defaulting to empty results", job_id)

	for pid, label2trial2results in matching_results.items():
		for label, trial2results in label2trial2results.items():
			for trial_id, results in trial2results.items():

				insert_matching_result(
					job_id=job_id,
					flow_type="T2P",
					query_id=nct_id,
					candidate_id=pid,
					inclusion_results=results.get("inclusion"),
					exclusion_results=results.get("exclusion"),
				)

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
		logger.info("[%s][T2P] Aggregation stage completed", job_id)
	except Exception:
		job_manager.update_stage(job_id, "rank", "FAILED")
		raise

	if os.path.exists(agg_output):
		agg_results = json.load(open(agg_output))
		if debug:
			logger.info("[%s][T2P][DEBUG] aggregation_result patient rows=%s", job_id, len(agg_results))
	else:
		# No processed pairs -> aggregation file may not be created.
		agg_results = {}
		logger.info("[%s][T2P] Aggregation output missing; defaulting to empty results", job_id)

	for pid, trial_dict in agg_results.items():
		for trial_id, assessment in trial_dict.items():
			if not isinstance(assessment, dict):
				continue

			insert_aggregation_result(
				job_id=job_id,
				flow_type="T2P",
				query_id=nct_id,
				candidate_id=pid,
				relevance_score=assessment.get("relevance_score_R"),
				eligibility_score=assessment.get("eligibility_score_E"),
				relevance_explanation=assessment.get("relevance_explanation"),
				eligibility_explanation=assessment.get("eligibility_explanation"),
			)

	patient_scores = []

	for pid, label2trial2results in matching_results.items():
		for label, trial2results in label2trial2results.items():
			if nct_id in trial2results:
				results = trial2results[nct_id]

				relevance = 0.0
				eligibility = 0.0
				if pid in agg_results and nct_id in agg_results[pid]:
					assessment = agg_results[pid][nct_id]
					relevance = assessment.get("relevance_score_R", 0.0)
					eligibility = assessment.get("eligibility_score_E", 0.0)

				# Rank primarily by criteria fit so the best-matching patients surface
				# at the top (legacy get_matching_score + get_agg_score did not track
				# how many criteria actually matched).
				total_score = compute_ranking_score(
					results.get("inclusion", {}),
					results.get("exclusion", {}),
					relevance_R=relevance,
					eligibility_E=eligibility,
				)
				patient_scores.append((pid, total_score))

	patient_scores.sort(key=lambda x: -x[1])
	if debug:
		logger.info("[%s][T2P][DEBUG] final ranked patients=%s", job_id, len(patient_scores))

	rank_position = 1
	for pid, score in patient_scores:
		insert_final_ranking(
			job_id=job_id,
			flow_type="T2P",
			query_id=nct_id,
			candidate_id=pid,
			final_score=score,
			rank_position=rank_position,
		)
		rank_position += 1

	job_manager.update_stage(job_id, "rank", "COMPLETED")
	logger.info("[%s][T2P] Ranking completed and results persisted", job_id)

	print(f"[{job_id}] Workflow Complete. Results stored in DB.")


def run_trial_to_patients_workflow_db(job_id, model=None, llm_service=None):
	"""
	API entry: load job params, run T2P workflow (DB-backed; persists all stages).
	"""
	job_row = get_job(job_id)
	if not job_row:
		raise ValueError(f"Job not found: {job_id}")

	params = job_row.get("parameters") or {}
	if isinstance(params, str):
		params = json.loads(params)

	nct_id = params.get("nct_id")
	if not nct_id:
		raise ValueError("nct_id missing from job parameters")

	corpus = params.get("corpus", "sigir")
	model = params.get("model", model)
	llm_service = params.get("llm_service", llm_service)
	retrieval_mode = params.get("retrieval_mode", "rag")
	debug = bool(params.get("debug", False))

	try:
		run_trial_to_patients_workflow(
			job_id=job_id,
			nct_id=nct_id,
			corpus=corpus,
			model=model,
			llm_service=llm_service,
			retrieval_mode=retrieval_mode,
			debug=debug,
		)
	except Exception as exc:
		# Never let a background T2P job hang in RUNNING. Flip any stage still marked
		# RUNNING to FAILED and record the error on the job so the status endpoint
		# reports a terminal state instead of a zombie job.
		logger.exception("[%s][T2P] Workflow failed: %s", job_id, exc)
		try:
			job_row = get_job(job_id) or {}
			stage_col_to_name = {
				"compose_status": "compose",
				"retrieve_status": "retrieve",
				"evaluate_status": "evaluate",
				"rank_status": "rank",
			}
			failed_stage = None
			jm = JobManager()
			for col, name in stage_col_to_name.items():
				if job_row.get(col) == "RUNNING":
					jm.update_stage(job_id, name, "FAILED")
					failed_stage = failed_stage or name
			fail_job(job_id, str(exc), failed_stage)
		except Exception:
			logger.exception("[%s][T2P] Failed to mark job FAILED", job_id)
		raise


if __name__ == "__main__":
	if len(sys.argv) < 3:
		print("Usage: python trial_to_patients.py <job_id> <nct_id> [corpus] [model] [llm_service]")
		sys.exit(1)

	job_id = sys.argv[1]
	nct_id = sys.argv[2]
	corpus = sys.argv[3] if len(sys.argv) > 3 else "sigir"
	model = sys.argv[4] if len(sys.argv) > 4 else DEFAULT_WORKFLOW_MODEL
	llm_service = sys.argv[5] if len(sys.argv) > 5 else DEFAULT_WORKFLOW_LLM_SERVICE

	run_trial_to_patients_workflow(job_id, nct_id, corpus, model, llm_service)
