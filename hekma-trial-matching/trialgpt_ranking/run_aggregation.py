__author__ = "qiao"

"""
Using GPT to aggregate the scores by itself.
Aligned with trailgpt: trial and patient context from DB (trialgpt_corpus, compose_summary_block).
"""

import json
import logging
import os
import sys
from nltk.tokenize import sent_tokenize

from repositories.trialgpt_corpus_repo import fetch_trials_by_ids
from repositories.compose_repo import fetch_compose_summary
from utils.trial_criteria_util import criteria_to_matching_text
from utils.llm_config import resolve_workflow_llm_service

try:
	from aggregation_llm import trialgpt_aggregation
except ImportError:
	try:
		from .aggregation_llm import trialgpt_aggregation
	except ImportError:
		from trialgpt_ranking.aggregation_llm import trialgpt_aggregation

logger = logging.getLogger(__name__)


def _coerce_json_list(value):
	if not value:
		return []
	if isinstance(value, list):
		return value
	if isinstance(value, str):
		try:
			parsed = json.loads(value)
			return parsed if isinstance(parsed, list) else []
		except (json.JSONDecodeError, TypeError):
			return []
	return []


def _format_patient_note(patient_text: str) -> str:
	sents = sent_tokenize(patient_text)
	sents.append(
		"The patient will provide informed consent, and will comply with the trial protocol without any practical issues."
	)
	return "\n".join(f"{idx}. {sent}" for idx, sent in enumerate(sents))


def _load_patient_text_map(matching_input_path: str | None) -> dict[str, str]:
	if not matching_input_path or not os.path.exists(matching_input_path):
		return {}
	try:
		rows = json.load(open(matching_input_path, encoding="utf-8"))
	except (json.JSONDecodeError, OSError):
		return {}
	out = {}
	for row in rows:
		pid = row.get("patient_id")
		text = row.get("patient")
		if pid and text:
			out[str(pid)] = text
	return out


def _normalize_aggregation_result(raw: dict) -> dict:
	r = raw.get("relevance_score_R", raw.get("relevance_score"))
	e = raw.get("eligibility_score_E", raw.get("eligibility_score"))
	return {
		"relevance_explanation": raw.get("relevance_explanation") or "",
		"relevance_score_R": float(r) if r is not None else 0.0,
		"eligibility_explanation": raw.get("eligibility_explanation") or "",
		"eligibility_score_E": float(e) if e is not None else 0.0,
	}


if __name__ == "__main__":
	corpus = sys.argv[1]
	model = sys.argv[2]
	matching_results_path = sys.argv[3]

	output_path = f"results/aggregation_results_{corpus}_{model}.json"

	run_aggregation_process(corpus, model, matching_results_path, output_path)


def run_aggregation_process(
	corpus,
	model,
	matching_results_path,
	output_path,
	llm_service=None,
	matching_input_path=None,
	reset_output=True,
):
	llm_service = resolve_workflow_llm_service(llm_service)

	if reset_output and os.path.exists(output_path):
		os.remove(output_path)

	results = json.load(open(matching_results_path, encoding="utf-8"))
	patient_text_map = _load_patient_text_map(matching_input_path)

	needed_trial_ids = set()
	for _, label_dict in results.items():
		for _, trials in label_dict.items():
			needed_trial_ids.update(trials.keys())

	trial_rows = fetch_trials_by_ids(list(needed_trial_ids))
	trial2info = {row["nct_id"]: row for row in trial_rows}

	output = {}
	aggregated_count = 0
	error_count = 0

	# Build the flat list of (patient, trial) aggregation calls up front so the LLM
	# round-trips can run concurrently instead of one blocking call at a time.
	tasks = []
	for patient_id, info in results.items():
		patient_raw = patient_text_map.get(patient_id) or fetch_compose_summary(patient_id)
		if not patient_raw:
			logger.warning(
				"Patient %s not found for aggregation (compose_summary_block and matching input).",
				patient_id,
			)
			continue

		patient = _format_patient_note(patient_raw)
		output[patient_id] = {}

		for label, trials in info.items():
			if not trials:
				continue

			for trial_id, trial_results in trials.items():
				if not isinstance(trial_results, dict):
					logger.warning(
						"Skipping aggregation for %s/%s: matching result is %s",
						patient_id,
						trial_id,
						type(trial_results).__name__,
					)
					error_count += 1
					continue

				if trial_id not in trial2info:
					logger.warning("Trial %s not found in trialgpt_corpus. Skipping.", trial_id)
					error_count += 1
					continue

				db_trial = trial2info[trial_id]
				trial_info = {
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
					"diseases_list": _coerce_json_list(db_trial.get("diseases")),
					"drugs_list": _coerce_json_list(db_trial.get("drugs")),
				}
				tasks.append((patient_id, trial_id, label, patient, trial_results, trial_info))

	import threading
	from concurrent.futures import ThreadPoolExecutor, as_completed
	from contextvars import copy_context

	try:
		workers = max(1, int(os.getenv("TRIALGPT_LLM_WORKERS", "4")))
	except (TypeError, ValueError):
		workers = 4

	lock = threading.Lock()

	def _persist():
		with open(output_path, "w", encoding="utf-8") as f:
			json.dump(output, f, indent=4)

	def _aggregate_one(patient, trial_results, trial_info):
		return trialgpt_aggregation(patient, trial_results, trial_info, model, llm_service)

	if tasks:
		with ThreadPoolExecutor(max_workers=workers) as executor:
			copied = copy_context()
			future_meta = {
				executor.submit(copied.run, _aggregate_one, patient, trial_results, trial_info): (
					patient_id,
					trial_id,
					label,
				)
				for (patient_id, trial_id, label, patient, trial_results, trial_info) in tasks
			}
			for future in as_completed(future_meta):
				patient_id, trial_id, label = future_meta[future]
				try:
					result = future.result()
				except Exception as e:
					logger.exception(
						"Error aggregating %s-%s (label=%s): %s",
						patient_id,
						trial_id,
						label,
						e,
					)
					with lock:
						error_count += 1
					continue

				with lock:
					output.setdefault(patient_id, {})[trial_id] = _normalize_aggregation_result(result)
					aggregated_count += 1
					_persist()
	else:
		_persist()

	logger.info(
		"Aggregation complete: %s pairs written, %s errors, output=%s",
		aggregated_count,
		error_count,
		output_path,
	)

	if aggregated_count == 0 and needed_trial_ids:
		raise RuntimeError(
			f"Aggregation produced zero scores for {len(needed_trial_ids)} trial(s). "
			f"See logs above (API key, model id, or JSON parse errors)."
		)

	return output
