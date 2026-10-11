"""
EHR Summary Cache Repository
============================
Manages the ehr_summary_cache table — one row per patient_id.

Strategy
--------
* Read       → SELECT WHERE patient_id = %s AND expires_at > NOW()
* Write      → INSERT ... ON CONFLICT (patient_id) DO UPDATE ... WHERE updated_at <= generation_start
               The WHERE guard prevents a long-running generation from overwriting a cache that was
               invalidated mid-flight (e.g. a Fasten ingest completed while the AI phase was running).
* Invalidate → Soft-delete: UPDATE SET expires_at = past, updated_at = NOW()
               Keeps the row so its updated_at timestamp can be checked by a concurrent write guard.
               Hard rows (never-seen patients) work as before via plain INSERT on first write.

TTL is controlled by EHR_SUMMARY_CACHE_TTL_HOURS (default 24).

Log levels
----------
INFO  — cache HIT (with TTL remaining), cache STORE, cache INVALIDATE
DEBUG — cache MISS reason (no row vs expired), store timing, stats results
WARNING — non-fatal read/write failures (request still succeeds)
ERROR — hard failures that warrant attention
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from psycopg2.extras import Json

from ..awsutils.postgresql_utils import pg_transaction

logger = logging.getLogger(__name__)

_TTL_HOURS = int(os.getenv("EHR_SUMMARY_CACHE_TTL_HOURS", "24"))

_DDL = """
CREATE TABLE IF NOT EXISTS ehr_summary_cache (
    id              BIGSERIAL   PRIMARY KEY,
    patient_id      TEXT        NOT NULL UNIQUE,
    summary_json    JSONB       NOT NULL,
    slim_json       JSONB,
    record_count    INT         NOT NULL DEFAULT 0,
    generated_at    TIMESTAMP   NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMP   NOT NULL,
    source_version  TEXT        NOT NULL DEFAULT '',
    created_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP   NOT NULL DEFAULT NOW()
);
ALTER TABLE ehr_summary_cache ADD COLUMN IF NOT EXISTS slim_json JSONB;
CREATE INDEX IF NOT EXISTS idx_ehr_summary_cache_patient ON ehr_summary_cache (patient_id);
CREATE INDEX IF NOT EXISTS idx_ehr_summary_cache_expires ON ehr_summary_cache (expires_at);
"""


def ensure_cache_table() -> None:
    """Idempotently create the cache table if it does not yet exist."""
    logger.debug("Ensuring ehr_summary_cache table exists (DDL)")
    t0 = time.perf_counter()
    try:
        with pg_transaction(dict_cursor=False) as (_, cur):
            cur.execute(_DDL)
        logger.debug("Cache table verified | elapsed=%.3fs", time.perf_counter() - t0)
    except Exception as exc:
        logger.warning(
            "Could not ensure ehr_summary_cache table | elapsed=%.3fs | error=%s",
            time.perf_counter() - t0, exc,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def strip_original_records(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of the summary dict with original_record removed from all events."""
    slim = dict(data)
    if "timeline" in slim:
        slim["timeline"] = [
            {k: v for k, v in ev.items() if k != "original_record"}
            for ev in slim["timeline"]
        ]
    if "categories" in slim:
        slim["categories"] = [
            {
                **cat,
                "events": [
                    {k: v for k, v in ev.items() if k != "original_record"}
                    for ev in cat.get("events", [])
                ],
            }
            for cat in slim["categories"]
        ]
    return slim


