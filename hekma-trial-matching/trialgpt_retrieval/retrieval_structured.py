from beir.datasets.data_loader import GenericDataLoader
import faiss
import json
from nltk import word_tokenize
import numpy as np
import os
from rank_bm25 import BM25Okapi
import sys
import tqdm
import torch
from transformers import AutoTokenizer, AutoModel

def get_bm25_corpus_index(corpus):
	corpus_path = os.path.join(f"trialgpt_retrieval/bm25_corpus_{corpus}.json")

	if os.path.exists(corpus_path):
		corpus_data = json.load(open(corpus_path))
		tokenized_corpus = corpus_data["tokenized_corpus"]
		corpus_nctids = corpus_data["corpus_nctids"]
	else:
		tokenized_corpus = []
		corpus_nctids = []

		with open(f"dataset/{corpus}/corpus.jsonl", "r") as f:
			for line in f.readlines():
				entry = json.loads(line)
				corpus_nctids.append(entry["_id"])
				tokens = word_tokenize(entry["title"].lower()) * 3
				for disease in entry["metadata"]["diseases_list"]:
					tokens += word_tokenize(disease.lower()) * 2
				tokens += word_tokenize(entry["text"].lower())
				tokenized_corpus.append(tokens)

		corpus_data = {"tokenized_corpus": tokenized_corpus, "corpus_nctids": corpus_nctids}
		with open(corpus_path, "w") as f:
			json.dump(corpus_data, f, indent=4)

	bm25 = BM25Okapi(tokenized_corpus)
	return bm25, corpus_nctids


def get_medcpt_corpus_index(corpus):
	corpus_path = f"trialgpt_retrieval/{corpus}_embeds.npy"
	nctids_path = f"trialgpt_retrieval/{corpus}_nctids.json"

	if os.path.exists(corpus_path):
		embeds = np.load(corpus_path)
		corpus_nctids = json.load(open(nctids_path))
	else:
		embeds = []
		corpus_nctids = []

		model = AutoModel.from_pretrained("ncbi/MedCPT-Article-Encoder").to("cuda")
		tokenizer = AutoTokenizer.from_pretrained("ncbi/MedCPT-Article-Encoder")

		with open(f"dataset/{corpus}/corpus.jsonl", "r") as f:
			print("Encoding the corpus")
			for line in tqdm.tqdm(f.readlines()):
				entry = json.loads(line)
				corpus_nctids.append(entry["_id"])
				title = entry["title"]
				text = entry["text"]

				with torch.no_grad():
					encoded = tokenizer(
						[[title, text]],
						truncation=True, padding=True,
						return_tensors='pt', max_length=512,
					).to("cuda")
					embed = model(**encoded).last_hidden_state[:, 0, :]
					embeds.append(embed[0].cpu().numpy())

		embeds = np.array(embeds)
		np.save(corpus_path, embeds)
		with open(nctids_path, "w") as f:
			json.dump(corpus_nctids, f, indent=4)

	index = faiss.IndexFlatIP(768)
	index.add(embeds)
	return index, corpus_nctids


def get_conditions_from_profile(patient_data):
	"""Build conditions list from new structured patient_profile format."""
	profile = patient_data.get("patient_profile", {})
	conditions = []
	conditions += profile.get("conditions", [])
	conditions += profile.get("symptoms", [])
	conditions += profile.get("risk_factors", [])
	conditions += profile.get("medical_history", [])
	# Deduplicate while preserving order
	seen = set()
	unique_conditions = []
	for c in conditions:
		if c not in seen:
			seen.add(c)
			unique_conditions.append(c)
	return unique_conditions


import argparse

