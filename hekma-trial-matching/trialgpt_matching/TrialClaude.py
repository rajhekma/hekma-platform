# __author__ = "qiao"

# """
# TrialGPT-Matching main functions (Claude/Anthropic version).
# """

# import json
# import os
# import anthropic


# api_key = os.getenv("ANTHROPIC_API_KEY", "")
# if not api_key:
#     raise ValueError("ANTHROPIC_API_KEY environment variable not set.")

# client = anthropic.Anthropic(api_key=api_key)


# def parse_criteria(criteria):
#     output = ""
#     criteria = criteria.split("\n\n")
#     idx = 0
#     for criterion in criteria:
#         criterion = criterion.strip()
#         if "inclusion criteria" in criterion.lower() or "exclusion criteria" in criterion.lower():
#             continue
#         if len(criterion) < 5:
#             continue
#         output += f"{idx}. {criterion}\n"
#         idx += 1
#     return output


# def print_trial(trial_info: dict, inc_exc: str) -> str:
#     trial = f"Title: {trial_info['brief_title']}\n"
#     trial += f"Target diseases: {', '.join(trial_info['diseases_list'])}\n"
#     trial += f"Interventions: {', '.join(trial_info['drugs_list'])}\n"
#     trial += f"Summary: {trial_info['brief_summary']}\n"
#     if inc_exc == "inclusion":
#         trial += "Inclusion criteria:\n %s\n" % parse_criteria(trial_info['inclusion_criteria'])
#     elif inc_exc == "exclusion":
#         trial += "Exclusion criteria:\n %s\n" % parse_criteria(trial_info['exclusion_criteria'])
#     return trial


# # def get_matching_prompt(trial_info: dict, inc_exc: str, patient: str) -> tuple[str, str]:
# #     prompt = (
# #         "You are a helpful assistant for clinical trial recruitment. "
# #         f"Your task is to compare a given patient note and the {inc_exc} criteria "
# #         "of a clinical trial to determine the patient's eligibility at the criterion level.\n"
# #     )
# #     if inc_exc == "inclusion":
# #         prompt += (
# #             "The factors that allow someone to participate in a clinical study "
# #             "are called inclusion criteria. They are based on characteristics such as age, "
# #             "gender, the type and stage of a disease, previous treatment history, "
# #             "and other medical conditions.\n"
# #         )
# #     elif inc_exc == "exclusion":
# #         prompt += (
# #             "The factors that disqualify someone from participating are called exclusion criteria. "
# #             "They are based on characteristics such as age, gender, the type and stage of a disease, "
# #             "previous treatment history, and other medical conditions.\n"
# #         )
# #     prompt += f"You should check the {inc_exc} criteria one-by-one, and output the following three elements for each criterion:\n"
# #     prompt += (
# #         f"\tElement 1. For each {inc_exc} criterion, briefly generate your reasoning process. "
# #         "First, judge whether the criterion is not applicable. Then check direct evidence. "
# #         "If none, infer carefully. Avoid overusing 'not enough information'.\n"
# #     )
# #     prompt += (
# #         "\tElement 2. If relevant information exists, generate a list of sentence IDs. "
# #         "Otherwise annotate an empty list.\n"
# #     )
# #     prompt += "\tElement 3. Classify eligibility.\n"
# #     if inc_exc == "inclusion":
# #         prompt += 'Label must be one of {"not applicable", "not enough information", "included", "not included"}.\n'
# #     elif inc_exc == "exclusion":
# #         prompt += 'Label must be one of {"not applicable", "not enough information", "excluded", "not excluded"}.\n'
# #     prompt += (
# #         "You should output only a JSON dict exactly formatted as: "
# #         "dict{str(criterion_number): "
# #         "list[str(element_1_brief_reasoning), list[int(element_2_sentence_id)], "
# #         "str(element_3_eligibility_label)]}."
# #     )
# #     user_prompt = f"Here is the patient note, each sentence is led by a sentence_id:\n{patient}\n\n"
# #     user_prompt += f"Here is the clinical trial:\n{print_trial(trial_info, inc_exc)}\n\n"
# #     user_prompt += "Plain JSON output:"
# #     return prompt, user_prompt
# def get_matching_prompt(trial_info: dict, inc_exc: str, patient: str) -> tuple[str, str]:

#     system_prompt = f"""
# <role>
# Clinical trial recruitment assistant.
# </role>

# <task>
# Compare the patient note with the {inc_exc} criteria of a clinical trial.
# Determine eligibility at the criterion level.
# Evaluate each criterion one-by-one.
# </task>

# <evaluation_steps>
# For each criterion:

