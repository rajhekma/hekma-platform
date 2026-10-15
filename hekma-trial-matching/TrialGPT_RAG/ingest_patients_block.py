import os
import re
import json
import time
import uuid
import argparse
from utils import ensure_collection
from tqdm import tqdm
from qdrant_client.models import (
    Distance,
    VectorParams,
    SparseVectorParams,
    SparseIndexParams,
    PointStruct,
)
from config import qdrant, DENSE_DIM, DENSE_VEC, SPARSE_VEC, PATIENT_COLLECTION

_UUID_NS = uuid.NAMESPACE_DNS
def stable_id(text: str) -> str:
    return str(uuid.uuid5(_UUID_NS, text))
from utils import embed, embed_batch, bm25_sparse_vector, expand_query_terms


def normalize_patient_id(value: str) -> str:
    """
    Canonicalize patient id format to match compose_summary_block keys.
    - Trim surrounding spaces.
    - For UUIDs, normalize to lowercase canonical form.
    """
    text = str(value).strip()
    try:
        return str(uuid.UUID(text))
    except Exception:
        return text


def _stringify_section(value) -> list[str]:
    """Convert nested profile sections into a flat list of strings."""
    parts = []

    if value is None:
        return parts

    if isinstance(value, str):
        text = value.strip()
        if text:
            parts.append(text)
        return parts

    if isinstance(value, (int, float, bool)):
        parts.append(str(value))
        return parts

    if isinstance(value, list):
        for item in value:
            parts.extend(_stringify_section(item))
        return parts

    if isinstance(value, dict):
        for k, v in value.items():
            if v is None:
                continue

            if isinstance(v, (str, int, float, bool)):
                text = str(v).strip()
                if text:
                    parts.append(f"{k}: {text}")
            elif isinstance(v, list):
                flattened = _stringify_section(v)
                if flattened:
                    parts.append(f"{k}: " + ", ".join(flattened))
            elif isinstance(v, dict):
                nested = _stringify_section(v)
                if nested:
                    parts.append(f"{k}: " + ", ".join(nested))
        return parts

    return parts


def profile_to_dense_text(profile: dict) -> str:
    """Convert nested patient profile into a dense semantic text string."""
    sections = [
        "demographics",
        "allergies",
        "conditions",
        "procedures",
        "medications",
        "observations",
        "immunizations",
    ]

    parts = []
    for section in sections:
        section_value = profile.get(section)
        flattened = _stringify_section(section_value)
        if flattened:
            parts.append(f"{section}: " + " | ".join(flattened))

    return " ".join(parts)


def profile_to_keywords(profile: dict) -> str:
    """Convert nested patient profile into keyword-heavy sparse text."""
    sections = [
        "demographics",
        "allergies",
        "conditions",
        "procedures",
        "medications",
        "observations",
        "immunizations",
    ]

    tokens = []
    for section in sections:
        tokens.extend(_stringify_section(profile.get(section)))

    return " ".join(t for t in tokens if t)


