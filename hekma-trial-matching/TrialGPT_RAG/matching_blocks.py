import json
import argparse
import os
from tqdm import tqdm
from matching_utils import (
    call_llm, reason_trial,
    parse_criteria, print_trial, get_matching_prompt,
    CONSENT_SENTENCE, TARGET_PATIENTS, DEFAULT_MODEL,
)


def load_retrieved(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_corpus(path: str) -> dict[str, dict]:
    corpus = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            trial = json.loads(line)
            nct_id = trial.get("nct_id")
            if nct_id:
                corpus[nct_id] = trial
    return corpus


def build_patient_text(raw_profile: dict) -> str:
    lines = []
    for key, value in raw_profile.items():
        if value:
            lines.append(f"{key}: {value}")
    #lines.append(f"consent: {CONSENT_SENTENCE}")
    return "\n".join(f"{i}. {line}" for i, line in enumerate(lines))


def build_trial_info(corpus_entry: dict) -> dict:
    m = corpus_entry.get("metadata", {})
    return {
        "brief_title":        corpus_entry.get("title", m.get("brief_title", "")),
        "brief_summary":      m.get("brief_summary", ""),
        "diseases_list":      m.get("diseases_list", []),
        "inclusion_criteria": m.get("inclusion_criteria", ""),
        "exclusion_criteria": m.get("exclusion_criteria", ""),
    }

def build_trial_info_v2(parsed_entry: dict) -> dict:
    return {
        "brief_title":        parsed_entry.get("brief_title", ""),
        "brief_summary":      parsed_entry.get("brief_summary", ""),
        "diseases":           parsed_entry.get("diseases", []),
        "inclusion_criteria": parsed_entry.get("inclusion_criteria", {}),
        "exclusion_criteria": parsed_entry.get("exclusion_criteria", {}),
    }


def run(retrieved_path: str, corpus_path: str, output_path: str, model: str, data_mode: str, threshold: float):
    retrieved = load_retrieved(retrieved_path)
    corpus    = load_corpus(corpus_path)

    results = {}
    if os.path.exists(output_path):
        try:
            with open(output_path, encoding="utf-8") as f:
                results = json.load(f)
        except Exception:
            results = {}

    if data_mode == "filtered":
        selected_ids = [pid for pid in retrieved if pid in TARGET_PATIENTS]
    else:
        selected_ids = list(retrieved.keys())

    for i, patient_id in enumerate(selected_ids, 1):
        if patient_id in results and results[patient_id].get("0"):
            print(f"[{i}/{len(selected_ids)}] Skipping {patient_id} (already exists)")
            continue

        entry       = retrieved[patient_id]
        raw_profile = entry.get("raw_profile", {})
        trials      = entry.get("trials", [])

        patient_text = build_patient_text(raw_profile)

        filtered_trials = [t for t in trials if t.get("score", 0) >= threshold]
        print(f"[{i}/{len(selected_ids)}] {patient_id} — {len(filtered_trials)}/{len(trials)} trials above threshold {threshold}")

        results[patient_id] = {"0": {}}

        for trial_stub in tqdm(filtered_trials, desc=f"Patient {patient_id}", leave=False):
            nct_id = trial_stub.get("nct_id", "unknown")

            if nct_id not in corpus:
                print(f"    [warn] {nct_id} not found in corpus, skipping.")
                continue

            trial_info = build_trial_info_v2(corpus[nct_id])
            results[patient_id]["0"][nct_id] = reason_trial(patient_text, raw_profile, trial_info, model)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4)
        print(f"  -> {patient_id} complete. Progress saved.")

    print(f"\n[done] Saved to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Matching v4 — uses new retrieval structure")
    parser.add_argument("-r",  "--retrieved", required=True,                  help="Path to retrieved JSON (new format)")
    parser.add_argument("-c",  "--corpus",    required=True,                  help="Path to corpus.jsonl")
    parser.add_argument("-o",  "--output",    default="reasoning_results_v4.json")
    parser.add_argument("-m",  "--model",     default=DEFAULT_MODEL)
    parser.add_argument("-t",  "--threshold", type=float, default=0.1,        help="Minimum trial score to process")
    parser.add_argument("-dm", "--data_mode", choices=["full", "filtered"],   default="filtered")
    args = parser.parse_args()

    run(args.retrieved, args.corpus, args.output, args.model, args.data_mode, args.threshold)