if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--corpus", required=True, help="e.g. trec_2021, trec_2022, sigir")
	parser.add_argument("--q_type", default="gpt4")
	parser.add_argument("--k", type=int, default=20)
	parser.add_argument("--bm25_wt", type=int, default=1)
	parser.add_argument("--medcpt_wt", type=int, default=1)
	args = parser.parse_args()

	corpus = args.corpus
	q_type = args.q_type
	k = args.k
	bm25_wt = args.bm25_wt
	medcpt_wt = args.medcpt_wt
	N = 20

	_, _, qrels = GenericDataLoader(data_folder=f"dataset/{corpus}/").load(split="test")

	id2queries_path = "/home/mayu/Documents/Code/HEKMA/trailgpt/trialgpt_retrieval/structured_patients.json" #f"results_claude_xml/retrieval_keywords_claude-sonnet-4-6_{corpus}.json"
	id2queries = json.load(open(id2queries_path))

	bm25, bm25_nctids = get_bm25_corpus_index(corpus)
	medcpt, medcpt_nctids = get_medcpt_corpus_index(corpus)

	model = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").to("cpu")
	tokenizer = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder")

	output_path = f"results_claude_xml/structured_qid2nctids_results_{q_type}_{corpus}_k{k}_bm25wt{bm25_wt}_medcptwt{medcpt_wt}_N{N}.json"

	qid2nctids = {}
	recalls = []

	for qid, patient_data in tqdm.tqdm(id2queries.items()):
		if qid not in qrels:
			continue

		truth_sum = sum(qrels[qid].values())
		conditions = get_conditions_from_profile(patient_data)

		if len(conditions) == 0:
			nctid2score = {}
		else:
			bm25_condition_top_nctids = []
			for condition in conditions:
				tokens = word_tokenize(condition.lower())
				top_nctids = bm25.get_top_n(tokens, bm25_nctids, n=N)
				bm25_condition_top_nctids.append(top_nctids)

			with torch.no_grad():
				encoded = tokenizer(
					conditions,
					truncation=True, padding=True,
					return_tensors='pt', max_length=256,
				).to("cpu")
				embeds = model(**encoded).last_hidden_state[:, 0, :].cpu().numpy()
				scores, inds = medcpt.search(embeds, k=N)

			medcpt_condition_top_nctids = []
			for ind_list in inds:
				top_nctids = [medcpt_nctids[ind] for ind in ind_list]
				medcpt_condition_top_nctids.append(top_nctids)

			nctid2score = {}
			for condition_idx, (bm25_top_nctids, medcpt_top_nctids) in enumerate(zip(bm25_condition_top_nctids, medcpt_condition_top_nctids)):
				if bm25_wt > 0:
					for rank, nctid in enumerate(bm25_top_nctids):
						if nctid not in nctid2score:
							nctid2score[nctid] = 0
						nctid2score[nctid] += (1 / (rank + k)) * (1 / (condition_idx + 1))

				if medcpt_wt > 0:
					for rank, nctid in enumerate(medcpt_top_nctids):
						if nctid not in nctid2score:
							nctid2score[nctid] = 0
						nctid2score[nctid] += (1 / (rank + k)) * (1 / (condition_idx + 1))

		nctid2score = sorted(nctid2score.items(), key=lambda x: -x[1])
		top_nctids = [nctid for nctid, _ in nctid2score[:N]]
		qid2nctids[qid] = top_nctids

		actual_sum = sum([qrels[qid].get(nctid, 0) for nctid in top_nctids])
		recalls.append(actual_sum / truth_sum)

	with open(output_path, "w") as f:
		json.dump(qid2nctids, f, indent=4)

	trial_info_path = "dataset/trial_info.json"
	with open(trial_info_path, "r") as f:
		trial_info = json.load(f)

	transformed_output = []

	for patient_id, nctid_list in qid2nctids.items():
		patient_data = id2queries.get(patient_id, {})
		patient_note = patient_data.get("patient_note", "")

		patient_entry = {
			"patient_id": patient_id,
			"patient": patient_note,
			"0": [],
			"1": [],
			"2": []
		}

		for nctid in nctid_list:
			trial_metadata = trial_info.get(nctid)
			if trial_metadata:
				trial_metadata["NCTID"] = nctid
				patient_entry["0"].append(trial_metadata)

		transformed_output.append(patient_entry)

	with open(output_path, "w") as f:
		json.dump(transformed_output, f, indent=4)