# 1. Briefly generate reasoning.
#    - First determine whether the criterion is not applicable.
#    - Then check for direct evidence in the patient note.
#    - If no direct evidence is found, infer carefully based on context.
#    - Avoid overusing "not enough information".

# 2. If relevant supporting information exists, list sentence IDs.
#    Otherwise return [].

# 3. Assign an eligibility label.
# </evaluation_steps>
# """

#     if inc_exc == "inclusion":
#         system_prompt += """
# <label_space>
# Allowed labels:
# - "not applicable"
# - "not enough information"
# - "included"
# - "not included"
# </label_space>
# """
#     elif inc_exc == "exclusion":
#         system_prompt += """
# <label_space>
# Allowed labels:
# - "not applicable"
# - "not enough information"
# - "excluded"
# - "not excluded"
# </label_space>
# """

#     system_prompt += """
# <output_format>
# Return ONLY valid JSON.

# Format:
# {
#   "criterion_number": [
#       "brief reasoning",
#       [list_of_sentence_ids],
#       "eligibility_label"
#   ]
# }

# Do not include markdown or explanations.
# </output_format>
# """

#     user_prompt = f"""
# <patient_note>
# Each sentence begins with a sentence_id.
# {patient}
# </patient_note>

# <trial_information>
# {print_trial(trial_info, inc_exc)}
# </trial_information>

# Return JSON only.
# """

#     return system_prompt.strip(), user_prompt.strip()

# def trialgpt_matching(trial: dict, patient: str, model: str):
#     results = {}
#     total_input_tokens = 0
#     total_output_tokens = 0

#     for inc_exc in ["inclusion", "exclusion"]:
#         system_prompt, user_prompt = get_matching_prompt(trial, inc_exc, patient)

#         response = client.messages.create(
#             model=model,
#             max_tokens=1024,
#             system=system_prompt,
#             messages=[{"role": "user", "content": user_prompt}],
#         )

#         total_input_tokens += response.usage.input_tokens
#         total_output_tokens += response.usage.output_tokens

#         message = response.content[0].text.strip()
#         message = message.strip("`").strip("json")

#         try:
#             results[inc_exc] = json.loads(message)
#         except Exception:
#             results[inc_exc] = message

#     return {
#         "results": results,
#         "usage": {
#             "input_tokens": total_input_tokens,
#             "output_tokens": total_output_tokens,
#         },
#     }
# __author__ = "qiao (improved)"

# """
# TrialGPT-Matching main functions (Claude/Anthropic version).

# Improvements:
# 1. LLM-based term normalization pre-step (targets medical knowledge errors)
# 2. Richer inclusion prompt with explicit implicit-inference chain
# 3. Rewritten exclusion prompt with distinct label definitions and decision guide
# 4. Inclusion context passthrough removed (was causing error propagation)
# 5. JSON parse retry with corrective follow-up before falling back
# """

# import json
# import os
# import anthropic

# api_key = os.getenv("ANTHROPIC_API_KEY", "")
# if not api_key:
#     raise ValueError("ANTHROPIC_API_KEY environment variable not set.")

# client = anthropic.Anthropic(api_key=api_key)


# # ---------------------------------------------------------------------------
# # Term normalization
# # ---------------------------------------------------------------------------

# def normalize_patient_note(patient: str, model: str) -> str:
#     """
#     Expand abbreviations and append canonical synonyms inline.
#     E.g. 'HTN' -> 'HTN (hypertension)', 'T2DM' -> 'T2DM (type 2 diabetes mellitus)'.
#     Does not restructure or interpret the note.
#     """
#     system_prompt = """You are a clinical NLP assistant. Normalize a patient note by:
# - Expanding common medical abbreviations inline (e.g. HTN → HTN (hypertension))
# - Appending canonical synonyms for non-standard terms in parentheses

# Rules:
# - Do NOT change sentence structure or remove any information
# - Do NOT add clinical interpretation
# - Only annotate terms with well-established canonical equivalents
# - Output only the normalized note, nothing else"""

#     response = client.messages.create(
#         model=model,
#         max_tokens=1024,
#         system=system_prompt,
#         messages=[{"role": "user", "content": f"Patient note:\n{patient}\n\nNormalized note:"}],
#     )
#     return response.content[0].text.strip()


# # ---------------------------------------------------------------------------
# # Criteria parsing / trial formatting
# # ---------------------------------------------------------------------------

# def parse_criteria(criteria):
#     output = ""
#     criteria = criteria.split("\n\n")
#     idx = 0
#     for criterion in criteria:
#         criterion = criterion.strip()
#         if "inclusion criteria" in criterion.lower() or "exclusion criteria" in criterion.lower():
#             continue
#         if len(criterion) < 5:
#             continue
#         output += f"{idx}. {criterion}\n"
#         idx += 1
#     return output


