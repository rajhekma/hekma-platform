# __author__ = "qiao"

# """
# Conduct the first stage retrieval by the hybrid retriever 
# """
# import torch
# import numpy as np
# from beir.datasets.data_loader import GenericDataLoader
# import json
# from nltk import word_tokenize
# import os
# from rank_bm25 import BM25Okapi
# import sys
# import tqdm
# from transformers import AutoModel, AutoTokenizer
# import faiss
# # Lazy imports: faiss, numpy, torch, transformers moved to functions

# def get_bm25_corpus_index(corpus):
# 	corpus_path = os.path.join(f"trialgpt_retrieval/bm25_corpus_{corpus}.json")

# 	# if already cached then load, otherwise build
# 	if os.path.exists(corpus_path):
# 		corpus_data = json.load(open(corpus_path))
# 		tokenized_corpus = corpus_data["tokenized_corpus"]
# 		corpus_nctids = corpus_data["corpus_nctids"]

# 	else:
# 		tokenized_corpus = []
# 		corpus_nctids = []

# 		with open(f"dataset/{corpus}/corpus.jsonl", "r") as f:
# 			for line in f.readlines():
# 				entry = json.loads(line)
# 				corpus_nctids.append(entry["_id"])
				
# 				# weighting: 3 * title, 2 * condition, 1 * text
# 				tokens = word_tokenize(entry["title"].lower()) * 3
# 				for disease in entry["metadata"]["diseases_list"]:
# 					tokens += word_tokenize(disease.lower()) * 2
# 				tokens += word_tokenize(entry["text"].lower())

# 				tokenized_corpus.append(tokens)

# 		corpus_data = {
# 			"tokenized_corpus": tokenized_corpus,
# 			"corpus_nctids": corpus_nctids,
# 		}

# 		with open(corpus_path, "w") as f:
# 			json.dump(corpus_data, f, indent=4)
	
# 	bm25 = BM25Okapi(tokenized_corpus)

# 	return bm25, corpus_nctids

			
# def get_medcpt_corpus_index(corpus):
# 	corpus_path = f"trialgpt_retrieval/{corpus}_embeds.npy" 
# 	nctids_path = f"trialgpt_retrieval/{corpus}_nctids.json"

# 	# if already cached then load, otherwise build
# 	if os.path.exists(corpus_path):
# 		embeds = np.load(corpus_path)
# 		corpus_nctids = json.load(open(nctids_path)) 

# 	else:
# 		embeds = []
# 		corpus_nctids = []

# 		# check device
# 		device = "cuda" if torch.cuda.is_available() else "cpu"
# 		model = AutoModel.from_pretrained("ncbi/MedCPT-Article-Encoder").to(device)
# 		tokenizer = AutoTokenizer.from_pretrained("ncbi/MedCPT-Article-Encoder")

# 		with open(f"dataset/{corpus}/corpus.jsonl", "r") as f:
# 			print("Encoding the corpus")
# 			for line in tqdm.tqdm(f.readlines()):
# 				entry = json.loads(line)
# 				corpus_nctids.append(entry["_id"])

# 				title = entry["title"]
# 				text = entry["text"]

# 				with torch.no_grad():
# 					# tokenize the articles
# 					encoded = tokenizer(
# 						[[title, text]], 
# 						truncation=True, 
# 						padding=True, 
# 						return_tensors='pt', 
# 						max_length=512,
# 					).to(device)
					
# 					embed = model(**encoded).last_hidden_state[:, 0, :]

# 					embeds.append(embed[0].cpu().numpy())

# 		embeds = np.array(embeds)

# 		np.save(corpus_path, embeds)
# 		with open(nctids_path, "w") as f:
# 			json.dump(corpus_nctids, f, indent=4)

# 	index = faiss.IndexFlatIP(768)
# 	index.add(embeds)
	
# 	return index, corpus_nctids
	
