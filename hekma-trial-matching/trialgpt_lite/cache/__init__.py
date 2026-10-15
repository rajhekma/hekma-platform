"""
PostgreSQL Cache-Aside Subsystem for TrialGPT Lite.
Provides high-speed persistent caching for search queries and clinical trial protocols.
"""

from trialgpt_lite.cache.pg_cache import (
    PostgreSQLCache,
    get_pg_cache,
    compute_query_hash,
    compute_match_hash,
)

__all__ = ["PostgreSQLCache", "get_pg_cache", "compute_query_hash", "compute_match_hash"]

