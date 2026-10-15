import os
import re
import json
from tqdm import tqdm
from fastembed import SparseTextEmbedding
from qdrant_client.models import SparseVector, Distance, VectorParams, SparseVectorParams, SparseIndexParams
from config import (
    openai_client,
    qdrant,
    LLM_MODEL,
    DENSE_DIM,
    DENSE_VEC,
    SPARSE_VEC,
    TRIAL_COLLECTION,
    PATIENT_EXTRACTION_PROMPT,
    QUERY_EXPANSION_PROMPT,
)

# ── Embedding & sparse vector ──────────────────────────────────────────────────

_bm25_model = SparseTextEmbedding(model_name="Qdrant/bm25")


def embed(text: str) -> list[float]:
    resp = openai_client.embeddings.create(model="text-embedding-3-large", input=text)
    return resp.data[0].embedding


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed many texts in a single OpenAI request (much faster than per-text).

    Returns embeddings in the same order as ``texts``. OpenAI may return items
    out of order, so we sort by the ``index`` field to be safe.
    """
    if not texts:
        return []
    resp = openai_client.embeddings.create(model="text-embedding-3-large", input=texts)
    ordered = sorted(resp.data, key=lambda d: d.index)
    return [d.embedding for d in ordered]


def bm25_sparse_vector(text: str) -> SparseVector:
    result = list(_bm25_model.embed([text]))[0]
    return SparseVector(indices=result.indices.tolist(), values=result.values.tolist())


def ensure_collection(collection: str = TRIAL_COLLECTION, recreate: bool = False):
    """Create collection with hybrid dense+sparse vectors if missing."""
    existing = [c.name for c in qdrant.get_collections().collections]
    if collection in existing:
        if not recreate:
            return
        qdrant.delete_collection(collection)
        print(f"[init] Dropped existing collection '{collection}'.")

    qdrant.create_collection(
        collection_name=collection,
        vectors_config={
            DENSE_VEC: VectorParams(size=DENSE_DIM, distance=Distance.COSINE),
        },
        sparse_vectors_config={
            SPARSE_VEC: SparseVectorParams(index=SparseIndexParams(on_disk=False)),
        },
    )
    print(f"[init] Collection '{collection}' created.")


# ── Trial metadata extraction ──────────────────────────────────────────────────

def extract_min_age(inclusion: str) -> int | None:
    m = re.search(r'(\d+)\s*(?:years?|yrs?)?\s*(?:of age)?\s*(?:and|or)?\s*(?:older|above|more)', inclusion, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r'(?:age[sd]?|between)\s+(\d+)', inclusion, re.I)
    return int(m.group(1)) if m else None


def extract_max_age(inclusion: str) -> int | None:
    m = re.search(r'(\d+)\s*(?:years?|yrs?)?\s*(?:of age)?\s*(?:and|or)?\s*(?:younger|below|less|under)', inclusion, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r'between\s+\d+\s*[-–]\s*(\d+)', inclusion, re.I)
    return int(m.group(1)) if m else None


def extract_sex(inclusion: str) -> str:
    text = inclusion.lower()
    has_male   = "male" in text
    has_female = "female" in text or "women" in text
    if has_male and has_female:
        return "All"
    if has_female:
        return "Female"
    if has_male:
        return "Male"
    return "All"


# ── Patient profile extraction ─────────────────────────────────────────────────

def extract_patient_profile(note: str) -> dict:
    resp = openai_client.chat.completions.create(
        model=LLM_MODEL,
        temperature=0,
        messages=[{"role": "user", "content": PATIENT_EXTRACTION_PROMPT.replace("{note}", note)}],
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r'^```json|^```|```$', '', raw, flags=re.MULTILINE).strip()
    return json.loads(raw)


def expand_query_terms(profile: dict) -> str:
    try:
        resp = openai_client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0,
            messages=[{"role": "user", "content": QUERY_EXPANSION_PROMPT.replace("{profile}", json.dumps(profile, indent=2))}],
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```json|^```|```$', '', raw, flags=re.MULTILINE).strip()
        match = re.search(r'\[.*?\]', raw, flags=re.DOTALL)
        if not match:
            return profile_to_keywords(profile)
        terms = json.loads(match.group())
        return " ".join(terms)
    except Exception as exc:
        print(f"[warn] Query expansion failed ({exc}); using keyword fallback")
        return profile_to_keywords(profile)

def load_or_build_profiles(queries: list[dict], cache_path: str) -> dict[str, dict]:
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            cache = json.load(f)
        print(f"[cache] Loaded {len(cache)} profiles from {cache_path}")

    missing = [q for q in queries if q["_id"] not in cache]
    if missing:
        print(f"[cache] Computing {len(missing)} missing profiles…")
        for query in tqdm(missing, desc="Extracting profiles", unit="query"):
            profile = extract_patient_profile(query["text"])
            profile["_expanded"] = expand_query_terms(profile)
            cache[query["_id"]] = profile
            with open(cache_path, "w") as f:
                json.dump(cache, f, indent=4)

    return cache

# ── Profile to query text ──────────────────────────────────────────────────────

def profile_to_dense_text(profile: dict) -> str:
    parts = []
    if profile.get("age"):
        parts.append(f"{profile['age']}-year-old {profile.get('sex', '').lower()}")
    parts.extend(profile.get("diseases", []))
    parts.extend(profile.get("biomarkers", []))
    if profile.get("stage_severity"):
        parts.append(profile["stage_severity"])
    if profile.get("prior_therapies"):
        parts.append("prior therapies: " + ", ".join(profile["prior_therapies"]))
    if profile.get("current_medications"):
        parts.append("current medications: " + ", ".join(profile["current_medications"]))
    if profile.get("comorbidities"):
        parts.append("comorbidities: " + ", ".join(profile["comorbidities"]))
    if profile.get("performance_status"):
        parts.append(profile["performance_status"])
    if profile.get("smoking_substance_history"):
        parts.append(profile["smoking_substance_history"])
    if profile.get("lab_values"):
        parts.append("labs: " + ", ".join(f"{k} {v}" for k, v in profile["lab_values"].items()))
    parts.extend(profile.get("key_constraints", []))
    return " ".join(p for p in parts if p)


def profile_to_keywords(profile: dict) -> str:
    tokens = [
        *profile.get("diseases", []),
        *profile.get("biomarkers", []),
        profile.get("stage_severity") or "",
        *profile.get("prior_therapies", []),
        *profile.get("current_medications", []),
        *profile.get("comorbidities", []),
        profile.get("performance_status") or "",
        profile.get("smoking_substance_history") or "",
        *profile.get("key_constraints", []),
    ]
    return " ".join(t for t in tokens if t)


def raw_profile_to_text(raw_profile: dict) -> str:
    """Flatten a stored patient profile dict into plain text for retrieval querying."""
    if not isinstance(raw_profile, dict):
        return str(raw_profile or "")

    parts = []
    for key, value in raw_profile.items():
        if value is None:
            continue
        if isinstance(value, list):
            text = ", ".join(str(x) for x in value if x is not None)
        elif isinstance(value, dict):
            text = ", ".join(f"{k}: {v}" for k, v in value.items() if v is not None)
        else:
            text = str(value)
        if text.strip():
            parts.append(f"{key}: {text.strip()}")
    return " ".join(parts)