# def print_trial(trial_info: dict, inc_exc: str) -> str:
#     trial = f"Title: {trial_info['brief_title']}\n"
#     trial += f"Target diseases: {', '.join(trial_info['diseases_list'])}\n"
#     trial += f"Interventions: {', '.join(trial_info['drugs_list'])}\n"
#     trial += f"Summary: {trial_info['brief_summary']}\n"
#     if inc_exc == "inclusion":
#         trial += "Inclusion criteria:\n %s\n" % parse_criteria(trial_info['inclusion_criteria'])
#     elif inc_exc == "exclusion":
#         trial += "Exclusion criteria:\n %s\n" % parse_criteria(trial_info['exclusion_criteria'])
#     return trial


# # ---------------------------------------------------------------------------
# # Prompt construction
# # ---------------------------------------------------------------------------

# def get_inclusion_prompt(trial_info: dict, patient: str) -> tuple[str, str]:
#     system_prompt = """
# <role>
# Clinical trial recruitment assistant.
# </role>

# <task>
# Compare the patient note with the INCLUSION criteria of a clinical trial.
# Determine eligibility at the criterion level. Evaluate each criterion one-by-one.
# </task>

# <evaluation_steps>
# For each inclusion criterion:

# 1. Reasoning — follow this chain:
#    (a) Is the criterion applicable? If the criterion assumes a context the patient clearly lacks, mark "not applicable".
#    (b) Is there DIRECT evidence in the note? If yes, state whether the patient meets or does not meet the criterion.
#    (c) If no direct evidence: ask — "Is this criterion about a routine, universally-documented clinical fact (e.g. age, sex, primary diagnosis)?"
#        - If YES and the note omits it entirely → lean toward "not included"
#        - If NO (e.g. rare comorbidity, prior niche therapy, specialist finding) → "not enough information"
#    Reserve "not included" for cases where absence of mention is itself strong evidence of absence.
#    Do not use it for criteria that could plausibly go unrecorded.

# 2. Evidence — list relevant sentence IDs. Return [] if none.

# 3. Label — assign exactly one label.
# </evaluation_steps>

# <label_space>
# Allowed labels:
# - "not applicable"      — criterion assumes a context clearly irrelevant to this patient
# - "not enough information" — note cannot confirm or rule out the criterion, AND omission is plausible
# - "included"            — patient meets this inclusion criterion
# - "not included"        — patient does not meet this inclusion criterion
# </label_space>

# <output_format>
# Return ONLY valid JSON. Format:
# {
#   "criterion_number": ["brief reasoning", [sentence_ids], "label"]
# }
# No markdown, no explanations.
# </output_format>
# """.strip()

#     user_prompt = f"""
# <patient_note>
# Each sentence begins with a sentence_id.
# {patient}
# </patient_note>

# <trial_information>
# {print_trial(trial_info, 'inclusion')}
# </trial_information>

# Return JSON only.
# """.strip()

#     return system_prompt, user_prompt


# def get_exclusion_prompt(trial_info: dict, patient: str) -> tuple[str, str]:

#     system_prompt = """
# <role>
# Clinical trial recruitment assistant.
# </role>

# <task>
# Compare the patient note with the EXCLUSION criteria of a clinical trial.
# Determine eligibility at the criterion level. Evaluate each criterion one-by-one.
# </task>

# <label_definitions>
# These four labels are NOT interchangeable. Read carefully:

# - "excluded"               — The note CONFIRMS the patient meets this exclusion criterion (they ARE disqualified).
# - "not excluded"           — The note contains evidence (direct or strongly implied) that the patient does NOT meet this criterion.
# - "not enough information" — The note neither confirms nor rules out the criterion, AND the criterion describes something a good clinical note might reasonably omit (e.g. a rare comorbidity). Do NOT use this if the condition would almost certainly appear in the note if present.
# - "not applicable"         — The criterion assumes a context clearly irrelevant to this patient (e.g. a pregnancy criterion for a male patient).
# </label_definitions>

# <decision_guide>
# Apply in order:
# 1. Is the criterion applicable? If not → "not applicable"
# 2. Does the note confirm the patient meets the exclusion criterion? → "excluded"
# 3. Does the note confirm (directly or by strong implication) the patient does NOT meet it? → "not excluded"
# 4. Would a thorough note almost certainly mention this condition if present? → "not excluded"
# 5. None of the above → "not enough information"
# </decision_guide>