def load_patient_block_summaries(path: str) -> list[dict]:
    """
    Load patient_block_summaries.json with format:
    {
      "<patient_id>": {
        "demographics": ...,
        "allergies": ...,
        "conditions": ...,
        "procedures": ...,
        "medications": ...,
        "observations": ...,
        "immunizations": ...
      },
      ...
    }

    Returns:
        [
            {"_id": "<patient_id>", "raw_profile": {...}},
            ...
        ]
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level JSON object in {path}")

    queries = []
    for patient_id, raw_profile in data.items():
        if not isinstance(raw_profile, dict):
            raise ValueError(
                f"Profile for patient_id={patient_id} must be a JSON object, "
                f"got {type(raw_profile).__name__}"
            )

        normalized_pid = normalize_patient_id(patient_id)

        queries.append(
            {
                "_id": normalized_pid,
                "raw_profile": raw_profile,
            }
        )

    if not queries:
        raise ValueError(f"No patient profiles found in {path}")

    return queries


def ingest_patient_block_summaries(
    summaries_path: str,
    batch_size: int,
    recreate: bool,
    expanded_cache_path: str = None,
):
    """Ingest patient_block_summaries.json into Qdrant using hybrid dense+sparse vectors."""
    queries = load_patient_block_summaries(summaries_path)

    expanded_cache = {}
    if expanded_cache_path and os.path.exists(expanded_cache_path):
        with open(expanded_cache_path) as f:
            expanded_cache = json.load(f)
        print(f"[cache] Loaded {len(expanded_cache)} expanded profiles from '{expanded_cache_path}'")

    ensure_collection(PATIENT_COLLECTION, recreate=recreate)

    skip_expansion = os.getenv("QDRANT_INGEST_SKIP_QUERY_EXPANSION", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    try:
        embed_batch_size = int(os.getenv("QDRANT_INGEST_EMBED_BATCH", "128"))
    except ValueError:
        embed_batch_size = 128
    embed_batch_size = max(1, embed_batch_size)

    # Precompute per-patient text once (dense text + sparse/expanded text).
    prepared = []
    for query in queries:
        pid = normalize_patient_id(query["_id"])
        raw_profile = query["raw_profile"]
        dense_text = profile_to_dense_text(raw_profile)
        if skip_expansion:
            expanded = profile_to_keywords(raw_profile)
        else:
            expanded = expanded_cache.get(pid) or expand_query_terms(raw_profile)
        prepared.append((pid, raw_profile, dense_text, expanded))

    points = []
    # Embed dense vectors in large batches (one OpenAI request per group) — this is
    # ~100x fewer round-trips than embedding one patient at a time.
    for start in tqdm(
        range(0, len(prepared), embed_batch_size),
        desc="Embedding patients",
        unit="batch",
    ):
        group = prepared[start : start + embed_batch_size]
        dense_vectors = embed_batch([g[2] for g in group])

        for (pid, raw_profile, _dense_text, expanded), dense_vec in zip(group, dense_vectors):
            points.append(
                PointStruct(
                    id=stable_id(pid),
                    vector={
                        DENSE_VEC:  dense_vec,
                        SPARSE_VEC: bm25_sparse_vector(expanded),
                    },
                    payload={
                        "patient_id":  pid,
                        "raw_profile": raw_profile,
                        "_expanded":   expanded,
                    },
                )
            )

            if len(points) >= batch_size:
                _upsert_patient_points(points)
                tqdm.write(f"[ingest] Upserted batch of {len(points)} patients")
                points = []

    if points:
        _upsert_patient_points(points)
        tqdm.write(f"[ingest] Upserted final {len(points)} patients")

    print(f"[done] Ingested {len(queries)} patients into '{PATIENT_COLLECTION}'.")


def _upsert_patient_points(points: list) -> None:
    for attempt in range(4):
        try:
            qdrant.upsert(collection_name=PATIENT_COLLECTION, points=points)
            return
        except Exception as exc:
            if attempt >= 3:
                raise
            wait = 2 ** attempt
            print(f"[ingest] Upsert retry {attempt + 1}/3 after error: {exc}")
            time.sleep(wait)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest patient_block_summaries.json into Qdrant"
    )
    parser.add_argument(
        "-js",
        "--json-path",
        required=True,
        help="Path to patient_block_summaries.json",
    )
    parser.add_argument(
        "-bs",
        "--batch-size",
        type=int,
        default=50,
        help="Upsert batch size",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate patient collection",
    )
    parser.add_argument(
        "--expanded-cache",
        default=None,
        help="Path to expanded_cache.json from dump_expanded.py",
    )
    args = parser.parse_args()

    ingest_patient_block_summaries(
        summaries_path=args.json_path,
        batch_size=args.batch_size,
        recreate=args.recreate,
        expanded_cache_path=args.expanded_cache,
    )