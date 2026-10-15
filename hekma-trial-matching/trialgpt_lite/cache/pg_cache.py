"""
PostgreSQL Cache-Aside Subsystem for TrialGPT Lite.
Stores query results, patient match reports, and 14-section trial protocols in PostgreSQL 15 JSONB.
Includes fail-open resilience, connection pooling, 30-day retention TTLs, and cache stampede protection.
"""

import json
import logging
import re
import hashlib
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, Any

import psycopg2
from psycopg2 import pool
from psycopg2.extras import execute_values, Json

from trialgpt_lite.config import (
    PG_HOST,
    PG_PORT,
    PG_DB,
    PG_USER,
    PG_PASSWORD,
    PG_CACHE_ENABLED,
    CACHE_RETENTION_DAYS,
    PG_CACHE_QUERY_TTL,
    PG_CACHE_STUDY_TTL,
    PG_CACHE_MATCH_TTL,
)

logger = logging.getLogger("trialgpt_lite.cache.pg")


def compute_query_hash(
    condition: str,
    statuses: Optional[list[str]] = None,
    page_size: int = 10,
    page_token: Optional[str] = None,
) -> str:
    """
    Computes a canonical SHA-256 hash for a search query.
    Normalizes case, whitespace, and sorted status filters.
    """
    clean_cond = re.sub(r"\s+", " ", (condition or "").strip().lower())
    clean_statuses = ",".join(sorted(s.strip().upper() for s in (statuses or [])))
    clean_token = (page_token or "").strip()
    raw_key = f"{clean_cond}|{clean_statuses}|{page_size}|{clean_token}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def compute_match_hash(
    condition: str,
    patient_note: Optional[str] = None,
    patient_age: Optional[float] = None,
    patient_sex: Optional[str] = None,
    statuses: Optional[list[str]] = None,
    page_size: int = 10,
    page_token: Optional[str] = None,
    max_criteria_evals: Optional[int] = None,
) -> str:
    """
    Computes a canonical SHA-256 hash for a full patient-to-trial matching request.
    Normalizes clinical note text, age, biological sex, criteria evaluation limits,
    and condition search parameters for 30-day match result caching.
    """
    clean_cond = re.sub(r"\s+", " ", (condition or "").strip().lower())
    clean_note = re.sub(r"\s+", " ", (patient_note or "").strip().lower())
    age_str = f"{float(patient_age):.2f}" if patient_age is not None else "NONE"
    sex_str = (patient_sex or "ALL").strip().upper()
    clean_statuses = ",".join(sorted(s.strip().upper() for s in (statuses or [])))
    clean_token = (page_token or "").strip()
    evals_str = str(max_criteria_evals) if max_criteria_evals is not None else "ALL"

    raw_key = f"{clean_cond}|{clean_note}|{age_str}|{sex_str}|{clean_statuses}|{page_size}|{clean_token}|{evals_str}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class PostgreSQLCache:
    """
    High-performance Cache-Aside client backed by PostgreSQL with 30-Day Retention.
    Features:
    - Threaded connection pooling (ThreadedConnectionPool)
    - Single-flight locking to prevent cache stampedes (dogpiling)
    - Fail-open fallback: any database errors gracefully fall through without crashing
    - Three-tiered caching:
        1. Condition Search Query lists (trialgpt_lite_cache_queries)
        2. Evaluated Patient Match Reports (trialgpt_lite_cache_matches)
        3. 14-Section Normalized Trial Protocols (trialgpt_lite_cache_studies)
    """

    def __init__(
        self,
        host: str = PG_HOST,
        port: int = PG_PORT,
        dbname: str = PG_DB,
        user: str = PG_USER,
        password: str = PG_PASSWORD,
        enabled: bool = PG_CACHE_ENABLED,
        query_ttl: int = PG_CACHE_QUERY_TTL,
        study_ttl: int = PG_CACHE_STUDY_TTL,
        match_ttl: int = PG_CACHE_MATCH_TTL,
        retention_days: int = CACHE_RETENTION_DAYS,
        min_conn: int = 1,
        max_conn: int = 10,
    ):
        self.enabled = enabled
        self.query_ttl = query_ttl
        self.study_ttl = study_ttl
        self.match_ttl = match_ttl
        self.retention_days = retention_days
        self.pool: Optional[pool.ThreadedConnectionPool] = None
        self._flight_locks: dict[str, threading.Lock] = {}
        self._lock_guard = threading.Lock()
        self._connected = False

        if not self.enabled:
            logger.info("PostgreSQL cache is explicitly disabled via configuration.")
            return

        try:
            self.pool = pool.ThreadedConnectionPool(
                minconn=min_conn,
                maxconn=max_conn,
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
                connect_timeout=3,
            )
            self._connected = True
            logger.info(f"PostgreSQL cache connection pool initialized: {host}:{port}/{dbname} (30-day retention)")
            self._ensure_tables()
        except Exception as e:
            logger.warning(
                f"Could not connect to PostgreSQL ({host}:{port}/{dbname}): {e}. "
                "Operating in FAIL-OPEN mode (all requests will query ClinicalTrials.gov API directly)."
            )
            self.pool = None
            self._connected = False

    @contextmanager
    def get_connection(self):
        """Context manager to safely acquire and return connections to pool."""
        if not self.pool or not self._connected:
            yield None
            return

        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
        except Exception as e:
            logger.warning(f"Error acquiring PostgreSQL connection from pool: {e}")
            yield None
        finally:
            if conn and self.pool:
                try:
                    self.pool.putconn(conn)
                except Exception as e:
                    logger.warning(f"Error returning connection to pool: {e}")

    def _ensure_tables(self):
        """Ensures cache tables and indices exist in public schema with 30-day TTL support."""
        if not self._connected:
            return

        create_tables_sql = """
        -- Table 1: Search Query Cache (30-Day Retention)
        CREATE TABLE IF NOT EXISTS public.trialgpt_lite_cache_queries (
            query_hash VARCHAR(64) PRIMARY KEY,
            condition_raw TEXT NOT NULL,
            page_size INT NOT NULL DEFAULT 10,
            page_token TEXT,
            nct_ids TEXT[] NOT NULL DEFAULT '{}',
            total_in_registry INT NOT NULL DEFAULT 0,
            next_page_token TEXT,
            cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            hit_count INT NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_trialgpt_cache_queries_expires 
            ON public.trialgpt_lite_cache_queries(expires_at);

        -- Table 2: 14-Section Trial Study Protocols Cache (30-Day Retention)
        CREATE TABLE IF NOT EXISTS public.trialgpt_lite_cache_studies (
            nct_id VARCHAR(20) PRIMARY KEY,
            title TEXT NOT NULL,
            overall_status VARCHAR(50) NOT NULL,
            study_type VARCHAR(50) DEFAULT 'INTERVENTIONAL',
            conditions TEXT[] DEFAULT '{}',
            phases TEXT[] DEFAULT '{}',
            lead_sponsor TEXT,
            protocol_data JSONB NOT NULL,
            cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            last_accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            hit_count INT NOT NULL DEFAULT 1,
            ctgov_last_updated VARCHAR(50)
        );

        CREATE INDEX IF NOT EXISTS idx_trialgpt_cache_studies_status 
            ON public.trialgpt_lite_cache_studies(overall_status);
        CREATE INDEX IF NOT EXISTS idx_trialgpt_cache_studies_expires 
            ON public.trialgpt_lite_cache_studies(expires_at);

        -- Table 3: Patient Criteria Match Reports Cache (30-Day Retention)
        CREATE TABLE IF NOT EXISTS public.trialgpt_lite_cache_matches (
            match_hash VARCHAR(64) PRIMARY KEY,
            condition_raw TEXT NOT NULL,
            patient_profile JSONB,
            page_size INT NOT NULL DEFAULT 10,
            page_token TEXT,
            nct_ids TEXT[] NOT NULL DEFAULT '{}',
            report_data JSONB NOT NULL,
            cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            hit_count INT NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_trialgpt_cache_matches_expires 
            ON public.trialgpt_lite_cache_matches(expires_at);
        CREATE INDEX IF NOT EXISTS idx_trialgpt_cache_matches_ncts 
            ON public.trialgpt_lite_cache_matches USING GIN (nct_ids);

        -- Table 4: Rephrased Patient Questionnaires Cache (30-Day Retention)
        CREATE TABLE IF NOT EXISTS public.trialgpt_lite_cache_questionnaires (
            nct_id VARCHAR(20) PRIMARY KEY,
            trial_title TEXT NOT NULL,
            engine VARCHAR(50) NOT NULL DEFAULT 'GROQ',
            questionnaire_data JSONB NOT NULL,
            cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            hit_count INT NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_trialgpt_cache_quest_expires 
            ON public.trialgpt_lite_cache_questionnaires(expires_at);

        -- Table 5: Plain-English Patient Study Summaries Cache (30-Day Retention)
        CREATE TABLE IF NOT EXISTS public.trialgpt_lite_cache_summaries (
            nct_id VARCHAR(20) PRIMARY KEY,
            trial_title TEXT NOT NULL,
            engine VARCHAR(50) NOT NULL DEFAULT 'GROQ',
            summary_data JSONB NOT NULL,
            cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            hit_count INT NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_trialgpt_cache_summaries_expires 
            ON public.trialgpt_lite_cache_summaries(expires_at);
        """
        try:
            with self.get_connection() as conn:
                if conn:
                    with conn.cursor() as cur:
                        cur.execute(create_tables_sql)
                    conn.commit()
                    logger.info("PostgreSQL cache tables (queries, studies, matches, questionnaires, summaries) verified/created successfully.")
        except Exception as e:
            logger.warning(f"Failed to verify/create PostgreSQL cache tables: {e}")

    def get_flight_lock(self, key: str) -> threading.Lock:
        """Single-flight lock provider to prevent cache stampedes."""
        with self._lock_guard:
            if key not in self._flight_locks:
                self._flight_locks[key] = threading.Lock()
            return self._flight_locks[key]

    # ==========================================
    # 1. Query Cache Operations (30-Day TTL)
    # ==========================================

    def get_cached_query(self, query_hash: str, allow_expired: bool = False) -> Optional[dict[str, Any]]:
        """
        Retrieves cached query metadata (nct_ids, total_in_registry, next_page_token).
        Returns None on cache miss, expiration (unless allow_expired=True), or DB error.
        """
        if not self.enabled or not self._connected:
            return None

        sql = """
        SELECT condition_raw, page_size, page_token, nct_ids, total_in_registry, 
               next_page_token, (expires_at < NOW()) as is_expired
        FROM public.trialgpt_lite_cache_queries
        WHERE query_hash = %s;
        """
        try:
            with self.get_connection() as conn:
                if not conn:
                    return None
                with conn.cursor() as cur:
                    cur.execute(sql, (query_hash,))
                    row = cur.fetchone()
                    if not row:
                        return None

                    is_expired = row[6]
                    if is_expired and not allow_expired:
                        return None

                    try:
                        cur.execute(
                            "UPDATE public.trialgpt_lite_cache_queries SET hit_count = hit_count + 1 WHERE query_hash = %s;",
                            (query_hash,),
                        )
                        conn.commit()
                    except Exception:
                        pass

                    return {
                        "condition_raw": row[0],
                        "page_size": row[1],
                        "page_token": row[2],
                        "nct_ids": list(row[3]) if row[3] else [],
                        "total_in_registry": row[4],
                        "next_page_token": row[5],
                        "is_expired": is_expired,
                    }
        except Exception as e:
            logger.warning(f"PostgreSQL cache get_cached_query failed (fail-open): {e}")
            return None

    def get_cached_query_with_studies(
        self, query_hash: str, allow_expired: bool = False
    ) -> Optional[tuple[dict[str, Any], list[dict[str, Any]]]]:
        """
        Ultra-efficient single roundtrip query that retrieves query metadata
        AND all corresponding 14-section trial protocols from PostgreSQL in ONE query.
        Updates hit counts atomically.
        """
        if not self.enabled or not self._connected:
            return None

        sql = """
        WITH q AS (
            UPDATE public.trialgpt_lite_cache_queries
            SET hit_count = hit_count + 1
            WHERE query_hash = %s
            RETURNING condition_raw, page_size, page_token, nct_ids, total_in_registry, 
                      next_page_token, (expires_at < NOW()) as is_expired
        ),
        s AS (
            UPDATE public.trialgpt_lite_cache_studies
            SET hit_count = hit_count + 1, last_accessed_at = NOW()
            WHERE nct_id = ANY(SELECT UNNEST(nct_ids) FROM q)
            RETURNING nct_id, protocol_data, (expires_at < NOW()) as is_expired
        )
        SELECT 
            (SELECT row_to_json(q.*) FROM q) as query_meta,
            (SELECT json_object_agg(nct_id, protocol_data) FROM s WHERE (NOT is_expired OR %s)) as studies_map;
        """
        try:
            with self.get_connection() as conn:
                if not conn:
                    return None
                with conn.cursor() as cur:
                    cur.execute(sql, (query_hash, allow_expired))
                    row = cur.fetchone()
                    if not row or not row[0]:
                        return None

                    q_meta = row[0]
                    studies_map = row[1] or {}

                    if q_meta.get("is_expired") and not allow_expired:
                        return None

                    nct_ids = q_meta.get("nct_ids") or []
                    if all(nid in studies_map for nid in nct_ids):
                        studies_list = [studies_map[nid] for nid in nct_ids if nid in studies_map]
                        conn.commit()
                        return q_meta, studies_list

                conn.commit()
                return None
        except Exception as e:
            logger.warning(f"PostgreSQL cache get_cached_query_with_studies failed: {e}")
            return None

    def set_cached_query(
        self,
        query_hash: str,
        condition_raw: str,
        page_size: int,
        page_token: Optional[str],
        nct_ids: list[str],
        total_in_registry: int,
        next_page_token: Optional[str],
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """Stores or updates a search query result in the cache with 30-day TTL."""
        if not self.enabled or not self._connected:
            return False

        ttl = ttl_seconds if ttl_seconds is not None else self.query_ttl
        sql = """
        INSERT INTO public.trialgpt_lite_cache_queries (
            query_hash, condition_raw, page_size, page_token, nct_ids, 
            total_in_registry, next_page_token, cached_at, expires_at, hit_count
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, NOW(), NOW() + (%s * INTERVAL '1 second'), 1
        )
        ON CONFLICT (query_hash) DO UPDATE SET
            condition_raw = EXCLUDED.condition_raw,
            page_size = EXCLUDED.page_size,
            page_token = EXCLUDED.page_token,
            nct_ids = EXCLUDED.nct_ids,
            total_in_registry = EXCLUDED.total_in_registry,
            next_page_token = EXCLUDED.next_page_token,
            cached_at = NOW(),
            expires_at = NOW() + (%s * INTERVAL '1 second');
        """
        try:
            with self.get_connection() as conn:
                if not conn:
                    return False
                with conn.cursor() as cur:
                    cur.execute(
                        sql,
                        (
                            query_hash,
                            condition_raw,
                            page_size,
                            page_token,
                            nct_ids,
                            total_in_registry,
                            next_page_token,
                            ttl,
                            ttl,
                        ),
                    )
                conn.commit()
                return True
        except Exception as e:
            logger.warning(f"PostgreSQL cache set_cached_query failed: {e}")
            return False

    # ==========================================
    # 2. Patient Match Reports Cache (30-Day TTL)
    # ==========================================

    def get_cached_match(self, match_hash: str, allow_expired: bool = False) -> Optional[dict[str, Any]]:
        """
        Retrieves a complete cached patient matching report by match_hash.
        Updates hit count atomically using CTE.
        """
        if not self.enabled or not self._connected:
            return None

        sql = """
        WITH hit AS (
            UPDATE public.trialgpt_lite_cache_matches
            SET hit_count = hit_count + 1
            WHERE match_hash = %s
            RETURNING report_data, (expires_at < NOW()) as is_expired
        )
        SELECT report_data, is_expired FROM hit;
        """
        try:
            with self.get_connection() as conn:
                if not conn:
                    return None
                with conn.cursor() as cur:
                    cur.execute(sql, (match_hash,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    report_data, is_expired = row[0], row[1]
                    if is_expired and not allow_expired:
                        return None
                    conn.commit()
                    return report_data
        except Exception as e:
            logger.warning(f"PostgreSQL cache get_cached_match failed (fail-open): {e}")
            return None

    def set_cached_match(
        self,
        match_hash: str,
        condition_raw: str,
        patient_profile: Optional[dict[str, Any]],
        page_size: int,
        page_token: Optional[str],
        nct_ids: list[str],
        report_data: dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """
        Stores an evaluated patient match report in PostgreSQL with a 30-day TTL.
        """
        if not self.enabled or not self._connected:
            return False

        ttl = ttl_seconds if ttl_seconds is not None else self.match_ttl
        clean_ids = [nid.strip().upper() for nid in nct_ids if nid]
        sql = """
        INSERT INTO public.trialgpt_lite_cache_matches (
            match_hash, condition_raw, patient_profile, page_size, page_token,
            nct_ids, report_data, cached_at, expires_at, hit_count
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, NOW(), NOW() + (%s * INTERVAL '1 second'), 1
        )
        ON CONFLICT (match_hash) DO UPDATE SET
            condition_raw = EXCLUDED.condition_raw,
            patient_profile = EXCLUDED.patient_profile,
            page_size = EXCLUDED.page_size,
            page_token = EXCLUDED.page_token,
            nct_ids = EXCLUDED.nct_ids,
            report_data = EXCLUDED.report_data,
            cached_at = NOW(),
            expires_at = NOW() + (%s * INTERVAL '1 second');
        """
        try:
            with self.get_connection() as conn:
                if not conn:
                    return False
                with conn.cursor() as cur:
                    cur.execute(
                        sql,
                        (
                            match_hash,
                            condition_raw,
                            Json(patient_profile) if patient_profile else None,
                            page_size,
                            page_token,
                            clean_ids,
                            Json(report_data),
                            ttl,
                            ttl,
                        ),
                    )
                conn.commit()
                return True
        except Exception as e:
            logger.warning(f"PostgreSQL cache set_cached_match failed: {e}")
            return False

    # ==========================================
    # 3. Study Protocol Cache Operations (30-Day TTL)
    # ==========================================

    def get_cached_study(self, nct_id: str, allow_expired: bool = False) -> Optional[dict[str, Any]]:
        """
        Retrieves a single clinical trial protocol by NCT ID with atomic hit counter update in 1 roundtrip.
        """
        if not self.enabled or not self._connected:
            return None

        clean_id = (nct_id or "").strip().upper()
        sql = """
        WITH hit AS (
            UPDATE public.trialgpt_lite_cache_studies
            SET hit_count = hit_count + 1, last_accessed_at = NOW()
            WHERE nct_id = %s
            RETURNING protocol_data, (expires_at < NOW()) as is_expired
        )
        SELECT protocol_data, is_expired FROM hit;
        """
        try:
            with self.get_connection() as conn:
                if not conn:
                    return None
                with conn.cursor() as cur:
                    cur.execute(sql, (clean_id,))
                    row = cur.fetchone()
                    if not row:
                        return None

                    protocol_data, is_expired = row[0], row[1]
                    if is_expired and not allow_expired:
                        return None

                    conn.commit()
                    return protocol_data
        except Exception as e:
            logger.warning(f"PostgreSQL cache get_cached_study failed for {nct_id}: {e}")
            return None

    def get_cached_studies(self, nct_ids: list[str], allow_expired: bool = False) -> dict[str, dict[str, Any]]:
        """
        Batch-retrieves multiple trial protocols in a single query via `WHERE nct_id = ANY(%s)`.
        Returns {nct_id: protocol_data}.
        """
        if not self.enabled or not self._connected or not nct_ids:
            return {}

        clean_ids = [nid.strip().upper() for nid in nct_ids if nid]
        sql = """
        SELECT nct_id, protocol_data, (expires_at < NOW()) as is_expired
        FROM public.trialgpt_lite_cache_studies
        WHERE nct_id = ANY(%s);
        """
        result = {}
        try:
            with self.get_connection() as conn:
                if not conn:
                    return {}
                with conn.cursor() as cur:
                    cur.execute(sql, (clean_ids,))
                    rows = cur.fetchall()
                    for nid, p_data, is_expired in rows:
                        if not is_expired or allow_expired:
                            result[nid] = p_data

                    if result:
                        try:
                            found_ids = list(result.keys())
                            cur.execute(
                                """
                                UPDATE public.trialgpt_lite_cache_studies
                                SET hit_count = hit_count + 1, last_accessed_at = NOW()
                                WHERE nct_id = ANY(%s);
                                """,
                                (found_ids,),
                            )
                            conn.commit()
                        except Exception:
                            pass
            return result
        except Exception as e:
            logger.warning(f"PostgreSQL cache get_cached_studies failed: {e}")
            return {}

    def set_cached_studies(self, studies_data: list[dict[str, Any]], ttl_seconds: Optional[int] = None) -> int:
        """
        Batch UPSERT for multiple normalized trial protocols into `trialgpt_lite_cache_studies` with 30-day TTL.
        """
        if not self.enabled or not self._connected or not studies_data:
            return 0

        ttl = ttl_seconds if ttl_seconds is not None else self.study_ttl
        rows = []
        for s in studies_data:
            nct_id = s.get("nct_id", "").strip().upper()
            if not nct_id:
                continue
            title = s.get("brief_title") or s.get("official_title") or "Unknown Title"
            overall_status = s.get("overall_status", "UNKNOWN")
            study_type = s.get("study_type", "INTERVENTIONAL")
            conditions = s.get("conditions", [])
            phases = s.get("phases", [])
            lead_sponsor = s.get("lead_sponsor")
            last_updated = s.get("timeline", {}).get("last_updated") if s.get("timeline") else None
            protocol_json = Json(s)

            rows.append((
                nct_id,
                title,
                overall_status,
                study_type,
                conditions,
                phases,
                lead_sponsor,
                protocol_json,
                last_updated,
            ))

        if not rows:
            return 0

        upsert_sql = f"""
        INSERT INTO public.trialgpt_lite_cache_studies (
            nct_id, title, overall_status, study_type, conditions, phases, lead_sponsor,
            protocol_data, ctgov_last_updated, cached_at, expires_at, last_accessed_at, hit_count
        ) VALUES %s
        ON CONFLICT (nct_id) DO UPDATE SET
            title = EXCLUDED.title,
            overall_status = EXCLUDED.overall_status,
            study_type = EXCLUDED.study_type,
            conditions = EXCLUDED.conditions,
            phases = EXCLUDED.phases,
            lead_sponsor = EXCLUDED.lead_sponsor,
            protocol_data = EXCLUDED.protocol_data,
            ctgov_last_updated = EXCLUDED.ctgov_last_updated,
            cached_at = NOW(),
            expires_at = NOW() + ({ttl} * INTERVAL '1 second'),
            last_accessed_at = NOW();
        """
        try:
            with self.get_connection() as conn:
                if not conn:
                    return 0
                with conn.cursor() as cur:
                    template = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW() + (" + str(ttl) + " * INTERVAL '1 second'), NOW(), 1)"
                    execute_values(cur, upsert_sql, rows, template=template)
                conn.commit()
                return len(rows)
        except Exception as e:
            logger.warning(f"PostgreSQL cache set_cached_studies failed: {e}")
            return 0

    def set_cached_study(self, study_data: dict[str, Any], ttl_seconds: Optional[int] = None) -> bool:
        """Stores a single trial protocol in the cache."""
        return self.set_cached_studies([study_data], ttl_seconds=ttl_seconds) > 0

    # ==========================================
    # 4. Rephrased Questionnaire Cache (30-Day TTL)
    # ==========================================

    def get_cached_questionnaire(self, nct_id: str, allow_expired: bool = False) -> Optional[dict[str, Any]]:
        """
        Retrieves a cached rephrased patient questionnaire by nct_id.
        Increments hit count atomically.
        """
        if not self.enabled or not self._connected or not nct_id:
            return None

        clean_id = nct_id.strip().upper()
        sql = """
        WITH hit AS (
            UPDATE public.trialgpt_lite_cache_questionnaires
            SET hit_count = hit_count + 1
            WHERE nct_id = %s
            RETURNING questionnaire_data, (expires_at < NOW()) as is_expired
        )
        SELECT questionnaire_data, is_expired FROM hit;
        """
        try:
            with self.get_connection() as conn:
                if not conn:
                    return None
                with conn.cursor() as cur:
                    cur.execute(sql, (clean_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    q_data, is_expired = row[0], row[1]
                    if is_expired and not allow_expired:
                        return None
                    conn.commit()
                    return q_data
        except Exception as e:
            logger.warning(f"PostgreSQL cache get_cached_questionnaire failed for {nct_id}: {e}")
            return None

    def set_cached_questionnaire(
        self,
        nct_id: str,
        trial_title: str,
        engine: str,
        questionnaire_data: dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """
        Stores rephrased patient questions in PostgreSQL with 30-day retention.
        """
        if not self.enabled or not self._connected or not nct_id:
            return False

        clean_id = nct_id.strip().upper()
        ttl = ttl_seconds if ttl_seconds is not None else self.study_ttl
        sql = """
        INSERT INTO public.trialgpt_lite_cache_questionnaires (
            nct_id, trial_title, engine, questionnaire_data, cached_at, expires_at, hit_count
        ) VALUES (
            %s, %s, %s, %s, NOW(), NOW() + (%s * INTERVAL '1 second'), 1
        )
        ON CONFLICT (nct_id) DO UPDATE SET
            trial_title = EXCLUDED.trial_title,
            engine = EXCLUDED.engine,
            questionnaire_data = EXCLUDED.questionnaire_data,
            cached_at = NOW(),
            expires_at = NOW() + (%s * INTERVAL '1 second');
        """
        try:
            with self.get_connection() as conn:
                if not conn:
                    return False
                with conn.cursor() as cur:
                    cur.execute(
                        sql,
                        (
                            clean_id,
                            trial_title or "Trial Study",
                            engine or "GROQ",
                            Json(questionnaire_data),
                            ttl,
                            ttl,
                        ),
                    )
                conn.commit()
                return True
        except Exception as e:
            logger.warning(f"PostgreSQL cache set_cached_questionnaire failed for {nct_id}: {e}")
            return False

    # ==========================================
    # 4b. Plain-English Patient Study Summaries Cache
    # ==========================================

    def get_cached_summary(self, nct_id: str, allow_expired: bool = False) -> Optional[dict[str, Any]]:
        """
        Retrieves a cached plain-English patient study summary by nct_id.
        Increments hit count atomically.
        """
        if not self.enabled or not self._connected or not nct_id:
            return None

        clean_id = nct_id.strip().upper()
        sql = """
        WITH hit AS (
            UPDATE public.trialgpt_lite_cache_summaries
            SET hit_count = hit_count + 1
            WHERE nct_id = %s
            RETURNING summary_data, (expires_at < NOW()) as is_expired
        )
        SELECT summary_data, is_expired FROM hit;
        """
        try:
            with self.get_connection() as conn:
                if not conn:
                    return None
                with conn.cursor() as cur:
                    cur.execute(sql, (clean_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    s_data, is_expired = row[0], row[1]
                    if is_expired and not allow_expired:
                        return None
                    conn.commit()
                    return s_data
        except Exception as e:
            logger.warning(f"PostgreSQL cache get_cached_summary failed for {nct_id}: {e}")
            return None

    def set_cached_summary(
        self,
        nct_id: str,
        trial_title: str,
        engine: str,
        summary_data: dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """
        Stores plain-English patient study summary in PostgreSQL with 30-day retention.
        """
        if not self.enabled or not self._connected or not nct_id:
            return False

        clean_id = nct_id.strip().upper()
        ttl = ttl_seconds if ttl_seconds is not None else self.study_ttl
        sql = """
        INSERT INTO public.trialgpt_lite_cache_summaries (
            nct_id, trial_title, engine, summary_data, cached_at, expires_at, hit_count
        ) VALUES (
            %s, %s, %s, %s, NOW(), NOW() + (%s * INTERVAL '1 second'), 1
        )
        ON CONFLICT (nct_id) DO UPDATE SET
            trial_title = EXCLUDED.trial_title,
            engine = EXCLUDED.engine,
            summary_data = EXCLUDED.summary_data,
            cached_at = NOW(),
            expires_at = NOW() + (%s * INTERVAL '1 second');
        """
        try:
            with self.get_connection() as conn:
                if not conn:
                    return False
                with conn.cursor() as cur:
                    cur.execute(
                        sql,
                        (
                            clean_id,
                            trial_title or "Trial Study",
                            engine or "GROQ",
                            Json(summary_data),
                            ttl,
                            ttl,
                        ),
                    )
                conn.commit()
                return True
        except Exception as e:
            logger.warning(f"PostgreSQL cache set_cached_summary failed for {nct_id}: {e}")
            return False

    # ==========================================
    # 5. Invalidation & Maintenance Operations
    # ==========================================

    def invalidate_study(self, nct_id: str) -> bool:
        """Invalidates a single trial protocol entry from PostgreSQL and all dependent matches."""
        return self.invalidate_studies([nct_id]) > 0

    def invalidate_studies(self, nct_ids: list[str]) -> int:
        """
        Dual Invalidation:
        Deletes updated study protocols from trialgpt_lite_cache_studies AND
        deletes all cached match reports that include ANY of these NCT IDs.
        """
        if not self.enabled or not self._connected or not nct_ids:
            return 0

        clean_ids = [nid.strip().upper() for nid in nct_ids if nid]
        sql_studies = "DELETE FROM public.trialgpt_lite_cache_studies WHERE nct_id = ANY(%s);"
        sql_matches = "DELETE FROM public.trialgpt_lite_cache_matches WHERE nct_ids && %s;"
        try:
            with self.get_connection() as conn:
                if not conn:
                    return 0
                with conn.cursor() as cur:
                    cur.execute(sql_studies, (clean_ids,))
                    count_studies = cur.rowcount
                    cur.execute(sql_matches, (clean_ids,))
                    count_matches = cur.rowcount
                conn.commit()
                logger.info(
                    f"Auto-Invalidated {count_studies} study protocols and {count_matches} match reports from PostgreSQL cache."
                )
                return count_studies
        except Exception as e:
            logger.warning(f"PostgreSQL cache invalidate_studies failed: {e}")
            return 0

    def invalidate_query(self, query_hash: str) -> bool:
        """Removes a specific query from the cache."""
        if not self.enabled or not self._connected:
            return False

        sql = "DELETE FROM public.trialgpt_lite_cache_queries WHERE query_hash = %s;"
        try:
            with self.get_connection() as conn:
                if not conn:
                    return False
                with conn.cursor() as cur:
                    cur.execute(sql, (query_hash,))
                    count = cur.rowcount
                conn.commit()
                return count > 0
        except Exception as e:
            logger.warning(f"PostgreSQL cache invalidate_query failed: {e}")
            return False

    def invalidate_match(self, match_hash: str) -> bool:
        """Removes a specific match report from the cache."""
        if not self.enabled or not self._connected:
            return False

        sql = "DELETE FROM public.trialgpt_lite_cache_matches WHERE match_hash = %s;"
        try:
            with self.get_connection() as conn:
                if not conn:
                    return False
                with conn.cursor() as cur:
                    cur.execute(sql, (match_hash,))
                    count = cur.rowcount
                conn.commit()
                return count > 0
        except Exception as e:
            logger.warning(f"PostgreSQL cache invalidate_match failed: {e}")
            return False

    def prune_expired(self) -> dict[str, int]:
        """Prunes expired queries, matches, and studies after their 30-day TTL."""
        if not self.enabled or not self._connected:
            return {"pruned_queries": 0, "pruned_matches": 0, "pruned_studies": 0}

        try:
            with self.get_connection() as conn:
                if not conn:
                    return {"pruned_queries": 0, "pruned_matches": 0, "pruned_studies": 0}
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM public.trialgpt_lite_cache_queries WHERE expires_at < NOW();")
                    pruned_q = cur.rowcount

                    cur.execute("DELETE FROM public.trialgpt_lite_cache_matches WHERE expires_at < NOW();")
                    pruned_m = cur.rowcount

                    cur.execute("DELETE FROM public.trialgpt_lite_cache_studies WHERE expires_at < NOW();")
                    pruned_s = cur.rowcount

                conn.commit()
                logger.info(f"Cache auto-pruned: {pruned_q} queries, {pruned_m} matches, {pruned_s} studies removed.")
                return {"pruned_queries": pruned_q, "pruned_matches": pruned_m, "pruned_studies": pruned_s}
        except Exception as e:
            logger.warning(f"PostgreSQL cache prune_expired failed: {e}")
            return {"pruned_queries": 0, "pruned_matches": 0, "pruned_studies": 0}

    def get_stats(self) -> dict[str, Any]:
        """Returns diagnostic statistics for monitoring and Swagger UI health check."""
        if not self.enabled:
            return {"status": "disabled", "engine": "PostgreSQL Cache-Aside"}
        if not self._connected:
            return {"status": "disconnected (fail-open)", "engine": "PostgreSQL Cache-Aside"}

        try:
            with self.get_connection() as conn:
                if not conn:
                    return {"status": "pool_exhausted", "engine": "PostgreSQL Cache-Aside"}
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM public.trialgpt_lite_cache_queries;")
                    q_row = cur.fetchone()
                    total_queries, query_hits = q_row[0], q_row[1]

                    cur.execute("SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM public.trialgpt_lite_cache_matches;")
                    m_row = cur.fetchone()
                    total_matches, match_hits = m_row[0], m_row[1]

                    cur.execute("SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM public.trialgpt_lite_cache_studies;")
                    s_row = cur.fetchone()
                    total_studies, study_hits = s_row[0], s_row[1]

                    return {
                        "status": "online",
                        "engine": "PostgreSQL 15 JSONB Cache-Aside",
                        "retention_policy": f"{self.retention_days} Days",
                        "cached_queries_count": total_queries,
                        "query_cache_hits": query_hits,
                        "cached_matches_count": total_matches,
                        "match_cache_hits": match_hits,
                        "cached_studies_count": total_studies,
                        "study_cache_hits": study_hits,
                        "query_ttl_seconds": self.query_ttl,
                        "study_ttl_seconds": self.study_ttl,
                        "match_ttl_seconds": self.match_ttl,
                    }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def close(self):
        """Closes all connections in the pool."""
        if self.pool:
            try:
                self.pool.closeall()
                logger.info("PostgreSQL cache connection pool closed.")
            except Exception as e:
                logger.warning(f"Error closing connection pool: {e}")


# Global Singleton instance
_cache_instance: Optional[PostgreSQLCache] = None
_init_lock = threading.Lock()


def get_pg_cache() -> PostgreSQLCache:
    """Returns singleton PostgreSQL cache instance."""
    global _cache_instance
    if _cache_instance is None:
        with _init_lock:
            if _cache_instance is None:
                _cache_instance = PostgreSQLCache()
    return _cache_instance
