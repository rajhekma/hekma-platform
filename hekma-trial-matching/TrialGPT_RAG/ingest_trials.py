import json
import uuid
import time
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams, SparseIndexParams, PointStruct,
)
from config import qdrant, COLLECTION, DENSE_DIM, DENSE_VEC, SPARSE_VEC

_UUID_NS = uuid.NAMESPACE_DNS

def stable_id(text: str) -> str:
    return str(uuid.uuid5(_UUID_NS, text))

from utils import embed, bm25_sparse_vector, extract_min_age, extract_max_age, extract_sex, ensure_collection


def _criteria_to_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        lines = []
        for key, text in value.items():
            if text:
                lines.append(f"{key}. {text}")
        return "\n".join(lines)
    return ""


def normalize_trial_record(raw: dict) -> dict:
    """Support both BEIR-style corpus rows and dataset/trials.jsonl rows."""
    if raw.get("_id") and isinstance(raw.get("metadata"), dict):
        return raw

    nct_id = raw.get("nct_id") or raw.get("_id") or ""
    drugs = raw.get("drugs") or []
    diseases = raw.get("diseases") or []
    if not isinstance(drugs, list):
        drugs = [str(drugs)]
    if not isinstance(diseases, list):
        diseases = [str(diseases)]

    inclusion = _criteria_to_text(raw.get("inclusion_criteria", ""))
    exclusion = _criteria_to_text(raw.get("exclusion_criteria", ""))

    return {
        "_id": nct_id,
        "title": raw.get("brief_title") or raw.get("title", ""),
        "text": raw.get("brief_summary", ""),
        "metadata": {
            "brief_summary": raw.get("brief_summary", ""),
            "inclusion_criteria": inclusion,
            "exclusion_criteria": exclusion,
            "drugs_list": drugs,
            "diseases_list": diseases,
            "phase": raw.get("phase", ""),
        },
    }


def parse_criteria(text: str) -> str:
    lines = [l.strip() for l in text.split("\n\n") if l.strip()]
    if len(lines) <= 1:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
    lines = [l for l in lines if not l.lower().startswith("inclusion")
             and not l.lower().startswith("exclusion") and l != ":"]
    return "\n".join(f"{i}. {c}" for i, c in enumerate(lines))


def build_trial_text(trial: dict) -> str:
    """Structured labeled text for dense embedding."""
    m       = trial.get("metadata", {})
    summary = m.get("brief_summary", "").strip() or trial.get("text", "").strip()

    drugs_list = m.get("drugs_list", [])
    drugs_str  = ", ".join(drugs_list) if drugs_list else m.get("drugs", "").strip()

    inc = parse_criteria(m.get("inclusion_criteria", ""))
    exc = parse_criteria(m.get("exclusion_criteria", ""))

    parts = [f"Title: {trial.get('title', '')}"]
    if m.get("diseases_list"):
        parts.append(f"Target diseases: {', '.join(m['diseases_list'])}")
    if summary:
        parts.append(f"Summary: {summary}")
    if drugs_str:
        parts.append(f"Interventions: {drugs_str}")
    if inc:
        parts.append(f"Inclusion criteria:\n{inc}")
    if exc:
        parts.append(f"Exclusion criteria:\n{exc}")

    return "\n".join(parts)


def build_trial_keywords(trial: dict) -> str:
    """Lean keyword string for BM25 sparse retrieval."""
    m = trial.get("metadata", {})

    drugs_list = m.get("drugs_list", [])
    drugs_str  = " ".join(drugs_list) if drugs_list else m.get("drugs", "").strip()

    inc_clean = parse_criteria(m.get("inclusion_criteria", ""))
    exc_clean = parse_criteria(m.get("exclusion_criteria", ""))

    tokens = [
        trial.get("title", ""),
        " ".join(m.get("diseases_list", [])),
        drugs_str,
        inc_clean,
        exc_clean,
    ]
    return " ".join(t for t in tokens if t)


def _upsert_points(points: list) -> None:
    for attempt in range(4):
        try:
            qdrant.upsert(collection_name=COLLECTION, points=points)
            return
        except Exception as exc:
            if attempt >= 3:
                raise
            wait = 2 ** attempt
            print(f"[ingest] Upsert retry {attempt + 1}/3 after error: {exc}")
            time.sleep(wait)


def ingest_corpus(jsonl_path: str, batch_size: int = 50, recreate: bool = False):
    ensure_collection(recreate=recreate)
    points = []

    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            trial = normalize_trial_record(json.loads(line))
            m = trial.get("metadata", {})

            dense_text   = build_trial_text(trial)
            keyword_text = build_trial_keywords(trial)

            payload = {
                "nct_id":             trial["_id"],
                "title":              trial.get("title", ""),
                "min_age":            extract_min_age(m.get("inclusion_criteria", "")),
                "max_age":            extract_max_age(m.get("inclusion_criteria", "")),
                "sex":                extract_sex(m.get("inclusion_criteria", "")),
                "dense_text":         dense_text,
                "bm25_text":          keyword_text,
                "inclusion_criteria": m.get("inclusion_criteria", ""),
                "exclusion_criteria": m.get("exclusion_criteria", ""),
            }

            points.append(
                PointStruct(
                    id=abs(hash(trial["_id"])) % (2**53),
                    vector={
                        DENSE_VEC:  embed(dense_text),
                        SPARSE_VEC: bm25_sparse_vector(keyword_text),
                    },
                    payload=payload,
                )
            )

            if len(points) >= batch_size:
                _upsert_points(points)
                print(f"[ingest] Upserted {len(points)} trials…")
                points = []
                time.sleep(0.2)

    if points:
        _upsert_points(points)
        print(f"[ingest] Upserted final {len(points)} trials.")

    print("[ingest] Done.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest trial corpus JSONL into Qdrant")
    parser.add_argument("-i", "--json-path", required=True, help="Path to trials JSONL")
    parser.add_argument("-bs", "--batch-size", type=int, default=50)
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()
    ingest_corpus(args.json_path, batch_size=args.batch_size, recreate=args.recreate)