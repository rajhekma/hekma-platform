""" Prompt optimized by Gemini v1"""
import json
import re
import sys
import time
import argparse
import os
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI
import anthropic

_TRAILGPT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _TRAILGPT_ROOT not in sys.path:
    sys.path.insert(0, _TRAILGPT_ROOT)
try:
    from trialgpt_matching.matching_prompt_policy import MATCHING_POLICY_BLOCK
except ImportError:
    MATCHING_POLICY_BLOCK = ""

OPENAI_CLIENT = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
ANTHROPIC_CLIENT = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

DEFAULT_MODEL = "claude-sonnet-4-6"
CONSENT_SENTENCE = "The patient will provide informed consent, and will comply with the trial protocol without any practical issues."

# The specific cohort requested
TARGET_PATIENTS = [
    'sigir-201424', 'sigir-20151', 'sigir-20155', 'sigir-20142', 
    'sigir-201414', 'sigir-201523', 'sigir-201513', 'sigir-20143', 
    'sigir-20159', 'sigir-201519'
]

def call_llm(system_prompt: str, user_prompt: str, model: str) -> dict:
    if model.startswith("claude"):
        resp = ANTHROPIC_CLIENT.messages.create(
            model=model,
            max_tokens=4096,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = resp.content[0].text.strip()
    else:
        resp = OPENAI_CLIENT.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
        )
        raw = resp.choices[0].message.content.strip()

    raw = re.sub(r'^```json|^```|```$', '', raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return {}

def parse_criteria(text: str) -> str:
    lines = [l.strip() for l in text.split("\n\n") if l.strip()]
    if len(lines) <= 1:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
    lines = [l for l in lines if not l.lower().startswith("inclusion")
             and not l.lower().startswith("exclusion") and l != ":"]
    return "\n".join(f"{i}. {c}" for i, c in enumerate(lines))

def print_trial(trial_info: dict, inc_exc: str) -> str:
    trial  = f"Title: {trial_info.get('brief_title', '')}\n"
    trial += f"Target diseases: {', '.join(trial_info.get('diseases_list', []))}\n"
    trial += f"Summary: {trial_info.get('brief_summary', '')}\n"

    if inc_exc == "inclusion":
        trial += "Inclusion criteria:\n %s\n" % parse_criteria(trial_info.get('inclusion_criteria', ''))
    elif inc_exc == "exclusion":
        trial += "Exclusion criteria:\n %s\n" % parse_criteria(trial_info.get('exclusion_criteria', ''))

    return trial

def get_matching_prompt(trial_info: dict, inc_exc: str, patient_note: str, profile: dict) -> tuple[str, str]:
    # Exclude _expanded as requested
    profile_clean = {k: v for k, v in profile.items() if k != "_expanded"}
    
    system_prompt = (
        "### Role\n"
        "You are an expert Clinical Trial Investigator. Determine patient eligibility "
        f"for {inc_exc} criteria using the provided Patient Note and Structured Profile.\n\n"
        
        "### Decision Logic\n"
        "1. **Exclusion Skepticism**: Be extremely conservative with the 'excluded' label. "
        "Only use 'excluded' if there is EXPLICIT evidence in the Note or Profile that the "
        "patient meets the disqualifying criteria. If the note is vague, default to 'not excluded'.\n"
        
        "2. **The Absence Rule vs. NEI**:\n"
        "   - Use the **Absence Rule** (and `[]` IDs) for common, high-level comorbidities "
        "like HIV, Cancer, Diabetes, or Pregnancy.\n"
        "   - Use **'not enough information'** (and `[]` IDs) for specific clinical details "
        "that a doctor might reasonably omit even if present, such as: specific surgery dates, "
        "minor secondary symptoms, or administrative requirements (insurance, distance to clinic).\n"
        
        "3. **Strict Thresholds**: Continue using 'not enough information' for missing numeric values "
        "(e.g., LVEF < 40%, HbA1c > 7) unless a specific diagnosis in the profile confirms the severity.\n"
        
        "### Examples of Correct Evidence Handling:\n"
        "**Case 1 (Absence)**: Criterion: 'No history of HIV.' -> Note/Profile don't mention HIV. "
        "Output: [\"No mention of HIV in clinical data; assumed absent.\", [], \"not excluded\"]\n"
        "**Case 2 (Threshold Missing)**: Criterion: 'HbA1c > 7.0%.' -> Note says 'Diabetes' but no labs. "
        "Output: [\"Patient has diabetes, but specific HbA1c value is missing.\", [], \"not enough information\"]\n\n"
        
        "### Output Format\n"
        "Return ONLY a JSON dictionary {criterion_number: [reasoning, sentence_ids, label]}.\n"
    )

    if inc_exc == "inclusion":
        system_prompt += 'Label set: {"not applicable", "not enough information", "included", "not included"}'
    else:
        system_prompt += 'Label set: {"not applicable", "not enough information", "excluded", "not excluded"}'
    if MATCHING_POLICY_BLOCK:
        system_prompt += MATCHING_POLICY_BLOCK

    user_prompt = (
        f"### Structured Patient Profile:\n{json.dumps(profile_clean, indent=2)}\n\n"
        f"### Patient Note (ID-indexed):\n{patient_note}\n\n"
        f"### {inc_exc.capitalize()} Criteria:\n{print_trial(trial_info, inc_exc)}\n\n"
        "### JSON Output:"
    )

    return system_prompt, user_prompt

def format_patient_with_ids(raw_note: str) -> str:
    note_with_consent = raw_note.strip() + " " + CONSENT_SENTENCE
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', note_with_consent) if s.strip()]
    return "\n".join(f"{i}. {s}" for i, s in enumerate(sentences))


def reason_trial(patient_text: str, profile: dict, trial: dict, model: str, max_retries: int = 3) -> dict:
    trial_results = {"inclusion": {}, "exclusion": {}}

    for inc_exc in ["inclusion", "exclusion"]:
        # Only process if criteria exist
        if not trial.get(f"{inc_exc}_criteria", "").strip():
            continue

        success = False
        attempt = 0
        while attempt < max_retries and not success:
            sys_p, usr_p = get_matching_prompt(trial, inc_exc, patient_text, profile)
            res = call_llm(sys_p, usr_p, model)
            
            # RETRY LOGIC: If the result is empty or invalid, retry
            if res and isinstance(res, dict) and len(res) > 0:
                trial_results[inc_exc] = res
                success = True
            else:
                attempt += 1
                if attempt < max_retries:
                    print(f"    [retry] Empty response for {inc_exc}. Retrying in 2s... ({attempt}/{max_retries})")
                    time.sleep(2)
        
        if not success:
            print(f"    [failed] Could not get {inc_exc} results after {max_retries} attempts.")

    return trial_results

def run(retrieved_path: str, profile_path: str, output_path: str, model: str, data_mode: str):
    with open(retrieved_path) as f:
        retrieved = json.load(f)
    with open(profile_path) as f:
        all_profiles = json.load(f)

    # Load existing progress to support resuming
    results = {}
    if os.path.exists(output_path):
        try:
            with open(output_path, "r") as f:
                results = json.load(f)
        except:
            results = {}

    # Filter strictly for requested patient IDs
    
    # filtered_data = [e for e in retrieved if e["patient_id"] in TARGET_PATIENTS]

    # for i, entry in enumerate(filtered_data, 1):
    if data_mode == "filtered":
        selected_data = [e for e in retrieved if e["patient_id"] in TARGET_PATIENTS]
    else:
        selected_data = retrieved

    for i, entry in enumerate(selected_data, 1):
        patient_id = entry["patient_id"]
        
        # Skip if already done
        if patient_id in results and results[patient_id].get("0"):
            print(f"[{i}/{len(selected_data)}] Skipping {patient_id} (already exists)")
            continue

        patient_raw = entry["patient"]
        trials = entry.get("0", [])
        profile = all_profiles.get(patient_id, {})
        patient_text = format_patient_with_ids(patient_raw)

        print(f"[{i}/{len(selected_data)}] Processing {patient_id} ({len(trials)} trials)")
        results[patient_id] = {"0": {}}

        for trial in tqdm(trials, desc=f"Patient {patient_id}", leave=False):
            nct_id = trial.get("NCTID", "unknown")
            results[patient_id]["0"][nct_id] = reason_trial(patient_text, profile, trial, model)

        # SAVE AFTER EVERY PATIENT
        with open(output_path, "w") as f:
            json.dump(results, f, indent=4)
        print(f"  -> {patient_id} complete. Progress saved.")

    print(f"\n[done] All target patients processed. Saved to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--retrieved", required=True)
    parser.add_argument("-p", "--profiles", default="profiles.json")
    parser.add_argument("-o", "--output", default="reasoning_results_v3_1.json")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "-dm",
        "--data_mode",
        type=str,
        choices=["full", "filtered"],
        default="filtered",
        help="Whether to use full retrieved data or only TARGET_PATIENTS-filtered data.",
    )
    args = parser.parse_args()

    run(args.retrieved, args.profiles, args.output, args.model, args.data_mode)