# <evaluation_steps>
# For each exclusion criterion:
# 1. Reasoning — apply the decision guide step-by-step.
# 2. Evidence — list relevant sentence IDs. Return [] if none.
# 3. Label — assign exactly one label from the label_definitions above.
# </evaluation_steps>

# <output_format>
# Return ONLY valid JSON. Format:
# {
#   "criterion_number": ["brief reasoning", [sentence_ids], "label"]
# }
# No markdown, no explanations.
# </output_format>
# """.strip()

#     user_prompt = f"""
# <patient_note>
# Each sentence begins with a sentence_id.
# {patient}
# </patient_note>

# <trial_information>
# {print_trial(trial_info, 'exclusion')}
# </trial_information>
# Return JSON only.
# """.strip()

#     return system_prompt, user_prompt


# # ---------------------------------------------------------------------------
# # JSON parse with retry
# # ---------------------------------------------------------------------------

# def _parse_with_retry(model: str, system_prompt: str, user_prompt: str, raw: str) -> dict:
#     """Try to parse raw as JSON. On failure, ask the model to self-correct once."""
#     cleaned = raw.strip().strip("`").strip("json").strip()
#     try:
#         return json.loads(cleaned)
#     except json.JSONDecodeError:
#         pass

#     retry_response = client.messages.create(
#         model=model,
#         max_tokens=1024,
#         system=system_prompt,
#         messages=[
#             {"role": "user", "content": user_prompt},
#             {"role": "assistant", "content": raw},
#             {
#                 "role": "user",
#                 "content": (
#                     "Your previous response was not valid JSON. "
#                     "Output ONLY the corrected JSON dict — no markdown, no explanation."
#                 ),
#             },
#         ],
#     )
#     corrected = retry_response.content[0].text.strip().strip("`").strip("json").strip()
#     try:
#         return json.loads(corrected)
#     except json.JSONDecodeError:
#         return {"_parse_error": corrected}


# # ---------------------------------------------------------------------------
# # Main matching function
# # ---------------------------------------------------------------------------

# def trialgpt_matching(trial: dict, patient: str, model: str, normalize: bool = True) -> dict:
#     total_input_tokens = 0
#     total_output_tokens = 0

#     # Step 1: optional term normalization
#     if normalize:
#         patient = normalize_patient_note(patient, model)

#     # Step 2: inclusion
#     inc_system, inc_user = get_inclusion_prompt(trial, patient)
#     inc_response = client.messages.create(
#         model=model,
#         max_tokens=1024,
#         system=inc_system,
#         messages=[{"role": "user", "content": inc_user}],
#     )
#     total_input_tokens += inc_response.usage.input_tokens
#     total_output_tokens += inc_response.usage.output_tokens
#     inc_raw = inc_response.content[0].text.strip()
#     inclusion_results = _parse_with_retry(model, inc_system, inc_user, inc_raw)

#     # Step 3: exclusion — with inclusion context
#     exc_system, exc_user = get_exclusion_prompt(trial, patient)
#     exc_response = client.messages.create(
#         model=model,
#         max_tokens=1024,
#         system=exc_system,
#         messages=[{"role": "user", "content": exc_user}],
#     )
#     total_input_tokens += exc_response.usage.input_tokens
#     total_output_tokens += exc_response.usage.output_tokens
#     exc_raw = exc_response.content[0].text.strip()
#     exclusion_results = _parse_with_retry(model, exc_system, exc_user, exc_raw)

#     return {
#         "results": {
#             "inclusion": inclusion_results,
#             "exclusion": exclusion_results,
#         },
#         "usage": {
#             "input_tokens": total_input_tokens,
#             "output_tokens": total_output_tokens,
#         },
#     }
__author__ = "qiao"

"""
TrialGPT-Matching: Refactored Claude Version
Features: Regex criteria parsing, Evidence-first grounding, and Token tracking.
"""

import json
import re
import os
import anthropic

from utils.anthropic_messages import create_anthropic_message

try:
    from .matching_prompt_policy import MATCHING_POLICY_BLOCK
except ImportError:
    from trialgpt_matching.matching_prompt_policy import MATCHING_POLICY_BLOCK

# Initialize Client
api_key = os.getenv("ANTHROPIC_API_KEY", "")
if not api_key:
    raise ValueError("ANTHROPIC_API_KEY environment variable not set.")

client = anthropic.Anthropic(api_key=api_key)


