import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from utils.qdrant_util import get_qdrant_client

collection = os.getenv("QDRANT_PATIENT_COLLECTION", "patient_profiles_hybrid_v1")
client = get_qdrant_client()

count = client.count(collection_name=collection, exact=True).count
print(f"collection: {collection}")
print(f"total_points: {count}")

info = client.get_collection(collection_name=collection)
vectors = info.config.params.vectors
sparse = info.config.params.sparse_vectors
print("dense_vectors:", {k: (v.size, str(v.distance)) for k, v in (vectors or {}).items()})
print("sparse_vectors:", list((sparse or {}).keys()))
print("=" * 80)

points, _ = client.scroll(
    collection_name=collection,
    limit=3,
    with_payload=True,
    with_vectors=True,
)

for i, p in enumerate(points, 1):
    payload = p.payload or {}
    raw_profile = payload.get("raw_profile", {})
    vecs = p.vector or {}
    dense = vecs.get("dense_medical") if isinstance(vecs, dict) else None
    sparse_v = vecs.get("bm25_sparse") if isinstance(vecs, dict) else None
    print(f"\n----- POINT {i} -----")
    print("qdrant_id:", p.id)
    print("patient_id:", payload.get("patient_id"))
    if isinstance(dense, list):
        print(f"dense_vector: dim={len(dense)} sample={ [round(x,4) for x in dense[:5]] } ...")
    if sparse_v is not None:
        n = len(getattr(sparse_v, "indices", []) or [])
        print(f"sparse_vector: nonzero_terms={n}")
    print("raw_profile keys:", sorted(raw_profile.keys()) if isinstance(raw_profile, dict) else type(raw_profile).__name__)
    print("raw_profile:")
    print(json.dumps(raw_profile, indent=2, ensure_ascii=False)[:2500])
    exp = payload.get("_expanded")
    if isinstance(exp, str):
        print("_expanded (first 300 chars):", exp[:300])
