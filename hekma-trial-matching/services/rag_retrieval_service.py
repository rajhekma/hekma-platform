from __future__ import annotations

import os
import re
import uuid
from typing import Any
from collections import Counter
import logging


_UUID_NS = uuid.NAMESPACE_DNS
_qdrant_client = None
_openai_client = None
_bm25_model = None
logger = logging.getLogger("rag_retrieval")


def _stable_id(text: str) -> str:
    return str(uuid.uuid5(_UUID_NS, text))


def _get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        from utils.qdrant_util import get_qdrant_client

        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", "6333"))
        logger.info("[RAG] Initializing Qdrant client host=%s port=%s", host, port)
        _qdrant_client = get_qdrant_client()
    return _qdrant_client


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    return _openai_client


def _get_bm25_model():
    global _bm25_model
    if _bm25_model is None:
        try:
            from fastembed import SparseTextEmbedding

            _bm25_model = SparseTextEmbedding(model_name="Qdrant/bm25")
            logger.info("[RAG] Using fastembed sparse model: Qdrant/bm25")
        except Exception:
            # Windows environments may fail loading onnxruntime DLLs.
            # Keep RAG flow alive by using a lightweight hashed sparse fallback.
            _bm25_model = False
            logger.warning("[RAG] fastembed unavailable; using hashed sparse fallback")
    return _bm25_model


_EMBED_MODEL = "text-embedding-3-large"
_EMBED_MAX_TOKENS_DEFAULT = 8000
_tiktoken_encoding = None


def _embed_max_tokens() -> int:
    """OpenAI embedding input cap; default leaves headroom under the 8192 limit."""
    try:
        return max(512, int(os.getenv("RAG_EMBED_MAX_TOKENS", str(_EMBED_MAX_TOKENS_DEFAULT))))
    except (TypeError, ValueError):
        return _EMBED_MAX_TOKENS_DEFAULT


def _get_tiktoken_encoding():
    global _tiktoken_encoding
    if _tiktoken_encoding is None:
        import tiktoken

        _tiktoken_encoding = tiktoken.get_encoding("cl100k_base")
    return _tiktoken_encoding


def truncate_text_for_embedding(text: str, max_tokens: int | None = None) -> str:
    """Trim text so text-embedding-3-large does not reject the request."""
    raw = (text or "").strip()
    if not raw:
        return ""
    limit = max_tokens or _embed_max_tokens()
    try:
        enc = _get_tiktoken_encoding()
        tokens = enc.encode(raw)
        if len(tokens) <= limit:
            return raw
        truncated = enc.decode(tokens[:limit])
        logger.warning(
            "Truncated embedding input | tokens_before=%s tokens_after=%s chars_before=%s",
            len(tokens),
            limit,
            len(raw),
        )
        return truncated
    except ImportError:
        # Fallback when tiktoken is missing (local dev); ~4 chars/token is conservative.
        max_chars = max(1024, limit * 4)
        if len(raw) <= max_chars:
            return raw
        logger.warning(
            "Truncated embedding input (char fallback) | chars_before=%s chars_after=%s",
            len(raw),
            max_chars,
        )
        return raw[:max_chars]


def _embed(text: str) -> list[float]:
    client = _get_openai_client()
    safe_text = truncate_text_for_embedding(text)
    resp = client.embeddings.create(model=_EMBED_MODEL, input=safe_text)
    try:
        from services.ai_usage import emit_llm_usage

        emit_llm_usage(
            product="trial_match",
            feature="trial_match.embedding",
            provider="openai",
            model=_EMBED_MODEL,
            usage=getattr(resp, "usage", None),
            source_service="hekma-trialgpt",
        )
    except Exception:
        logger.debug("AI usage emit skipped", exc_info=True)
    return resp.data[0].embedding


def _retrieval_tuning():
    """Relevance tuning knobs (env-overridable).

    * RAG_OVERSAMPLE: hybrid pool = top_k * oversample (wider recall before re-rank)
    * RAG_DENSE_RERANK: reorder the hybrid pool by pure dense cosine (topical
      relevance) so semantically on-topic candidates rise into the returned top_k
    * RAG_MAX_POOL: hard cap on the pool size
    """
    try:
        oversample = max(1, int(os.getenv("RAG_OVERSAMPLE", "3")))
    except (TypeError, ValueError):
        oversample = 3
    rerank = os.getenv("RAG_DENSE_RERANK", "true").lower() in ("1", "true", "yes")
    try:
        max_pool = max(10, int(os.getenv("RAG_MAX_POOL", "200")))
    except (TypeError, ValueError):
        max_pool = 200
    return oversample, rerank, max_pool