# def run_retrieval(corpus, q_type, k, bm25_wt, medcpt_wt, output_path, N=2000, 
# 				  queries_path=None, id2queries_path=None, 
# 				  bm25_index=None, bm25_nctids=None,
# 				  medcpt_index=None, medcpt_nctids=None,
# 				  ignore_qrels=False):

# 	# Default paths if not provided
# 	if queries_path is None: queries_path = f"dataset/{corpus}/queries.jsonl"
# 	if id2queries_path is None: id2queries_path = f"/home/mayu/Documents/Code/HEKMA/trailgpt/results_gpt5/retrieval_keywords_gpt-5.2-2025-12-11_sigir.json" #"dataset/{corpus}/id2queries.json"

# 	# loading all types of queries
# 	print("id2queries_path = ", id2queries_path)
# 	id2queries = json.load(open(id2queries_path))

# 	# Load indices if not passed in (standard mode)
# 	if bm25_index is None or bm25_nctids is None:
# 		bm25, bm25_nctids = get_bm25_corpus_index(corpus)
# 	else:
# 		bm25 = bm25_index
	
# 	medcpt, medcpt_nctids = None, None
# 	if medcpt_wt > 0:
# 		import torch
# 		from transformers import AutoTokenizer, AutoModel

# 		if medcpt_index is None or medcpt_nctids is None:
# 			medcpt, medcpt_nctids = get_medcpt_corpus_index(corpus)
# 		else:
# 			medcpt = medcpt_index

# 		# check device
# 		device = "cuda" if torch.cuda.is_available() else "cpu"
# 		print(f"Using device: {device}")

# 		# loading the query encoder for MedCPT
# 		model = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").to(device)
# 		tokenizer = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder")
	
# 	# then conduct the searches, saving top N
# 	qid2nctids = {}
# 	# recalls = [] # Recall calculation for validation only

# 	# Try to load qrels just in case, but don't fail if missing
# 	qrels = {}
# 	if not ignore_qrels:
# 		try:
# 			if os.path.exists(f"dataset/{corpus}/qrels"):
# 				_, _, qrels = GenericDataLoader(data_folder=f"dataset/{corpus}/").load(split="test")
# 		except:
# 			pass

# 	with open(queries_path, "r") as f:
# 		for line in tqdm.tqdm(f.readlines()):
# 			entry = json.loads(line)
# 			query = entry["text"]
# 			qid = entry["_id"]

# 			if not ignore_qrels and len(qrels) > 0 and qid not in qrels:
# 				continue

# 			# truth_sum = sum(qrels[qid].values()) if qid in qrels else 0
			
# 			# get the keyword list
# 			conditions = []
# 			if q_type in ["raw", "human_summary"]:
# 				if qid in id2queries:
# 					conditions = [id2queries[qid][q_type]]
# 			elif "turbo" in q_type:
# 				if qid in id2queries and "conditions" in id2queries[qid][q_type]:
# 					conditions = id2queries[qid][q_type]["conditions"]
# 			elif "Clinician" in q_type:
# 				if qid in id2queries:
# 					conditions = id2queries[qid].get(q_type, [])

# 			# Fallback if structure is simple
# 			if not conditions and qid in id2queries and "conditions" in id2queries[qid]:
# 				conditions = id2queries[qid]["conditions"]

# 			if len(conditions) == 0:
# 				nctid2score = {}
# 			else:
# 				# a list of nctid lists for the bm25 retriever
# 				bm25_condition_top_nctids = []

# 				for condition in conditions:
# 					tokens = word_tokenize(condition.lower())
# 					top_nctids = bm25.get_top_n(tokens, bm25_nctids, n=N)
# 					bm25_condition_top_nctids.append(top_nctids)
				
# 				# doing MedCPT retrieval
# 				medcpt_condition_top_nctids = []
# 				if medcpt_wt > 0:
# 					with torch.no_grad():
# 						encoded = tokenizer(
# 							conditions, 
# 							truncation=True, 
# 							padding=True, 
# 							return_tensors='pt', 
# 							max_length=256,
# 						).to(device)

