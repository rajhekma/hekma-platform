# # __author__ = "qiao"

# # """
# # Running the TrialGPT matching for three cohorts (sigir, TREC 2021, TREC 2022).
# # """

# # import json
# # from nltk.tokenize import sent_tokenize
# # import os
# # import sys

# # try:
# # 	from TrialGPT import trialgpt_matching
# # except ImportError:
# # 	try:
# # 		from .TrialGPT import trialgpt_matching
# # 	except ImportError:
# # 		from trialgpt_matching.TrialGPT import trialgpt_matching 

# # def run_matching_process(retrieved_trials_path, output_path, model):
# # 	dataset = json.load(open(retrieved_trials_path))

# # 	# Dict{Str(patient_id): Dict{Str(label): Dict{Str(trial_id): Str(output)}}}
# # 	if os.path.exists(output_path):
# # 		output = json.load(open(output_path))
# # 	else:
# # 		output = {}

# # 	from tqdm import tqdm
# # 	for instance in tqdm(dataset):
# # 		# Dict{'patient': Str(patient), '0': Str(NCTID), ...}
# # 		patient_id = instance["patient_id"]
# # 		patient = instance["patient"]
# # 		sents = sent_tokenize(patient)
# # 		sents.append("The patient will provide informed consent, and will comply with the trial protocol without any practical issues.")
# # 		sents = [f"{idx}. {sent}" for idx, sent in enumerate(sents)]
# # 		patient = "\n".join(sents)

# # 		# initialize the patient id in the output 
# # 		if patient_id not in output:
# # 			output[patient_id] = {"0": {}, "1": {}, "2": {}}
		
# # 		# For Type 2 (Patient to Trials), the structure often has trials in labels or just a list. 
# # 		# The original code expects '0', '1', '2' keys which come from TREC qrels relevance levels.
# # 		# For a generic search, we might just have a list of candidates.
# # 		# We need to adapt to handle a flat list of trials if the '0','1','2' structure isn't present
# # 		# However, for now we will maintain compatibility with the retrieved_trials.json structure.
		
# # 		# Check if instance is flat list or labeled dict
# # 		# If it's a flat list of candidates (orchestration mode usually), we treat them all as "candidates"
# # 		# But the original code iterates ["2", "1", "0"].
		
# # 		# ADAPTATION: If the instance has a "candidates" key, use that.
# # 		if "candidates" in instance:
# # 			# Treat all as candidates, maybe assign to a dummy label '0' or processed differently
# # 			input_lists = {"candidates": instance["candidates"]}
# # 		else:
# # 			input_lists = {k: v for k, v in instance.items() if k in ["2", "1", "0"]}

# # 		for label, trial_list in input_lists.items():
# # 			for trial in trial_list: 
# # 				trial_id = trial["NCTID"]

# # 				# already calculated and cached
# # 				# Check if trial_id is in any of the labels in output
# # 				already_done = False
# # 				for l in ["0", "1", "2", "candidates"]:
# # 					if l in output[patient_id] and trial_id in output[patient_id][l]:
# # 						already_done = True
# # 						break
# # 				if already_done: continue

# # 				# Ensure output structure supports the label
# # 				if label not in output[patient_id]:
# # 					output[patient_id][label] = {}
				
# # 				# in case anything goes wrong (e.g., API calling errors)
# # 				try:
# # 					results = trialgpt_matching(trial, patient, model)
# # 					output[patient_id][label][trial_id] = results

# # 					with open(output_path, "w") as f:
# # 						json.dump(output, f, indent=4)

# # 				except Exception as e:
# # 					import traceback
# # 					print(f"\n[ERROR] {e}")
# # 					traceback.print_exc()
# # 					continue

# # 	# Ensure file is saved at least once (e.g. if dataset was empty)
# # 	if not os.path.exists(output_path) or output:
# # 		with open(output_path, "w") as f:
# # 			json.dump(output, f, indent=4)


# # if __name__ == "__main__":
# # 	corpus = sys.argv[1]
# # 	model = sys.argv[2] 
	
# # 	retrieved_trials_path = f"/home/mayu/Documents/Code/HEKMA/trailgpt/results_gpt5/qid2nctids_results_gpt-5.2-2025-12-11_sigir_k20_bm25wt1_medcptwt1_N20.json" #"dataset/{corpus}/retrieved_trials.json"
# # 	output_path = f"results_gpt5/matching_results_{corpus}_{model}.json"
	
# # 	run_matching_process(retrieved_trials_path, output_path, model)
"""
Running the TrialGPT matching for three cohorts (sigir, TREC 2021, TREC 2022).
"""
from dotenv import load_dotenv
load_dotenv()
import json
import argparse
from nltk.tokenize import sent_tokenize
import os

from contextvars import copy_context

from utils.matching_result_util import normalize_matching_results
from services.ai_usage import current_usage_patient_id, emit_llm_usage

try:
    from TrialGPT import trialgpt_matching as openai_matching
except ImportError:
    try:
        from .TrialGPT import trialgpt_matching as openai_matching
    except ImportError:
        from trialgpt_matching.TrialGPT import trialgpt_matching as openai_matching

def _gemini_unavailable(*args, **kwargs):
    raise RuntimeError(
        "Gemini matching is unavailable in this environment. "
        "Required cryptography/google runtime is blocked or not installed."
    )


try:
    from TrialGemini import trialgpt_matching as gemini_matching