def _dense_rerank_order(qdrant, collection, dense_query, dense_vec, id_field, pool_ids, pool_k):
    """Return candidate ids ordered by pure dense cosine similarity (topical relevance).

    Candidates absent from the dense result keep a 0 score and fall to the back,
    preserving their original hybrid order as the tiebreak.
    """
    try:
        dense_res = qdrant.query_points(
            collection_name=collection,
            query=dense_query,
            using=dense_vec,
            limit=pool_k,
            with_payload=True,
        )
    except Exception:
        return pool_ids

    dense_scores = {}
    for pt in dense_res.points:
        cid = pt.payload.get(id_field)
        if cid is not None:
            dense_scores[cid] = pt.score or 0.0

    original_rank = {cid: i for i, cid in enumerate(pool_ids)}
    return sorted(
        pool_ids,
        key=lambda cid: (dense_scores.get(cid, 0.0), -original_rank.get(cid, 0)),
        reverse=True,
    )


def _bm25_sparse_vector(text: str):
    from qdrant_client.models import SparseVector

    model = _get_bm25_model()
    if model:
        result = list(model.embed([text]))[0]
        return SparseVector(indices=result.indices.tolist(), values=result.values.tolist())

    # Fallback sparse representation: token-frequency hashing.
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    counts = Counter(tokens)
    if not counts:
        return SparseVector(indices=[0], values=[0.0])
    modulus = 2_000_003
    bucket = {}
    for tok, val in counts.items():
        idx = abs(hash(tok)) % modulus
        bucket[idx] = bucket.get(idx, 0.0) + float(val)
    indices = sorted(bucket.keys())
    values = [bucket[i] for i in indices]
    return SparseVector(indices=indices, values=values)


def _flatten_dict_text(data: dict[str, Any]) -> str:
    parts = []
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, list):
            flat = ", ".join(str(x) for x in value if x is not None)
        elif isinstance(value, dict):
            flat = ", ".join(f"{k}: {v}" for k, v in value.items() if v is not None)
        else:
            flat = str(value)
        if flat.strip():
            parts.append(f"{key}: {flat.strip()}")
    return " ".join(parts)


def _parse_criteria(text: str) -> str:
    lines = [l.strip() for l in text.split("\n\n") if l.strip()]
    if len(lines) <= 1:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
    lines = [l for l in lines if not l.lower().startswith("inclusion") and not l.lower().startswith("exclusion") and l != ":"]
    return "\n".join(f"{i}. {c}" for i, c in enumerate(lines))


def _trial_dense_text(trial: dict[str, Any]) -> str:
    diseases = trial.get("diseases_list") or trial.get("diseases") or []
    drugs = trial.get("drugs_list") or trial.get("drugs") or []
    summary = (trial.get("brief_summary") or trial.get("text") or "").strip()
    inc = _parse_criteria(trial.get("inclusion_criteria", ""))
    exc = _parse_criteria(trial.get("exclusion_criteria", ""))
    parts = [f"Title: {trial.get('title', '')}"]
    if diseases:
        parts.append(f"Target diseases: {', '.join(diseases)}")
    if summary:
        parts.append(f"Summary: {summary}")
    if drugs:
        parts.append(f"Interventions: {', '.join(drugs)}")
    if inc:
        parts.append(f"Inclusion criteria:\n{inc}")
    if exc:
        parts.append(f"Exclusion criteria:\n{exc}")
    return "\n".join(parts)


def _trial_sparse_text(trial: dict[str, Any]) -> str:
    diseases = trial.get("diseases_list") or trial.get("diseases") or []
    drugs = trial.get("drugs_list") or trial.get("drugs") or []
    inc = _parse_criteria(trial.get("inclusion_criteria", ""))
    exc = _parse_criteria(trial.get("exclusion_criteria", ""))
    tokens = [trial.get("title", ""), " ".join(diseases), " ".join(drugs), inc, exc]
    return " ".join(t for t in tokens if t)