# 						# encode the queries (use the [CLS] last hidden states as the representations)
# 						embeds = model(**encoded).last_hidden_state[:, 0, :].cpu().numpy()

# 						# search the Faiss index
# 						scores, inds = medcpt.search(embeds, k=N)				

# 					for ind_list in inds:
# 						top_nctids = [medcpt_nctids[ind] for ind in ind_list]
# 						medcpt_condition_top_nctids.append(top_nctids)
# 				else:
# 					# If MedCPT skipped, just pad with empty to match zip (though zip will stop at shortest, so logic below needs adjustment)
# 					# ACTUALLY, the zip below iterates `bm25_condition_top_nctids` AND `medcpt_condition_top_nctids`
# 					# If one is empty, zip yields nothing. 
# 					# We should change the loop logic to handle one or both.
# 					pass

# 				nctid2score = {}
				
# 				# Get number of conditions
# 				num_conditions = len(conditions)

# 				for condition_idx in range(num_conditions):
					
# 					if bm25_wt > 0 and condition_idx < len(bm25_condition_top_nctids):
# 						bm25_top_nctids = bm25_condition_top_nctids[condition_idx]
# 						for rank, nctid in enumerate(bm25_top_nctids):
# 							if nctid not in nctid2score:
# 								nctid2score[nctid] = 0
# 							nctid2score[nctid] += (1 / (rank + k)) * (1 / (condition_idx + 1))
					
# 					if medcpt_wt > 0 and condition_idx < len(medcpt_condition_top_nctids):
# 						medcpt_top_nctids = medcpt_condition_top_nctids[condition_idx]
# 						for rank, nctid in enumerate(medcpt_top_nctids):
# 							if nctid not in nctid2score:
# 								nctid2score[nctid] = 0
# 							nctid2score[nctid] += (1 / (rank + k)) * (1 / (condition_idx + 1))

# 			nctid2score = sorted(nctid2score.items(), key=lambda x: -x[1])
# 			top_nctids = [nctid for nctid, _ in nctid2score[:N]]
# 			qid2nctids[qid] = top_nctids

# 			# actual_sum = sum([qrels[qid].get(nctid, 0) for nctid in top_nctids]) if qid in qrels else 0
# 			# recalls.append(actual_sum / truth_sum) if truth_sum > 0 else 0
	
# 	with open(output_path, "w") as f:
# 		json.dump(qid2nctids, f, indent=4)
# if __name__ == "__main__":
# 	# different corpora, "trec_2021", "trec_2022", "sigir"
# 	corpus = sys.argv[1]

# 	# query type
# 	q_type = sys.argv[2]

# 	# different k for fusion
# 	k = int(sys.argv[3])

# 	# bm25 weight 
# 	bm25_wt = int(sys.argv[4])

# 	# medcpt weight
# 	medcpt_wt = int(sys.argv[5])

# 	output_path = f"results_gpt5/qid2nctids_results_{q_type}_{corpus}_k{k}_bm25wt{bm25_wt}_medcptwt{medcpt_wt}_N2000.json"
	
# 	run_retrieval(corpus, q_type, k, bm25_wt, medcpt_wt, output_path)
__author__ = "qiao"

"""
Conduct the first stage retrieval by the hybrid retriever 
"""

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
from repositories.trialgpt_corpus_repo import (
	fetch_all_trials,
	fetch_trials_by_location,
	fetch_trials_by_location_and_diseases,
)

