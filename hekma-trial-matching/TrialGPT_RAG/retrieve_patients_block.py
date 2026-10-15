import json
import uuid
import time
import argparse
from tqdm import tqdm
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams, SparseIndexParams,
    PointStruct, Prefetch, FusionQuery, Fusion,
)
from config import qdrant, PATIENT_COLLECTION, DENSE_DIM, DENSE_VEC, SPARSE_VEC, TRIAL_COLLECTION

_UUID_NS = uuid.NAMESPACE_DNS

def stable_id(text: str) -> str:
    return str(uuid.uuid5(_UUID_NS, text))

from utils import embed, bm25_sparse_vector, extract_min_age, extract_max_age
from utils import extract_sex, raw_profile_to_text, ensure_collection
from ingest_trials import build_trial_text, build_trial_keywords, ingest_corpus


# ── Patient lookup ────────────────────────────────────────────────────────────

def fetch_expanded(pid: str) -> str:
    point_id = stable_id(pid)
    results  = qdrant.retrieve(
        collection_name=PATIENT_COLLECTION,
        ids=[point_id],
        with_payload=True,
    )
    if not results:
        raise ValueError(f"Patient '{pid}' not found in '{PATIENT_COLLECTION}'")
    return results[0].payload.get("_expanded", "")


# ── Retrieval ──────────────────────────────────────────────────────────────────

def retrieve_trials_for_patient(raw_profile: dict, expanded: str, top_k: int, threshold: float) -> list[dict]:
    base_text        = raw_profile_to_text(raw_profile)
    dense_query      = embed(base_text)
    sparse_base      = bm25_sparse_vector(base_text)
    sparse_expanded  = bm25_sparse_vector(expanded)

    results = qdrant.query_points(
        collection_name=TRIAL_COLLECTION,
        prefetch=[
            Prefetch(query=dense_query,     using=DENSE_VEC,  limit=150),
            Prefetch(query=sparse_base,     using=SPARSE_VEC, limit=150),
            Prefetch(query=sparse_expanded, using=SPARSE_VEC, limit=150),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
        with_payload=True,
    )

    return [
        {
            "nct_id": pt.payload.get("nct_id"),
            "title":  pt.payload.get("title"),
            "score":  pt.score,
        }
        for pt in results.points
        if pt.score >= threshold
    ]


# ── Main ───────────────────────────────────────────────────────────────────────

def run(corpus_path, patients_path, output_path, top_k, threshold, recreate, no_ingest):
    if not no_ingest:
        ingest_corpus(corpus_path, recreate=recreate)

    with open(patients_path, encoding="utf-8") as f:
        patients = json.load(f)

    output = {}
    for pid, raw_profile in tqdm(patients.items(), desc="Retrieving trials", unit="patient"):
        expanded = fetch_expanded(pid)
        trials   = retrieve_trials_for_patient(raw_profile, expanded, top_k, threshold)
        output[pid] = {
            "raw_profile": raw_profile,
            "trials": trials,
        }
        tqdm.write(f"  {pid} | {len(trials)} trials retrieved")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4)

    print(f"\n[done] Saved results for {len(output)} patients to '{output_path}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest filtered corpus and retrieve trials per patient")
    parser.add_argument("-c",  "--corpus",    required=True,                       help="Path to filtered_corpus.jsonl")
    parser.add_argument("-p",  "--patients",  required=True,                       help="Path to patients JSON file")
    parser.add_argument("-o",  "--output",    default="patient_trials.json",       help="Output JSON file path")
    parser.add_argument("--top-k",            type=int,   default=10,              help="Max trials to retrieve per patient")
    parser.add_argument("-t",  "--threshold", type=float, default=0.1,             help="Minimum RRF score threshold")
    parser.add_argument("--recreate",         action="store_true",                 help="Drop and recreate trial collection before ingestion")
    parser.add_argument("--no-ingest",        action="store_true",                 help="Skip ingestion, query only")
    args = parser.parse_args()

    run(args.corpus, args.patients, args.output, args.top_k, args.threshold, args.recreate, args.no_ingest)