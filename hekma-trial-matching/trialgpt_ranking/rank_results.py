__author__ = "qiao"

"""
Rank the trials given the matching and aggregation results
"""

import json
import sys

eps = 1e-9

def get_matching_score(matching):
	from utils.matching_result_util import get_label, normalize_matching_results

	matching = normalize_matching_results(matching)

	# count only the valid ones
	included = 0
	not_inc = 0
	na_inc = 0
	no_info_inc = 0

	excluded = 0
	not_exc = 0
	na_exc = 0
	no_info_exc = 0
	
	# first count inclusions
	try:
		for criteria, info in matching["inclusion"].items():
			label = get_label(info)
			if label is None:
				continue

			if label == "included":
				included += 1	
			elif label == "not included":
				not_inc += 1
			elif label == "not applicable":
				na_inc += 1
			elif label == "not enough information":
				no_info_inc += 1
		
		# then count exclusions
		for criteria, info in matching["exclusion"].items():
			label = get_label(info)
			if label is None:
				continue

			if label == "excluded":
				excluded += 1	
			elif label == "not excluded":
				not_exc += 1
			elif label == "not applicable":
				na_exc += 1
			elif label == "not enough information":
				no_info_exc += 1
	except Exception as e:
		print(e)
	# get the matching score
	score = 0
	
	score += included / (included + not_inc + no_info_inc + eps)
	
	if not_inc > 0:
		score -= 1
	
	if excluded > 0:
		score -= 1
	
	return score 


def get_agg_score(assessment):
	try:
		rel_score = float(assessment["relevance_score_R"])
		eli_score = float(assessment["eligibility_score_E"])
	except:
		rel_score = 0
		eli_score = 0
	
	score = (rel_score + eli_score) / 100

	return score 


if __name__ == "__main__":
	# args are the results paths
	matching_results_path = sys.argv[1]
	agg_results_path = sys.argv[2]

	# loading the results
	matching_results = json.load(open(matching_results_path))
	agg_results = json.load(open(agg_results_path))
	
	# loop over the patients
	import json

	output_path = "/home/mayu/Documents/Code/HEKMA/trailgpt_default/bm_15032026/patient_trial_rankings.json"

	all_results = {}

	for patient_id, label2trial2results in matching_results.items():

		trial2score = {}

		for _, trial2results in label2trial2results.items():
			for trial_id, results in trial2results.items():

				matching_score = get_matching_score(results)

				if patient_id not in agg_results or trial_id not in agg_results[patient_id]:
					print(f"Patient {patient_id} Trial {trial_id} not in the aggregation results.")
					agg_score = 0
				else:
					agg_score = get_agg_score(agg_results[patient_id][trial_id])

				trial_score = matching_score + agg_score
				trial2score[trial_id] = trial_score

		sorted_trial2score = sorted(trial2score.items(), key=lambda x: -x[1])

		print()
		print(f"Patient ID: {patient_id}")
		print("Clinical trial ranking:")

		patient_results = []

		for trial, score in sorted_trial2score:
			print(trial, score)

			patient_results.append({
				"trial_id": trial,
				"score": score
			})

		print("===")
		print()

		all_results[patient_id] = patient_results


	with open(output_path, "w", encoding="utf-8") as f:
		json.dump(all_results, f, indent=4, ensure_ascii=False)
	'''
	for patient_id, label2trial2results in matching_results.items():

		trial2score = {}

		for _, trial2results in label2trial2results.items():
			for trial_id, results in trial2results.items():

				matching_score = get_matching_score(results)
				
				if patient_id not in agg_results or trial_id not in agg_results[patient_id]:
					print(f"Patient {patient_id} Trial {trial_id} not in the aggregation results.")
					agg_score = 0
				else:
					agg_score = get_agg_score(agg_results[patient_id][trial_id])

				trial_score = matching_score + agg_score
				
				trial2score[trial_id] = trial_score

		sorted_trial2score = sorted(trial2score.items(), key=lambda x: -x[1])
		
		print()
		print(f"Patient ID: {patient_id}")
		print("Clinical trial ranking:")
		
		for trial, score in sorted_trial2score:
			print(trial, score)

		print("===")
		print()
	'''
