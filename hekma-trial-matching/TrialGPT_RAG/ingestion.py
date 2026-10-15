import json
import time
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams, SparseIndexParams, PointStruct,
)
from config import qdrant, COLLECTION, DENSE_DIM, DENSE_VEC, SPARSE_VEC
from utils import embed, bm25_sparse_vector, extract_min_age, extract_max_age, extract_sex


def ensure_collection(recreate: bool = False):
    existing = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION in existing:
        if not recreate:
            return
        qdrant.delete_collection(COLLECTION)
        print(f"[init] Dropped existing collection '{COLLECTION}'.")
    qdrant.create_collection(
        collection_name=COLLECTION,
        vectors_config={
            DENSE_VEC: VectorParams(size=DENSE_DIM, distance=Distance.COSINE),
        },
        sparse_vectors_config={
            SPARSE_VEC: SparseVectorParams(index=SparseIndexParams(on_disk=False)),
        },
    )
    print(f"[init] Collection '{COLLECTION}' created.")


def build_dense_text(trial: dict) -> str:
    m = trial.get("metadata", {})
    parts = [
        trial.get("title", ""),
        " ".join(m.get("diseases_list", [])),
        m.get("brief_summary", ""),
        m.get("inclusion_criteria", ""),#[:500],
        m.get("exclusion_criteria", ""),#[:300],
        " ".join(m.get("drugs_list", [])),
    ]
    return " ".join(p for p in parts if p)


def build_bm25_text(trial: dict) -> str:
    m = trial.get("metadata", {})
    parts = [
        trial.get("title", ""),
        " ".join(m.get("diseases_list", [])),
        m.get("brief_summary", ""),
        m.get("inclusion_criteria", ""),
        m.get("exclusion_criteria", ""),
        " ".join(m.get("drugs_list", [])),
    ]
    return " ".join(p for p in parts if p)


def ingest_corpus(jsonl_path: str, batch_size: int = 50, recreate: bool = False):
    ensure_collection(recreate=recreate)
    points = []

    with open(jsonl_path) as f:
        for line in f:
            trial = json.loads(line)
            m = trial.get("metadata", {})

            dense_text = build_dense_text(trial)
            bm25_text  = build_bm25_text(trial)

            payload = {
                "nct_id":             trial["_id"],
                "title":              trial.get("title", ""),
                "min_age":            extract_min_age(m.get("inclusion_criteria", "")),
                "max_age":            extract_max_age(m.get("inclusion_criteria", "")),
                "sex":                extract_sex(m.get("inclusion_criteria", "")),
                "dense_text":         dense_text,
                "bm25_text":          bm25_text,
                "inclusion_criteria": m.get("inclusion_criteria", ""),
                "exclusion_criteria": m.get("exclusion_criteria", ""),
            }

            points.append(
                PointStruct(
                    id=abs(hash(trial["_id"])) % (2**53),
                    vector={
                        DENSE_VEC:  embed(dense_text),
                        SPARSE_VEC: bm25_sparse_vector(bm25_text),
                    },
                    payload=payload,
                )
            )

            if len(points) >= batch_size:
                qdrant.upsert(collection_name=COLLECTION, points=points)
                print(f"[ingest] Upserted {len(points)} trials…")
                points = []
                time.sleep(0.2)

    if points:
        qdrant.upsert(collection_name=COLLECTION, points=points)
        print(f"[ingest] Upserted final {len(points)} trials.")

    print("[ingest] Done.")