def retrieve_trial_ids_for_patient(
    patient_id: str,
    raw_profile: dict[str, Any],
    top_k: int = 20,
    threshold: float = 0.1,
    debug: bool = False,
) -> list[str]:
    from qdrant_client.models import Prefetch, FusionQuery, Fusion

    qdrant = _get_qdrant_client()
    trial_collection = os.getenv("QDRANT_TRIAL_COLLECTION", "clinical_trials_hybrid_v1")
    patient_collection = os.getenv("QDRANT_PATIENT_COLLECTION", "patient_profiles_hybrid_v1")
    dense_vec = os.getenv("QDRANT_DENSE_VECTOR", "dense_medical")
    sparse_vec = os.getenv("QDRANT_SPARSE_VECTOR", "bm25_sparse")

    point_id = _stable_id(patient_id)
    logger.info(
        "[RAG:P2T] Retrieving trials patient_id=%s top_k=%s threshold=%.3f collections(patient=%s,trial=%s)",
        patient_id,
        top_k,
        threshold,
        patient_collection,
        trial_collection,
    )
    expanded = ""
    try:
        found = qdrant.retrieve(collection_name=patient_collection, ids=[point_id], with_payload=True)
        if found:
            expanded = found[0].payload.get("_expanded", "") or ""
    except Exception:
        expanded = ""

    base_text = _flatten_dict_text(raw_profile or {})
    if debug:
        logger.info(
            "[RAG:P2T][DEBUG] profile_fields=%s base_text_chars=%s",
            len(raw_profile or {}),
            len(base_text or ""),
        )
    if not expanded:
        expanded = base_text
    if debug:
        logger.info("[RAG:P2T][DEBUG] expanded_text_chars=%s", len(expanded or ""))

    dense_query = _embed(base_text)
    sparse_base = _bm25_sparse_vector(base_text)
    sparse_expanded = _bm25_sparse_vector(expanded)

    oversample, rerank, max_pool = _retrieval_tuning()
    pool_k = min(max(top_k * oversample, top_k), max_pool)

    results = qdrant.query_points(
        collection_name=trial_collection,
        prefetch=[
            Prefetch(query=dense_query, using=dense_vec, limit=150),
            Prefetch(query=sparse_base, using=sparse_vec, limit=150),
            Prefetch(query=sparse_expanded, using=sparse_vec, limit=150),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=pool_k,
        with_payload=True,
    )

    pool = [
        pt.payload.get("nct_id")
        for pt in results.points
        if pt.payload.get("nct_id") and (pt.score or 0) >= threshold
    ]

    if rerank and pool:
        pool = _dense_rerank_order(
            qdrant, trial_collection, dense_query, dense_vec, "nct_id", pool, pool_k
        )

    out = pool[:top_k]
    logger.info(
        "[RAG:P2T] Retrieved %s trial candidates for patient_id=%s (pool=%s oversample=%s rerank=%s)",
        len(out),
        patient_id,
        len(pool),
        oversample,
        rerank,
    )
    return out


def retrieve_patient_ids_for_trial(
    trial: dict[str, Any],
    top_k: int = 20,
    threshold: float = 0.1,
    debug: bool = False,
) -> list[str]:
    from qdrant_client.models import Prefetch, FusionQuery, Fusion

    qdrant = _get_qdrant_client()
    patient_collection = os.getenv("QDRANT_PATIENT_COLLECTION", "patient_profiles_hybrid_v1")
    logger.info(
        "[RAG:T2P] Retrieving patients nct_like_title=%r top_k=%s threshold=%.3f collection=%s",
        (trial.get("title") or "")[:80],
        top_k,
        threshold,
        patient_collection,
    )
    dense_vec = os.getenv("QDRANT_DENSE_VECTOR", "dense_medical")
    sparse_vec = os.getenv("QDRANT_SPARSE_VECTOR", "bm25_sparse")

    dense_text = _trial_dense_text(trial)
    sparse_text = _trial_sparse_text(trial)
    expanded_text = sparse_text  # keep deterministic and cheap for API flow
    if debug:
        logger.info(
            "[RAG:T2P][DEBUG] dense_chars=%s sparse_chars=%s",
            len(dense_text or ""),
            len(sparse_text or ""),
        )

    dense_query = _embed(dense_text)
    sparse_base = _bm25_sparse_vector(sparse_text)
    sparse_expanded = _bm25_sparse_vector(expanded_text)

    oversample, rerank, max_pool = _retrieval_tuning()
    pool_k = min(max(top_k * oversample, top_k), max_pool)

    results = qdrant.query_points(
        collection_name=patient_collection,
        prefetch=[
            Prefetch(query=dense_query, using=dense_vec, limit=150),
            Prefetch(query=sparse_base, using=sparse_vec, limit=150),
            Prefetch(query=sparse_expanded, using=sparse_vec, limit=150),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=pool_k,
        with_payload=True,
    )

    pool = [
        pt.payload.get("patient_id")
        for pt in results.points
        if pt.payload.get("patient_id") and (pt.score or 0) >= threshold
    ]

    if rerank and pool:
        pool = _dense_rerank_order(
            qdrant, patient_collection, dense_query, dense_vec, "patient_id", pool, pool_k
        )

    out = pool[:top_k]
    logger.info(
        "[RAG:T2P] Retrieved %s patient candidates (pool=%s oversample=%s rerank=%s)",
        len(out), len(pool), oversample, rerank,
    )
    return out