def get_bm25_corpus_index(corpus):
	corpus_path = os.path.join(f"trialgpt_retrieval/bm25_corpus_{corpus}.json")

	# if already cached then load, otherwise build
	if os.path.exists(corpus_path):
		corpus_data = json.load(open(corpus_path))
		tokenized_corpus = corpus_data["tokenized_corpus"]
		corpus_nctids = corpus_data["corpus_nctids"]

	else:
		tokenized_corpus = []
		corpus_nctids = []

		with open(f"/home/mayu/Documents/Code/HEKMA/trailgpt_default/common_everything/filtered_corpus.jsonl", "r") as f:
			for line in f.readlines():
				entry = json.loads(line)
				corpus_nctids.append(entry["_id"])
				
				# weighting: 3 * title, 2 * condition, 1 * text
				tokens = word_tokenize(entry["title"].lower()) * 3
				for disease in entry["metadata"]["diseases_list"]:
					tokens += word_tokenize(disease.lower()) * 2
				tokens += word_tokenize(entry["text"].lower())

				tokenized_corpus.append(tokens)

		corpus_data = {
			"tokenized_corpus": tokenized_corpus,
			"corpus_nctids": corpus_nctids,
		}

		with open(corpus_path, "w") as f:
			json.dump(corpus_data, f, indent=4)
	
	bm25 = BM25Okapi(tokenized_corpus)

	return bm25, corpus_nctids

			
