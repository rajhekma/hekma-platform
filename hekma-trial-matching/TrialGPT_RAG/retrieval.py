import json
from qdrant_client.models import (
    Filter, FieldCondition, Range, MatchAny,
    FusionQuery, Fusion, Prefetch,
)
from config import qdrant, COLLECTION, DENSE_VEC, SPARSE_VEC
from utils import (
    embed, bm25_sparse_vector,
    extract_patient_profile, expand_query_terms,
    profile_to_dense_text, profile_to_keywords,
)


def hybrid_retrieve(patient_note: str, top_k_final: int = 80, profile: dict = None) -> list[dict]:
    if profile is None:
        print("[query] Extracting structured patient profile…")
        profile = extract_patient_profile(patient_note)
        profile["_expanded"] = expand_query_terms(profile)
        print(f"[query] Profile:\n{json.dumps(profile, indent=2)}")

    dense_query      = embed(profile_to_dense_text(profile))
    sparse_query     = bm25_sparse_vector(profile_to_keywords(profile))
    expanded_query   = bm25_sparse_vector(profile.get("_expanded", profile_to_keywords(profile)))
    raw_sparse_query = bm25_sparse_vector(patient_note)

    patient_age = profile.get("age")
    patient_sex = profile.get("sex", "Unknown")

    # Age: soft filter (should) so trials with null age are not excluded
    # Sex: hard filter (must) since it's usually explicit in trials
    must_conditions   = []
    should_conditions = []

    if patient_age is not None:
        should_conditions.append(FieldCondition(key="min_age", range=Range(lte=patient_age)))
        should_conditions.append(FieldCondition(key="max_age", range=Range(gte=patient_age)))
    if patient_sex not in ("All", "Unknown"):
        must_conditions.append(FieldCondition(key="sex", match=MatchAny(any=[patient_sex, "All"])))

    query_filter = None
    # query_filter = Filter(
    #     must=must_conditions     if must_conditions   else None,
    #     should=should_conditions if should_conditions else None,
    # ) if (must_conditions or should_conditions) else None

    results = qdrant.query_points(
        collection_name=COLLECTION,
        prefetch=[
            Prefetch(query=dense_query,       using=DENSE_VEC,  limit=150, filter=query_filter),
            Prefetch(query=sparse_query,      using=SPARSE_VEC, limit=150, filter=query_filter),
            Prefetch(query=expanded_query,    using=SPARSE_VEC, limit=150, filter=query_filter),
            Prefetch(query=raw_sparse_query,  using=SPARSE_VEC, limit=150, filter=query_filter),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k_final,
        with_payload=True,
    )

    return [
        {
            "nct_id":  pt.payload.get("nct_id"),
            "title":   pt.payload.get("title"),
            "score":   pt.score,
            "payload": pt.payload,
        }
        for pt in results.points
    ]