except Exception:
    try:
        from .TrialGemini import trialgpt_matching as gemini_matching
    except Exception:
        try:
            from trialgpt_matching.TrialGemini import trialgpt_matching as gemini_matching
        except Exception:
            gemini_matching = _gemini_unavailable

def _claude_unavailable(*args, **kwargs):
    raise RuntimeError(
        "Claude matching is unavailable in this environment. "
        "Install anthropic dependencies and ensure runtime policy allows them."
    )


try:
    from TrialClaude import trialgpt_matching as claude_matching
except Exception:
    try:
        from .TrialClaude import trialgpt_matching as claude_matching
    except Exception:
        try:
            from trialgpt_matching.TrialClaude import trialgpt_matching as claude_matching
        except Exception:
            claude_matching = _claude_unavailable


def get_matching_fn(llm_service):
    if llm_service == "gemini":
        return gemini_matching
    if llm_service == "claude":
        return claude_matching
    return openai_matching


def _matching_workers() -> int:
    """Number of concurrent LLM matching calls (bounded for provider rate limits)."""
    try:
        return max(1, int(os.getenv("TRIALGPT_LLM_WORKERS", "4")))
    except (TypeError, ValueError):
        return 4


def run_matching_process(retrieved_trials_path, output_path, model, llm_service):
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    dataset = json.load(open(retrieved_trials_path))
    trialgpt_matching = get_matching_fn(llm_service)

    if os.path.exists(output_path):
        output = json.load(open(output_path))
    else:
        output = {}

    totals = {"input_tokens": 0, "output_tokens": 0, "trials": 0}
    lock = threading.Lock()

    def _persist():
        with open(output_path, "w") as f:
            json.dump(output, f, indent=4)

    def _match_one(patient_id, patient, label, trial):
        trial_id = trial["NCTID"]
        response_data = trialgpt_matching(trial, patient, model)
        normalized = normalize_matching_results(response_data["results"])
        usage = response_data.get("usage", {}) or {}
        emit_llm_usage(
            patient_id=current_usage_patient_id() or patient_id,
            product="trial_match",
            feature="trial_match.matching",
            provider=llm_service,
            model=model,
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            source_service="hekma-trialgpt",
        )
        return patient_id, label, trial_id, normalized, usage

    workers = _matching_workers()
    from tqdm import tqdm
    for instance in tqdm(dataset):
        patient_id = instance["patient_id"]
        patient = instance["patient"]
        sents = sent_tokenize(patient)
        sents.append("The patient will provide informed consent, and will comply with the trial protocol without any practical issues.")
        sents = [f"{idx}. {sent}" for idx, sent in enumerate(sents)]
        patient = "\n".join(sents)

        if patient_id not in output:
            output[patient_id] = {"0": {}, "1": {}, "2": {}}

        if "candidates" in instance:
            input_lists = {"candidates": instance["candidates"]}
        else:
            input_lists = {k: v for k, v in instance.items() if k in ["2", "1", "0"]}

        # Collect the candidate calls that still need an LLM round-trip so we can
        # run them concurrently instead of one blocking call at a time.
        pending = []
        for label, trial_list in input_lists.items():
            for trial in trial_list:
                trial_id = trial["NCTID"]
                already_done = any(
                    l in output[patient_id] and trial_id in output[patient_id][l]
                    for l in ["0", "1", "2", "candidates"]
                )
                if already_done:
                    continue
                if label not in output[patient_id]:
                    output[patient_id][label] = {}
                pending.append((label, trial))

        if not pending:
            continue

        with ThreadPoolExecutor(max_workers=workers) as executor:
            copied = copy_context()
            futures = [
                executor.submit(copied.run, _match_one, patient_id, patient, label, trial)
                for label, trial in pending
            ]
            for future in as_completed(futures):
                try:
                    pid, label, trial_id, normalized, usage = future.result()
                except Exception as e:
                    import traceback
                    print(f"\n[ERROR] {e}")
                    traceback.print_exc()
                    continue

                with lock:
                    output[pid].setdefault(label, {})[trial_id] = normalized
                    totals["input_tokens"] += usage.get("input_tokens", 0)
                    totals["output_tokens"] += usage.get("output_tokens", 0)
                    totals["trials"] += 1
                    _persist()

    total_input_tokens = totals["input_tokens"]
    total_output_tokens = totals["output_tokens"]
    total_trials_processed = totals["trials"]

    if not os.path.exists(output_path) or output:
        _persist()

    print(f"\n{'='*40}")
    print(f"Run complete: {total_trials_processed} trials processed")
    print(f"Total input tokens:  {total_input_tokens:,}")
    print(f"Total output tokens: {total_output_tokens:,}")
    print(f"Total tokens:        {total_input_tokens + total_output_tokens:,}")
    print(f"{'='*40}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run TrialGPT matching pipeline.")
    parser.add_argument("-c", "--corpus", required=True, help="Corpus name (e.g. sigir, trec2021, trec2022)")
    parser.add_argument("-m", "--model", required=True, help="Model name (e.g. gpt-4o, gemini-1.5-pro, claude-sonnet-4-6)")
    parser.add_argument("-l", "--llm", required=True, choices=["openai", "gemini", "claude"], help="LLM service to use")
    parser.add_argument("-i", "--input", required=True, help="Path to retrieved_trials JSON file")
    parser.add_argument("-o", "--output-dir", default="results", help="Directory for output JSON (default: results/)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, f"matching_results_{args.corpus}_{args.model}.json")

    run_matching_process(args.input, output_path, args.model, args.llm)