def get_medcpt_corpus_index(corpus):
	corpus_path = f"trialgpt_retrieval/{corpus}_embeds.npy" 
	nctids_path = f"trialgpt_retrieval/{corpus}_nctids.json"

	# if already cached then load, otherwise build
	if os.path.exists(corpus_path):
		embeds = np.load(corpus_path)
		corpus_nctids = json.load(open(nctids_path)) 

	else:
		embeds = []
		corpus_nctids = []

		model = AutoModel.from_pretrained("ncbi/MedCPT-Article-Encoder").to("cuda")
		tokenizer = AutoTokenizer.from_pretrained("ncbi/MedCPT-Article-Encoder")

		with open(f"/home/mayu/Documents/Code/HEKMA/trailgpt_default/common_everything/filtered_corpus.jsonl", "r") as f:
			print("Encoding the corpus")
			for line in tqdm.tqdm(f.readlines()):
				entry = json.loads(line)
				corpus_nctids.append(entry["_id"])

				title = entry["title"]
				text = entry["text"]

				with torch.no_grad():
					# tokenize the articles
					encoded = tokenizer(
						[[title, text]], 
						truncation=True, 
						padding=True, 
						return_tensors='pt', 
						max_length=512,
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
	

def get_bm25_corpus_index_from_db(region=None, disease=None):
	"""
	DB-backed corpus adapter matching old trailgpt behavior:
	- optional hard filters by region/disease
	- same BM25 token weighting pattern as Model1 retrieval core
	"""
	if region and disease:
		trials = fetch_trials_by_location_and_diseases(region, disease)
	elif region:
		trials = fetch_trials_by_location(region)
	else:
		trials = fetch_all_trials()

	tokenized_corpus = []
	corpus_nctids = []

	for trial in trials:
		nct_id = trial.get("nct_id")
		if not nct_id:
			continue

		title = (trial.get("title") or "").lower()
		text = (trial.get("text") or "").lower()
		diseases = trial.get("diseases") or []

		tokens = word_tokenize(title) * 3
		for d in diseases:
			tokens += word_tokenize(str(d).lower()) * 2
		tokens += word_tokenize(text)

		tokenized_corpus.append(tokens)
		corpus_nctids.append(nct_id)

	if not tokenized_corpus:
		return None, []

	return BM25Okapi(tokenized_corpus), corpus_nctids


def run_retrieval(
	q_type,
	k,
	bm25_wt,
	medcpt_wt,
	queries,
	id2queries,
	N=2000,
	region=None,
	disease=None,
	corpus="sigir",
):
	"""
	Stable retrieval entrypoint for P2T workflow.
	Keeps Model1 fusion logic, but sources corpus from DB tables.
	Returns: {query_id: [ranked_nctid, ...]}
	"""
	bm25, bm25_nctids = get_bm25_corpus_index_from_db(region=region, disease=disease)
	if bm25 is None or not bm25_nctids:
		return {entry["_id"]: [] for entry in queries}

	medcpt = None
	medcpt_nctids = None
	query_model = None
	query_tokenizer = None
	device = "cpu"

	if medcpt_wt > 0:
		medcpt, medcpt_nctids = get_medcpt_corpus_index(corpus)
		device = "cuda" if torch.cuda.is_available() else "cpu"
		query_model = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").to(device)
		query_tokenizer = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder")

	qid2nctids = {}
	for entry in queries:
		qid = entry["_id"]

		conditions = []
		if q_type in ["raw", "human_summary"]:
			if qid in id2queries and q_type in id2queries[qid]:
				conditions = [id2queries[qid][q_type]]
		elif "turbo" in q_type:
			if qid in id2queries and "turbo" in id2queries[qid] and "conditions" in id2queries[qid]["turbo"]:
				conditions = id2queries[qid]["turbo"]["conditions"]
		elif "Clinician" in q_type:
			if qid in id2queries:
				conditions = id2queries[qid].get(q_type, [])

		if not conditions and qid in id2queries and "conditions" in id2queries[qid]:
			conditions = id2queries[qid]["conditions"]

		if len(conditions) == 0:
			qid2nctids[qid] = []
			continue

		bm25_condition_top_nctids = []
		for condition in conditions:
			tokens = word_tokenize(condition.lower())
			top_nctids = bm25.get_top_n(tokens, bm25_nctids, n=N)
			bm25_condition_top_nctids.append(top_nctids)

		medcpt_condition_top_nctids = []
		if medcpt_wt > 0 and medcpt is not None:
			with torch.no_grad():
				encoded = query_tokenizer(
					conditions,
					truncation=True,
					padding=True,
					return_tensors="pt",
					max_length=256,
				).to(device)
				embeds = query_model(**encoded).last_hidden_state[:, 0, :].cpu().numpy()
				_, inds = medcpt.search(embeds, k=N)

			for ind_list in inds:
				top_nctids = [medcpt_nctids[ind] for ind in ind_list]
				medcpt_condition_top_nctids.append(top_nctids)

		nctid2score = {}
		num_conditions = len(conditions)
		for condition_idx in range(num_conditions):
			if bm25_wt > 0 and condition_idx < len(bm25_condition_top_nctids):
				for rank, nctid in enumerate(bm25_condition_top_nctids[condition_idx]):
					nctid2score[nctid] = nctid2score.get(nctid, 0) + (1 / (rank + k)) * (1 / (condition_idx + 1))

			if medcpt_wt > 0 and condition_idx < len(medcpt_condition_top_nctids):
				for rank, nctid in enumerate(medcpt_condition_top_nctids[condition_idx]):
					nctid2score[nctid] = nctid2score.get(nctid, 0) + (1 / (rank + k)) * (1 / (condition_idx + 1))

		nctid2score = sorted(nctid2score.items(), key=lambda x: -x[1])
		qid2nctids[qid] = [nctid for nctid, _ in nctid2score[:N]]

	return qid2nctids

if __name__ == "__main__":
	# different corpora, "trec_2021", "trec_2022", "sigir"
	corpus = sys.argv[1]

	# query type
	q_type = sys.argv[2]

	# different k for fusion
	k = int(sys.argv[3])

	# bm25 weight 
	bm25_wt = int(sys.argv[4])

	# medcpt weight
	medcpt_wt = int(sys.argv[5])

	# how many to rank
	N = 20

	# loading the qrels
	_, _, qrels = GenericDataLoader(data_folder=f"dataset/{corpus}/").load(split="test")
	# print(qrels)
	# import sys
	# sys.exit(0)

	# loading all types of queries
	id2queries_path = f"/home/mayu/Documents/Code/HEKMA/trailgpt_default/common_everything/trial_steps/retrieval_keywords_gpt-5.2-2025-12-11_sigir.json"
	id2queries = json.load(open(id2queries_path)) #f"dataset/{corpus}/id2queries.json"))
	

	# loading the indices
	bm25, bm25_nctids = get_bm25_corpus_index(corpus)
	medcpt, medcpt_nctids = get_medcpt_corpus_index(corpus)

	# loading the query encoder for MedCPT
	model = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").to("cpu")
	tokenizer = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder")
	
	# then conduct the searches, saving top 1k
	output_path = f"common_everything/qid2nctids_results_{q_type}_{corpus}_k{k}_bm25wt{bm25_wt}_medcptwt{medcpt_wt}_N{N}.json"
	
	qid2nctids = {}
	recalls = []

	with open(f"/home/mayu/Documents/Code/HEKMA/trailgpt_default/common_everything/queries_filtered.jsonl", "r") as f:#"dataset/{corpus}/queries.jsonl", "r") as f:
		for line in tqdm.tqdm(f.readlines()):
			entry = json.loads(line)
			query = entry["text"]
			qid = entry["_id"]

			if qid not in qrels:
				continue

			truth_sum = sum(qrels[qid].values())
			
			# get the keyword list
			if q_type in ["raw", "human_summary"]:
				conditions = [id2queries[qid][q_type]]
			elif "turbo" in q_type:
				conditions = id2queries[qid][q_type]["conditions"]
			elif "Clinician" in q_type:
				conditions = id2queries[qid].get(q_type, [])
			else:
				conditions = id2queries[qid]["conditions"]
			
			#print(len(conditions))
			#import sys
			#sys.exit(0)
			if len(conditions) == 0:
				nctid2score = {}
			else:
				# a list of nctid lists for the bm25 retriever
				bm25_condition_top_nctids = []

				for condition in conditions:
					tokens = word_tokenize(condition.lower())
					top_nctids = bm25.get_top_n(tokens, bm25_nctids, n=N)
					bm25_condition_top_nctids.append(top_nctids)
				
				# doing MedCPT retrieval
				with torch.no_grad():
					encoded = tokenizer(
						conditions, 
						truncation=True, 
						padding=True, 
						return_tensors='pt', 
						max_length=256,
					).to("cpu")

					# encode the queries (use the [CLS] last hidden states as the representations)
					embeds = model(**encoded).last_hidden_state[:, 0, :].cpu().numpy()

					# search the Faiss index
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
	overall_recall = sum(recalls) / len(recalls)
	print("recall = ", recalls)
	print("recall = ", overall_recall)
	with open(output_path, "w") as f:
		json.dump(qid2nctids, f, indent=4)

	# added in trial metadata and patient metadata extraction
	trial_info_path = "dataset/trial_info.json"
	queries_path = f"/home/mayu/Documents/Code/HEKMA/trailgpt_default/common_everything/queries_filtered.jsonl"#"dataset/{corpus}/queries.jsonl"

	with open(trial_info_path, "r") as f:
		trial_info = json.load(f)

	patients = {}
	with open(queries_path, "r") as f:
		for line in f:
			obj = json.loads(line.strip())
			patients[obj["_id"]] = obj["text"]

	transformed_output = []

	# iterate over each patient ID and their retrieved trial NCTID list
	for patient_id, nctid_list in qid2nctids.items():
		patient_note = patients.get(patient_id, "")
		# create a dictionary for each patient
		patient_entry = {
			"patient_id": patient_id,
			"patient": patient_note,
			"0": [],
			"1": [],
			"2": []
		}

		# go through each retrieved trial NCTID and add in metadata
		for nctid in nctid_list:
			trial_metadata = trial_info.get(nctid)
			if trial_metadata:
				trial_metadata["NCTID"] = nctid
				# added it to label 0 but can change depending on preference
				patient_entry["0"].append(trial_metadata)

		transformed_output.append(patient_entry)

	# save the output path to the same location as retrieval output
	transformed_output_path = output_path
	with open(transformed_output_path, "w") as f:
		json.dump(transformed_output, f, indent=4)


