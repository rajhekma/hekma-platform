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
CONSENT_SENTENCE = "The patient has voluntarily provided written informed consent and is fully willing and able to comply with all study procedures, restrictions, diary cards, and protocol requirements."

# The specific cohort requested
TARGET_PATIENTS = [
    '009de56a-60d0-512a-97c8-c7fe0d949382',
    '0052e85d-53e3-5659-af83-ea58a696fbc9',
    '004fec23-6023-572a-922e-6d73b325e771',
    '00bf0672-1125-5fee-b375-838a4e4628a1',
    '00bf3895-2908-5212-90b2-ad471e5173c2',
    '00bfa868-a2cd-534d-985b-0b14925d3b48',
    '00c0260b-9c66-55f9-9bfa-7f7792cb0a1b', 
    '00c03471-65b1-5c2e-9667-6b1f20c1688f',
    '00c0703e-143c-5487-ad6b-700a4f229ac1',
    '00c09a05-4c3f-5595-b2ac-19d52854041c',
    '00c0a6b3-04d7-54fd-995f-84a494accb3b',
    '00c0ab5b-4c5c-5e27-9a48-86a3877909cf',
    '00c16018-ef4f-530d-bdc0-3e9ced90dbce',
    '00c0cccc-04eb-5440-aa17-8958f5d15fc0',
    '00c13f8d-c0c1-55f2-b2d5-eab8ea4fdae2',
    '00c1447c-399a-5115-9224-d80bad5017ec',
    '00c14bf2-f57d-5a6a-a4aa-07d3a939bb40',
    '00c151da-49bd-5bd2-b837-16bd53df50cb',
    '00c1613c-12d2-5a2c-adb2-977b92ed765f',
    '00c1bc9d-afce-5409-88a9-b8e0d1b0e2a5',
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

def print_trial_v2(trial_info: dict, inc_exc: str) -> str:
    trial  = f"Title: {trial_info.get('brief_title', '')}\n"
    trial += f"Target diseases: {', '.join(trial_info.get('diseases', []))}\n"
    trial += f"Summary: {trial_info.get('brief_summary', '')}\n"
    if inc_exc == "inclusion":
        criteria = trial_info.get('inclusion_criteria', {})
        trial += "Inclusion criteria:\n"
        trial += "\n".join(f" {k}. {v}" for k, v in criteria.items()) + "\n"
    elif inc_exc == "exclusion":
        criteria = trial_info.get('exclusion_criteria', {})
        trial += "Exclusion criteria:\n"
        trial += "\n".join(f" {k}. {v}" for k, v in criteria.items()) + "\n"
    return trial

def get_matching_prompt(trial_info: dict, inc_exc: str, patient_note: str, profile: dict) -> tuple[str, str]:
    # Exclude _expanded as requested
    #profile_clean = {k: v for k, v in profile.items() if k != "_expanded"}
    
    system_prompt = (
    "### Role\n"
    "You are an expert Clinical Trial Investigator. Evaluate patient eligibility for each "
    f"{'inclusion' if inc_exc == 'inclusion' else 'exclusion'} criterion using the provided Patient Profile.\n\n"

    "### Core Decision Rules\n"
    "1. **Explicit Evidence Required**: For both inclusion and exclusion, a label of 'included'/'excluded' "
    "requires explicit or strongly implied evidence in the Patient Profile. Do not assume fulfillment.\n\n"

    "2. **Absence Rule**: If the Patient Profile does not mention a current, active, diagnosable "
    "condition (e.g., HIV, cancer, pregnancy, diabetes), assume it is absent. Do not label these "
    "as 'not enough information'.\n\n"
    "**Do NOT apply the Absence Rule to:**\n"
    "- Historical or resolved conditions\n"
    "- Drug pharmacological classes (e.g., CYP3A4 inhibitors)\n"
    "- Administrative criteria (e.g., trial participation history, ability to provide consent)\n"
    "For these, use NEI if information is missing.\n\n"

    "3. **Date Handling**: Patient dates (DOB, test dates, procedure dates) may have been "
    "anonymized and are unreliable. Do not use DOB or any date in the profile to infer age "
    "under any circumstances. If a criterion requires age verification, label it as "
    "'not enough information' unless age is explicitly stated as a plain value in the profile "
    "(e.g., 'Patient is 45 years old' or 'Age: 45').\n\n"

    "4. **Not Enough Information (NEI)**: Use NEI only for specific clinical details a physician might "
    "reasonably omit even if present — such as exact lab values, surgery dates, or specific drug dosages. "
    "Minimize NEI usage; default to the Absence Rule where applicable.\n\n"

    "5. **Numeric Thresholds**: If a threshold-based criterion (e.g., HbA1c > 7%, LVEF < 40%) is not "
    "explicitly documented, use NEI. If a value is present, apply the threshold strictly — borderline "
    "values that meet the threshold satisfy the criterion.\n\n"

    "6. **Compound Criteria**: For criteria with multiple sub-conditions joined by 'or', the criterion "
    "is met if ANY sub-condition is met. For 'and', ALL sub-conditions must be met. Evaluate each "
    "sub-condition separately in reasoning before assigning the final label.\n\n"

    "7. **Not Applicable**: Use only when a criterion is structurally inapplicable to the patient "
    "(e.g., a pregnancy criterion for a documented male patient).\n\n"

    "8. **Investigator Judgment Criteria**: For criteria that explicitly require investigator opinion, "
    "clinical judgment, or use language like 'according to the investigator', 'in the opinion of', "
    "'at the discretion of' — do NOT attempt to make a final decision. Label as 'not enough information' "
    "and flag in reasoning that this requires human investigator review.\n\n"

    "### Examples\n"
    "**Absence Rule**: Criterion: 'No history of HIV.' Profile silent on HIV. "
    "-> [\"No mention of HIV; assumed absent per Absence Rule.\", \"\", \"not excluded\"]\n\n"

    "**NEI for lab value**: Criterion: 'HbA1c > 7.0%.' Profile mentions diabetes but no labs. "
    "-> [\"Diabetes noted but HbA1c value not documented.\", \"diabetes\", \"not enough information\"]\n\n"

    "**Borderline threshold**: Criterion: 'HbA1c > 7.0%.' Profile shows HbA1c = 7.1%. "
    "-> [\"HbA1c of 7.1% exceeds the 7.0% threshold.\", \"HbA1c = 7.1%\", \"excluded\"]\n\n"

    "**Compound OR**: Criterion: 'Arthritis OR skin rash OR oral ulcers.' Profile mentions skin rash. "
    "-> [\"Skin rash explicitly documented; OR condition satisfied.\", \"skin rash\", \"included\"]\n\n"

    "**Not Applicable**: Criterion: 'Not pregnant or lactating.' Profile documents patient is male. "
    "-> [\"Criterion not applicable to male patient.\", \"male\", \"not applicable\"]\n\n"

    "**Age NEI**: Criterion: 'Age > 18 years.' Profile contains DOB but no explicit age statement. "
    "-> [\"DOB present but unreliable; age not explicitly stated.\", \"\", \"not enough information\"]\n\n"

    "**Investigator Judgment**: Criterion: 'Any condition that may render the diagnosis doubtful, "
    "according to the opinion of the investigator.' "
    "-> [\"This criterion requires investigator clinical judgment and cannot be determined from the profile alone. "
    "Human review required.\", \"\", \"not enough information\"]\n\n"

    "### Output Format\n"
    "Return ONLY a valid JSON dictionary in this exact format:\n"
    "{criterion_number: [\"reasoning\", \"relevant profile excerpt or empty string\", \"label\"]}\n"
    "No extra text, no markdown, no preamble.\n\n"
)
    if inc_exc == "inclusion":
        system_prompt += 'Label set: {"not applicable", "not enough information", "included", "not included"}\n'
    else:
        system_prompt += 'Label set: {"not applicable", "not enough information", "excluded", "not excluded"}\n'
    if MATCHING_POLICY_BLOCK:
        system_prompt += MATCHING_POLICY_BLOCK

    user_prompt = (
        f"### Structured Patient Profile:\n{profile}\n\n" #{json.dumps(profile_clean, indent=2)}\n\n"
        f"### Patient Note (ID-indexed):\n{patient_note}\n\n"
        f"### {inc_exc.capitalize()} Criteria:\n{print_trial_v2(trial_info, inc_exc)}\n\n"
        "### JSON Output:"
    )


    return system_prompt, user_prompt

def format_patient_with_ids(raw_note: str) -> str:
    note_with_consent = raw_note.strip() # + " " + CONSENT_SENTENCE
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', note_with_consent) if s.strip()]
    return "\n".join(f"{i}. {s}" for i, s in enumerate(sentences))


def reason_trial(patient_text: str, profile: dict, trial: dict, model: str, max_retries: int = 3) -> dict:
    trial_results = {"inclusion": {}, "exclusion": {}}

    for inc_exc in ["inclusion", "exclusion"]:
        # Only process if criteria exist
        if not trial.get(f"{inc_exc}_criteria", ""):
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
