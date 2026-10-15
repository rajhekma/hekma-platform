__author__ = "qiao"

"""
TrialGPT-Matching main functions (OpenAI version).
"""

import json
import os
from openai import OpenAI

try:
    from .matching_prompt_policy import MATCHING_POLICY_BLOCK
except ImportError:
    from trialgpt_matching.matching_prompt_policy import MATCHING_POLICY_BLOCK


api_key = os.getenv("OPENAI_API_KEY", "")
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set.")

client = OpenAI(api_key=api_key)


def parse_criteria(criteria):
    output = ""
    criteria = criteria.split("\n\n")
    idx = 0
    for criterion in criteria:
        criterion = criterion.strip()
        if "inclusion criteria" in criterion.lower() or "exclusion criteria" in criterion.lower():
            continue
        if len(criterion) < 5:
            continue
        output += f"{idx}. {criterion}\n"
        idx += 1
    return output


def print_trial(trial_info: dict, inc_exc: str) -> str:
    trial = f"Title: {trial_info['brief_title']}\n"
    trial += f"Target diseases: {', '.join(trial_info['diseases_list'])}\n"
    trial += f"Interventions: {', '.join(trial_info['drugs_list'])}\n"
    trial += f"Summary: {trial_info['brief_summary']}\n"
    if inc_exc == "inclusion":
        trial += "Inclusion criteria:\n %s\n" % parse_criteria(trial_info['inclusion_criteria'])
    elif inc_exc == "exclusion":
        trial += "Exclusion criteria:\n %s\n" % parse_criteria(trial_info['exclusion_criteria'])
    return trial


def get_matching_prompt(trial_info: dict, inc_exc: str, patient: str) -> tuple[str, str]:
    prompt = (
        "You are a helpful assistant for clinical trial recruitment. "
        f"Your task is to compare a given patient note and the {inc_exc} criteria "
        "of a clinical trial to determine the patient's eligibility at the criterion level.\n"
    )
    if inc_exc == "inclusion":
        prompt += (
            "The factors that allow someone to participate in a clinical study "
            "are called inclusion criteria. They are based on characteristics such as age, "
            "gender, the type and stage of a disease, previous treatment history, "
            "and other medical conditions.\n"
        )
    elif inc_exc == "exclusion":
        prompt += (
            "The factors that disqualify someone from participating are called exclusion criteria. "
            "They are based on characteristics such as age, gender, the type and stage of a disease, "
            "previous treatment history, and other medical conditions.\n"
        )
    prompt += MATCHING_POLICY_BLOCK
    prompt += f"You should check the {inc_exc} criteria one-by-one, and output the following three elements for each criterion:\n"
    prompt += (
        f"\tElement 1. For each {inc_exc} criterion, briefly generate your reasoning process. "
        "First, judge whether the criterion is not applicable. Then check direct evidence. "
        "Only infer where the GLOBAL POLICY above allows; never infer age from DOB or dates, and never "
        "replace investigator-opinion criteria with your own judgment. Otherwise infer conservatively "
        "and avoid overusing 'not enough information'.\n"
    )
    prompt += (
        "\tElement 2. If relevant information exists, generate a list of sentence IDs. "
        "Otherwise annotate an empty list.\n"
    )
    prompt += "\tElement 3. Classify eligibility.\n"
    if inc_exc == "inclusion":
        prompt += 'Label must be one of {"not applicable", "not enough information", "included", "not included"}.\n'
    elif inc_exc == "exclusion":
        prompt += 'Label must be one of {"not applicable", "not enough information", "excluded", "not excluded"}.\n'
    prompt += (
        "You should output only a JSON dict exactly formatted as: "
        "dict{str(criterion_number): "
        "list[str(element_1_brief_reasoning), list[int(element_2_sentence_id)], "
        "str(element_3_eligibility_label)]}."
    )
    user_prompt = f"Here is the patient note, each sentence is led by a sentence_id:\n{patient}\n\n"
    user_prompt += f"Here is the clinical trial:\n{print_trial(trial_info, inc_exc)}\n\n"
    user_prompt += "Plain JSON output:"
    return prompt, user_prompt


def trialgpt_matching(trial: dict, patient: str, model: str):
    results = {}
    total_input_tokens = 0
    total_output_tokens = 0

    for inc_exc in ["inclusion", "exclusion"]:
        system_prompt, user_prompt = get_matching_prompt(trial, inc_exc, patient)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )

        total_input_tokens += response.usage.prompt_tokens
        total_output_tokens += response.usage.completion_tokens

        message = response.choices[0].message.content.strip()
        message = message.strip("`").strip("json")

        try:
            results[inc_exc] = json.loads(message)
        except Exception:
            results[inc_exc] = message

    return {
        "results": results,
        "usage": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
        },
    }