def parse_criteria(criteria_text):
    """
    Improved parsing using regex to handle nested lists, 
    bullets, and various newline formats common in clinical trial text.
    """
    # Split by double newlines or lines starting with numbers/bullets
    parts = re.split(r'\n\n|\n(?=\d+\.)|\n(?=\s*[\*\-\•])', criteria_text)
    
    clean_criteria = []
    idx = 0
    for p in parts:
        clean = p.strip().strip('*-•').strip()
        # Filter out headers and very short fragments
        if len(clean) < 10 or any(x in clean.lower() for x in ["criteria:", "inclusion", "exclusion"]):
            continue
        clean_criteria.append(f"{idx}. {clean}")
        idx += 1
    
    return "\n".join(clean_criteria)


def print_trial(trial_info: dict, inc_exc: str) -> str:
    """Formats trial metadata and specific criteria type."""
    trial = f"Title: {trial_info['brief_title']}\n"
    trial += f"Target diseases: {', '.join(trial_info['diseases_list'])}\n"
    trial += f"Interventions: {', '.join(trial_info['drugs_list'])}\n"
    trial += f"Summary: {trial_info['brief_summary']}\n"
    
    # Use the improved regex parser
    criteria_source = trial_info.get(f'{inc_exc}_criteria', "")
    trial += f"{inc_exc.capitalize()} criteria:\n{parse_criteria(criteria_source)}\n"

    return trial


def get_matching_prompt(trial_info: dict, inc_exc: str, patient: str) -> tuple[str, str]:
    """
    Constructs the system and user prompts with evidence-first instructions.
    """
    
    system_prompt = (
        "You are an expert Clinical Trial Recruitment Assistant. Your goal is to determine patient eligibility "
        "at the criterion level. \n\n"
        "MEDICAL INFERENCE RULE: If the patient note is silent on a specific medical condition, "
        "assume the patient does NOT have that condition. Do not guess or hallucinate history.\n\n"
        f"{MATCHING_POLICY_BLOCK}\n"
    )

    # Specific Logic Hints to prevent "Exclusion Inversion"
    if inc_exc == "inclusion":
        logic_hint = (
            "INCLUSION LOGIC:\n"
            "- 'included': Patient meets this requirement.\n"
            "- 'not included': Patient does NOT meet this requirement.\n"
            "- 'not applicable': The criterion describes a demographic the patient isn't in.\n"
            "- 'not enough information': Required evidence is missing OR the GLOBAL POLICY forbids inferring "
            "(age from dates, investigator-opinion criteria, unreliable timelines)."
        )
    else:
        logic_hint = (
            "EXCLUSION LOGIC (Read carefully):\n"
            "- 'excluded': The patient HAS the condition listed. They are DISQUALIFIED.\n"
            "- 'not excluded': The patient does NOT have the condition. They remain eligible.\n"
            "- 'not applicable': The criterion does not apply to this patient.\n"
            "- 'not enough information': Cannot verify from the note OR the GLOBAL POLICY forbids substituting "
            "judgment (e.g. investigator-opinion exclusions, age from anonymized dates)."
        )

    system_prompt += f"""
{logic_hint}

For each criterion, output exactly three elements:
1. Brief reasoning (Element 1).
2. Sentence IDs — integer list, or empty list (Element 2).
3. Eligibility label (Element 3).

OUTPUT: Return ONLY a valid JSON object where keys are criterion numbers (strings).
Format: {{ "0": ["reasoning text", [0, 1], "label"], ... }}
Use the same label vocabulary as TrialGPT (included / not included / not applicable / not enough information for inclusion; excluded / not excluded / not applicable / not enough information for exclusion).
"""

    user_prompt = (
        f"PATIENT NOTE:\n{patient}\n\n"
        f"CLINICAL TRIAL:\n{print_trial(trial_info, inc_exc)}\n\n"
        "Provide the JSON response:"
    )

    return system_prompt, user_prompt


def trialgpt_matching(trial: dict, patient: str, model: str):
    """
    Executes matching using Claude, tracking tokens and ensuring clean JSON output.
    """
    results = {}
    total_input_tokens = 0
    total_output_tokens = 0

    for inc_exc in ["inclusion", "exclusion"]:
        system_prompt, user_prompt = get_matching_prompt(trial, inc_exc, patient)

        response = create_anthropic_message(
            client,
            model=model,
            max_tokens=4096, # Increased for long reasoning
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0,
        )

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # Clean the output (Claude is usually clean, but regex ensures it)
        text = response.content[0].text.strip()
        
        # Extract JSON block if Claude adds conversational filler
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                results[inc_exc] = json.loads(json_match.group())
            except Exception as e:
                results[inc_exc] = f"JSON Parse Error: {str(e)} | Raw: {text[:100]}"
        else:
            results[inc_exc] = text

    return {
        "results": results,
        "usage": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
        },
    }