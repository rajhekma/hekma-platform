"""Shared Qdrant client factory for API and TrialGPT_RAG ingest scripts."""

from __future__ import annotations

import os


def get_qdrant_client():
    from qdrant_client import QdrantClient

    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    api_key = (os.getenv("QDRANT_API_KEY") or "").strip() or None
    https = os.getenv("QDRANT_HTTPS", "false").strip().lower() in ("1", "true", "yes")
    scheme = "https" if https else "http"

    # Use explicit URL so api_key works over plain HTTP (not HTTPS).
    return QdrantClient(
        url=f"{scheme}://{host}:{port}",
        api_key=api_key,
        check_compatibility=False,
    )
