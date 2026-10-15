__author__ = "qiao"

"""
TrialGPT-Ranking main functions.
"""

import json
from nltk.tokenize import sent_tokenize
import time
import os

from openai import OpenAI, AzureOpenAI

api_key = os.getenv("OPENAI_API_KEY", "")
if api_key.startswith("sk-"):
    client = OpenAI(api_key=api_key)
else:
    client = AzureOpenAI(
        api_version="2023-09-01-preview",
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT") or os.getenv("OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY") or api_key,
    )

def convert_criteria_pred_to_string(
		prediction: dict,
		trial_info: dict,
) -> str:
	"""Given the TrialGPT prediction, output the linear string of the criteria."""
	output = ""

	for inc_exc in ["inclusion", "exclusion"]:

		from utils.trial_criteria_util import criteria_to_list

		idx2criterion = {}
		criteria = criteria_to_list(trial_info.get(inc_exc + "_criteria"))
		for idx, criterion in enumerate(criteria, start=1):
			idx2criterion[str(idx)] = criterion

		from utils.matching_result_util import parse_criterion_result

		for idx, info in enumerate(prediction[inc_exc].items()):
			criterion_idx, preds = info

			if criterion_idx not in idx2criterion:
				continue

			criterion = idx2criterion[criterion_idx]

			parsed = parse_criterion_result(preds)
			if not parsed:
				continue

			output += f"{inc_exc} criterion {idx}: {criterion}\n"
			output += f"\tPatient relevance: {parsed[0]}\n"
			if len(parsed[1]) > 0:
				output += f"\tEvident sentences: {parsed[1]}\n"
			output += f"\tPatient eligibility: {parsed[2]}\n"
	
	return output


def convert_pred_to_prompt(
		patient: str,
		pred: dict,
		trial_info: dict,
) -> str:
	"""Convert the prediction to a prompt string."""
	# get the trial string
	def _join_terms(items) -> str:
		if not items:
			return ""
		parts = []
		for item in items:
			if isinstance(item, str):
				parts.append(item)
			elif isinstance(item, dict):
				parts.append(
					str(item.get("name") or item.get("term") or item.get("title") or item)
				)
			else:
				parts.append(str(item))
		return ", ".join(parts)

	trial = f"Title: {trial_info['brief_title']}\n"
	trial += f"Target conditions: {_join_terms(trial_info.get('diseases_list') or [])}\n"
	trial += f"Summary: {trial_info['brief_summary']}"

	# then get the prediction strings
	pred = convert_criteria_pred_to_string(pred, trial_info)

	# construct the prompt
	prompt = "You are a helpful assistant for clinical trial recruitment. You will be given a patient note, a clinical trial, and the patient eligibility predictions for each criterion.\n"
	prompt += "Your task is to output two scores, a relevance score (R) and an eligibility score (E), between the patient and the clinical trial.\n"
	prompt += "First explain the consideration for determining patient-trial relevance. Predict the relevance score R (0~100), which represents the overall relevance between the patient and the clinical trial. R=0 denotes the patient is totally irrelevant to the clinical trial, and R=100 denotes the patient is exactly relevant to the clinical trial.\n"
	prompt += "Then explain the consideration for determining patient-trial eligibility. Predict the eligibility score E (-R~R), which represents the patient's eligibility to the clinical trial. Note that -R <= E <= R (the absolute value of eligibility cannot be higher than the relevance), where E=-R denotes that the patient is ineligible (not included by any inclusion criteria, or excluded by all exclusion criteria), E=R denotes that the patient is eligible (included by all inclusion criteria, and not excluded by any exclusion criteria), E=0 denotes the patient is neutral (i.e., no relevant information for all inclusion and exclusion criteria).\n"
	prompt += 'Please output a JSON dict formatted as Dict{"relevance_explanation": Str, "relevance_score_R": Float, "eligibility_explanation": Str, "eligibility_score_E": Float}.'


	user_prompt = "Here is the patient note:\n"
	user_prompt += patient + "\n\n"
	user_prompt += "Here is the clinical trial description:\n"
	user_prompt += trial + "\n\n"
	user_prompt += "Here are the criterion-level eligibility prediction:\n"
	user_prompt += pred + "\n\n"
	user_prompt += "Plain JSON output:"

	return prompt, user_prompt


def trialgpt_aggregation(patient: str, trial_results: dict, trial_info: dict, model: str):
	system_prompt, user_prompt = convert_pred_to_prompt(
			patient,
			trial_results,
			trial_info
	)   

	messages = [
		{"role": "system", "content": system_prompt},
		{"role": "user", "content": user_prompt}
	]

	response = client.chat.completions.create(
		model=model,
		messages=messages,
		temperature=0,
	)
	result = response.choices[0].message.content.strip()
	result = result.strip("`").strip("json")
	result = json.loads(result)

	return result