def get_cached_summary(
    patient_id: str,
    include_records: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Return the cached summary for *patient_id* if it exists and has not expired.
    Returns None on MISS (no row) or expiry.

    include_records=False (default) — fetches slim_json (no original_record),
        much faster: ~40% less data transferred from DB.
    include_records=True — fetches the full summary_json.
    """
    logger.debug(
        "Cache lookup | patient_id=%s | include_records=%s", patient_id, include_records
    )
    t0 = time.perf_counter()
    try:
        col = "summary_json" if include_records else "COALESCE(slim_json, summary_json)"
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                f"""
                SELECT {col} AS payload, generated_at, expires_at, record_count
                FROM   ehr_summary_cache
                WHERE  patient_id = %s
                  AND  expires_at > NOW()
                LIMIT  1
                """,
                (patient_id,),
            )
            row = cur.fetchone()

        elapsed = time.perf_counter() - t0

        if not row:
            logger.info(
                "Cache MISS | patient_id=%s | reason=no_valid_entry | lookup=%.3fs",
                patient_id, elapsed,
            )
            return None

        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)

        generated_at: datetime = row["generated_at"]
        expires_at: datetime = row["expires_at"]
        record_count: int = row["record_count"]

        now_utc = datetime.utcnow()
        ttl_remaining_s = (expires_at - now_utc).total_seconds()
        age_s = (now_utc - generated_at).total_seconds()

        logger.info(
            "Cache HIT | patient_id=%s | records=%d | include_records=%s | "
            "generated_at=%s | expires_at=%s | "
            "age=%.0fs | ttl_remaining=%.0fs | lookup=%.3fs",
            patient_id, record_count, include_records,
            generated_at.strftime("%Y-%m-%d %H:%M UTC"),
            expires_at.strftime("%Y-%m-%d %H:%M UTC"),
            age_s, ttl_remaining_s, elapsed,
        )

        return {
            "data": payload,
            "generated_at": generated_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "record_count": record_count,
        }

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        logger.warning(
            "Cache read ERROR | patient_id=%s | elapsed=%.3fs | error=%s — falling through to live generation",
            patient_id, elapsed, exc,
        )
        return None


def store_cached_summary(
    patient_id: str,
    summary_dict: Dict[str, Any],
    record_count: int = 0,
    generation_start: Optional[datetime] = None,
) -> bool:
    """
    Upsert the summary for *patient_id*.

    Mid-flight invalidation guard
    -----------------------------
    If *generation_start* is provided, the ON CONFLICT UPDATE is only applied
    when the existing row's ``updated_at`` is older than *generation_start*.
    This prevents a generation that started before a Fasten ingest (which
    soft-deletes the cache and bumps ``updated_at``) from overwriting the
    now-current empty slot with stale pre-ingest data.

    Returns True if the row was written, False if blocked or on error.
    A write failure is logged but never propagates to the caller.
    """
    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)
    expires_at = now + timedelta(hours=_TTL_HOURS)
    expires_at_naive = expires_at.replace(tzinfo=None)

    # Guard timestamp: if generation_start is None, use the epoch so the
    # WHERE always passes (backward-compatible path, no guard needed).
    guard_ts = (
        generation_start.replace(tzinfo=None)
        if generation_start is not None
        else datetime(1970, 1, 1)
    )

    slim_dict = strip_original_records(summary_dict)

    logger.debug(
        "Cache store start | patient_id=%s | records=%d | ttl_hours=%d | "
        "expires_at=%s | guard_ts=%s",
        patient_id, record_count, _TTL_HOURS,
        expires_at.strftime("%Y-%m-%d %H:%M UTC"),
        guard_ts.isoformat() if generation_start else "none (no guard)",
    )
    t0 = time.perf_counter()

    try:
        with pg_transaction(dict_cursor=False) as (_, cur):
            cur.execute(
                """
                INSERT INTO ehr_summary_cache
                    (patient_id, summary_json, slim_json, record_count, generated_at, expires_at, updated_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (patient_id) DO UPDATE
                    SET summary_json  = EXCLUDED.summary_json,
                        slim_json     = EXCLUDED.slim_json,
                        record_count  = EXCLUDED.record_count,
                        generated_at  = EXCLUDED.generated_at,
                        expires_at    = EXCLUDED.expires_at,
                        updated_at    = EXCLUDED.updated_at
                    WHERE ehr_summary_cache.updated_at <= %s
                """,
                (
                    patient_id,
                    Json(summary_dict),
                    Json(slim_dict),
                    record_count,
                    now_naive,
                    expires_at_naive,
                    now_naive,
                    guard_ts,               # WHERE guard
                ),
            )
            written = cur.rowcount > 0

        elapsed = time.perf_counter() - t0
        if written:
            logger.info(
                "Cache STORED | patient_id=%s | records=%d | expires_at=%s | "
                "ttl_hours=%d | elapsed=%.3fs",
                patient_id, record_count,
                expires_at.strftime("%Y-%m-%d %H:%M UTC"),
                _TTL_HOURS, elapsed,
            )
        else:
            logger.warning(
                "Cache store SKIPPED (mid-flight invalidation detected) | "
                "patient_id=%s | generation_start=%s | elapsed=%.3fs | "
                "The cache was invalidated while generation was in progress — "
                "stale data NOT written; next request will regenerate.",
                patient_id,
                generation_start.isoformat() if generation_start else "n/a",
                elapsed,
            )
        return written

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        logger.error(
            "Cache STORE FAILED | patient_id=%s | elapsed=%.3fs | error=%s",
            patient_id, elapsed, exc,
        )
        return False


def invalidate_cached_summary(patient_id: str) -> bool:
    """
    Soft-delete the cached summary for *patient_id* by expiring it immediately.

    Why soft-delete instead of hard DELETE?
    ----------------------------------------
    A hard DELETE removes the row entirely, so a concurrent long-running generation
    that started before the ingest has no way to detect the invalidation happened —
    it blindly INSERTs stale data back.

    A soft-delete (UPDATE expires_at to past, bump updated_at) leaves the row with
    a current ``updated_at`` timestamp.  ``store_cached_summary`` uses that timestamp
    as a guard: it only overwrites the row when ``updated_at <= generation_start``,
    so any generation that started before this invalidation is blocked from writing.

    ``get_cached_summary`` already filters ``expires_at > NOW()``, so callers see a
    cache MISS immediately after this call.

    Returns True if a row was soft-deleted, False if no entry existed or on error.
    """
    logger.debug("Cache invalidation start | patient_id=%s", patient_id)
    t0 = time.perf_counter()
    try:
        with pg_transaction(dict_cursor=False) as (_, cur):
            cur.execute(
                """
                UPDATE ehr_summary_cache
                   SET expires_at = NOW() - INTERVAL '1 second',
                       updated_at = NOW()
                 WHERE patient_id = %s
                """,
                (patient_id,),
            )
            invalidated = cur.rowcount > 0

        elapsed = time.perf_counter() - t0
        if invalidated:
            logger.info(
                "Cache INVALIDATED (soft-delete) | patient_id=%s | elapsed=%.3fs — "
                "entry expired immediately; next request will regenerate",
                patient_id, elapsed,
            )
        else:
            logger.info(
                "Cache invalidation — no entry found | patient_id=%s | elapsed=%.3fs",
                patient_id, elapsed,
            )

        return invalidated

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        logger.error(
            "Cache INVALIDATION FAILED | patient_id=%s | elapsed=%.3fs | error=%s",
            patient_id, elapsed, exc,
        )
        return False


def get_cache_stats() -> Dict[str, Any]:
    """Return aggregate stats about the cache table."""
    logger.debug("Cache stats query start")
    t0 = time.perf_counter()
    try:
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                """
                SELECT
                    COUNT(*)                                     AS total_entries,
                    COUNT(*) FILTER (WHERE expires_at > NOW())  AS live_entries,
                    COUNT(*) FILTER (WHERE expires_at <= NOW()) AS stale_entries,
                    MIN(generated_at)                           AS oldest_generated,
                    MAX(generated_at)                           AS newest_generated
                FROM ehr_summary_cache
                """
            )
            row = cur.fetchone()

        elapsed = time.perf_counter() - t0
        stats = dict(row) if row else {}
        logger.debug(
            "Cache stats result | total=%s | live=%s | stale=%s | elapsed=%.3fs",
            stats.get("total_entries"), stats.get("live_entries"),
            stats.get("stale_entries"), elapsed,
        )
        return stats

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        logger.warning(
            "Cache stats query FAILED | elapsed=%.3fs | error=%s",
            elapsed, exc,
        )
        return {}
