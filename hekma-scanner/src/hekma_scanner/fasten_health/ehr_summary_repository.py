"""
Repository for EHR summary — reads from all fastenhealth_* tables.

All queries are read-only.  Original records are never mutated.

Log levels
----------
INFO  — patient lookup results, table discovery count, per-table record count
DEBUG — SQL execution timing, skipped tables, zero-row results
WARNING — statement timeouts or query errors (graceful fallback — empty list)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Set

from psycopg2 import Error as PsycopgError

from ..awsutils.postgresql_utils import pg_transaction

logger = logging.getLogger(__name__)

# Tables skipped entirely — administrative or contain raw binary blobs.
_SKIP_TABLES = {
    "fastenhealth_patient",
    "fastenhealth_binary",   # raw base64 blobs — too large, not clinical text
    "fastenhealth_media",    # images / attachments
}

# Statement timeout (ms) for per-table data fetch.
_QUERY_TIMEOUT_MS = 30_000

# Maximum records per table (most-recent preferred).
MAX_RECORDS_PER_TABLE = int(os.getenv("EHR_SUMMARY_MAX_RECORDS_PER_TABLE", "25"))

# Observation rows are multi-domain (labs, vitals, social history, screeners)
# and are summarized entirely via rule-based logic (0 OpenAI tokens).
# A higher limit prevents repetitive vitals (e.g. BP) from squeezing out labs,
# weights, temperatures, and other observations.
MAX_OBSERVATION_RECORDS_PER_TABLE = int(
    os.getenv("EHR_SUMMARY_MAX_OBSERVATION_RECORDS", "500")
)

# Manual + scan rows are cheap (rule-based summaries) and must not be squeezed
# out by the EHR cap of 25 mixed rows per table.
MAX_HEKMA_RECORDS_PER_TABLE = int(os.getenv("EHR_SUMMARY_MAX_HEKMA_RECORDS_PER_TABLE", "100"))

_HEKMA_SOURCES = ("manual", "scan")
_HEKMA_ORG_CONNECTION_IDS = ("hekma:manual", "hekma:scan")


def _is_missing_relation_error(exc: BaseException) -> bool:
    """True when Postgres reports a missing relation (undefined_table)."""
    if getattr(exc, "pgcode", None) == "42P01":
        return True
    message = str(exc).lower()
    return "does not exist" in message and "relation" in message


def get_patient_by_id(patient_id: str) -> Optional[Dict[str, Any]]:
    """Return fastenhealth_patient row for patient_id, or None if missing/unprovisioned."""
    logger.debug("DB lookup by patient_id | patient_id=%s", patient_id)
    t0 = time.perf_counter()
    try:
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                """
                SELECT id, patient_id, hekma_mail_id, raw_resource, created_at
                FROM fastenhealth_patient
                WHERE patient_id = %s
                  AND archived_at IS NULL
                LIMIT 1
                """,
                (patient_id,),
            )
            row = cur.fetchone()
    except PsycopgError as exc:
        elapsed = time.perf_counter() - t0
        if _is_missing_relation_error(exc):
            logger.warning(
                "fastenhealth_patient table missing | patient_id=%s | elapsed=%.3fs | error=%s",
                patient_id,
                elapsed,
                exc,
            )
            return None
        raise

    elapsed = time.perf_counter() - t0
    if row:
        logger.debug(
            "Patient found by patient_id | patient_id=%s | elapsed=%.3fs",
            patient_id, elapsed,
        )
    else:
        logger.debug(
            "Patient NOT found by patient_id | patient_id=%s | elapsed=%.3fs",
            patient_id, elapsed,
        )
    return dict(row) if row else None


def get_patient_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Return fastenhealth_patient row for Hekma email, or None if missing/unprovisioned."""
    logger.debug("DB lookup by email | email=%s", email)
    t0 = time.perf_counter()
    try:
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                """
                SELECT id, patient_id, hekma_mail_id, raw_resource, created_at
                FROM fastenhealth_patient
                WHERE LOWER(hekma_mail_id) = LOWER(%s)
                  AND archived_at IS NULL
                LIMIT 1
                """,
                (email,),
            )
            row = cur.fetchone()
    except PsycopgError as exc:
        elapsed = time.perf_counter() - t0
        if _is_missing_relation_error(exc):
            logger.warning(
                "fastenhealth_patient table missing | email=%s | elapsed=%.3fs | error=%s",
                email,
                elapsed,
                exc,
            )
            return None
        raise

    elapsed = time.perf_counter() - t0
    if row:
        logger.debug(
            "Patient found by email | email=%s | patient_id=%s | elapsed=%.3fs",
            email, row["patient_id"], elapsed,
        )
    else:
        logger.debug(
            "Patient NOT found by email | email=%s | elapsed=%.3fs",
            email, elapsed,
        )
    return dict(row) if row else None


def get_ctms_patient_identity(
    patient_id: Optional[str] = None, email: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Best-effort MySQL Patient row for PDF/header name when Fasten is absent."""
    patient_id = (patient_id or "").strip() or None
    email = (email or "").strip() or None
    if not patient_id and not email:
        return None
    try:
        from ..awsutils.mysql_db_connection import mysql_connection
    except Exception:
        return None
    clauses: list = []
    params: list = []
    if patient_id:
        clauses.append("CAST(patientId AS CHAR) = %s")
        params.append(str(patient_id))
    elif email:
        clauses.append("LOWER(TRIM(email)) = LOWER(TRIM(%s))")
        params.append(email)
    else:
        return None
    try:
        with mysql_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT patientId, email, firstName, lastName, status "
                "FROM Patient WHERE " + " AND ".join(clauses) + " "
                "AND UPPER(COALESCE(status, '')) NOT IN ('DELETED', 'ARCHIVED') "
                "LIMIT 1",
                tuple(params),
            )
            row = cur.fetchone()
    except Exception as exc:
        logger.warning(
            "CTMS patient lookup failed | patient_id=%s | email=%s | error=%s",
            patient_id, email, exc,
        )
        return None
    return dict(row) if row else None


def stub_patient_row(
    patient_id: str,
    *,
    email: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    gender: Optional[str] = None,
    birth_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Identity row so summaries work without a Fasten EHR connection."""
    given = [first_name] if first_name else []
    raw: Dict[str, Any] = {}
    if given or last_name:
        raw["name"] = [{"family": last_name or "", "given": given}]
    if gender:
        raw["gender"] = str(gender).lower()
    if birth_date:
        raw["birthDate"] = str(birth_date)[:10]
    return {
        "id": None,
        "patient_id": str(patient_id),
        "hekma_mail_id": email,
        "raw_resource": raw,
        "created_at": None,
    }


_TABLE_DISCOVERY_SQL = r"""
    SELECT tablename
    FROM pg_tables
    WHERE schemaname = 'public'
      AND tablename LIKE 'fastenhealth\_%'
    ORDER BY tablename
"""


def _select_tables(cur) -> List[str]:
    """Eligible fastenhealth_* table names, reusing an already-open cursor."""
    cur.execute(_TABLE_DISCOVERY_SQL)
    return [
        row["tablename"]
        for row in cur.fetchall()
        if row["tablename"] not in _SKIP_TABLES
    ]


def list_fastenhealth_tables() -> List[str]:
    """
    Return all fastenhealth_* table names that currently exist in the DB,
    excluding administrative and binary tables.
    """
    logger.debug("Querying pg_tables for fastenhealth_* tables")
    t0 = time.perf_counter()
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(_TABLE_DISCOVERY_SQL)
        rows = cur.fetchall()

    all_tables = [row["tablename"] for row in rows]
    skipped = [t for t in all_tables if t in _SKIP_TABLES]
    tables = [t for t in all_tables if t not in _SKIP_TABLES]
    elapsed = time.perf_counter() - t0

    logger.info(
        "Tables discovered | total=%d | eligible=%d | skipped=%d | skipped_tables=%s | elapsed=%.3fs",
        len(all_tables), len(tables), len(skipped), skipped, elapsed,
    )
    logger.debug("Eligible tables | %s", tables)
    return tables


def get_patient_records_from_table(
    patient_id: str, table_name: str
) -> List[Dict[str, Any]]:
    """
    Fetch the most-recent MAX_RECORDS_PER_TABLE rows for *patient_id* from
    *table_name*.  Returns a list of dicts; returns [] on error.

    Table name is sourced from pg_tables (not user input) so string
    interpolation is safe.
    """
    limit = (
        MAX_OBSERVATION_RECORDS_PER_TABLE
        if table_name == "fastenhealth_observation"
        else MAX_RECORDS_PER_TABLE
    )
    sql = f"""
        SELECT id, patient_id, hekma_mail_id, resource_id, raw_resource, created_at
        FROM (
            SELECT id, patient_id, hekma_mail_id, resource_id, raw_resource, created_at
            FROM {table_name}
            WHERE patient_id = %s
              AND archived_at IS NULL
            ORDER BY created_at DESC
            LIMIT {limit}
        ) recent
        ORDER BY created_at ASC
    """
    logger.debug(
        "DB fetch | table=%s | patient_id=%s | limit=%d | timeout_ms=%d",
        table_name, patient_id, limit, _QUERY_TIMEOUT_MS,
    )
    t0 = time.perf_counter()
    try:
        with pg_transaction(dict_cursor=True) as (conn, cur):
            cur.execute(f"SET LOCAL statement_timeout = {_QUERY_TIMEOUT_MS}")
            cur.execute(sql, (patient_id,))
            rows = cur.fetchall()

        elapsed = time.perf_counter() - t0
        count = len(rows)

        if count == 0:
            logger.debug(
                "DB fetch empty | table=%s | patient_id=%s | elapsed=%.3fs",
                table_name, patient_id, elapsed,
            )
        else:
            logger.info(
                "DB fetch OK | table=%s | patient_id=%s | rows=%d | elapsed=%.3fs",
                table_name, patient_id, count, elapsed,
            )
            if count == limit:
                logger.debug(
                    "DB fetch hit limit | table=%s | limit=%d — older records excluded",
                    table_name, limit,
                )

        return [dict(r) for r in rows]

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        logger.warning(
            "DB fetch FAILED | table=%s | patient_id=%s | elapsed=%.3fs | error=%s",
            table_name, patient_id, elapsed, exc,
        )
        return []


def get_hekma_source_records_from_table(
    patient_id: str, table_name: str
) -> List[Dict[str, Any]]:
    """
    Fetch manual/scan FHIR rows for *patient_id* from *table_name*.

    These are Hekma-authored (plus button, REST, document scan), not EHR poll.
    Failures return [] so a missing column on one table cannot block overlay.
    """
    sql_with_source = f"""
        SELECT id, patient_id, hekma_mail_id, resource_id, raw_resource, created_at
        FROM {table_name}
        WHERE patient_id = %s
          AND archived_at IS NULL
          AND (
            COALESCE(source, '') IN %s
            OR org_connection_id IN %s
          )
        ORDER BY created_at DESC
        LIMIT {MAX_HEKMA_RECORDS_PER_TABLE}
    """
    sql_org_only = f"""
        SELECT id, patient_id, hekma_mail_id, resource_id, raw_resource, created_at
        FROM {table_name}
        WHERE patient_id = %s
          AND archived_at IS NULL
          AND org_connection_id IN %s
        ORDER BY created_at DESC
        LIMIT {MAX_HEKMA_RECORDS_PER_TABLE}
    """
    t0 = time.perf_counter()
    try:
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(f"SET LOCAL statement_timeout = {_QUERY_TIMEOUT_MS}")
            cur.execute(
                sql_with_source,
                (patient_id, _HEKMA_SOURCES, _HEKMA_ORG_CONNECTION_IDS),
            )
            rows = cur.fetchall()
        logger.debug(
            "Hekma-source fetch | table=%s | patient_id=%s | rows=%d | elapsed=%.3fs",
            table_name, patient_id, len(rows), time.perf_counter() - t0,
        )
        return [dict(r) for r in rows]
    except Exception as source_exc:
        logger.debug(
            "Hekma-source fetch retry without source column | table=%s | error=%s",
            table_name, source_exc,
        )
    try:
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(f"SET LOCAL statement_timeout = {_QUERY_TIMEOUT_MS}")
            cur.execute(sql_org_only, (patient_id, _HEKMA_ORG_CONNECTION_IDS))
            rows = cur.fetchall()
        logger.debug(
            "Hekma-source fetch (org_connection_id) | table=%s | patient_id=%s | "
            "rows=%d | elapsed=%.3fs",
            table_name, patient_id, len(rows), time.perf_counter() - t0,
        )
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning(
            "Hekma-source fetch FAILED | table=%s | patient_id=%s | elapsed=%.3fs | error=%s",
            table_name, patient_id, time.perf_counter() - t0, exc,
        )
        return []


def _tables_with_source_column(cur, tables: List[str]) -> Set[str]:
    """Subset of *tables* carrying the `source` column added by migration 032."""
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND column_name = 'source'
          AND table_name = ANY(%s)
        """,
        (list(tables),),
    )
    return {row["table_name"] for row in cur.fetchall()}


def _batch_hekma_source_records(
    cur, patient_id: str, tables: List[str]
) -> Dict[str, List[Dict[str, Any]]]:
    """UNION ALL the per-table manual/scan reads into one statement."""
    with_source = _tables_with_source_column(cur, tables)

    branches: List[str] = []
    params: List[Any] = []
    for table in tables:
        if table in with_source:
            predicate = "(COALESCE(source, '') IN %s OR org_connection_id IN %s)"
            predicate_params: tuple = (_HEKMA_SOURCES, _HEKMA_ORG_CONNECTION_IDS)
        else:
            predicate = "org_connection_id IN %s"
            predicate_params = (_HEKMA_ORG_CONNECTION_IDS,)
        branches.append(
            f"""(
                SELECT %s::text AS source_table, id, patient_id, hekma_mail_id,
                       resource_id, raw_resource, created_at
                FROM {table}
                WHERE patient_id = %s AND archived_at IS NULL AND {predicate}
                ORDER BY created_at DESC
                LIMIT {MAX_HEKMA_RECORDS_PER_TABLE}
            )"""
        )
        params.append(table)
        params.append(patient_id)
        params.extend(predicate_params)

    sql = (
        "SELECT * FROM (\n"
        + "\nUNION ALL\n".join(branches)
        + "\n) merged ORDER BY source_table, created_at DESC"
    )
    cur.execute(sql, tuple(params))

    result: Dict[str, List[Dict[str, Any]]] = {}
    for raw_row in cur.fetchall():
        row = dict(raw_row)
        result.setdefault(row.pop("source_table"), []).append(row)
    return result


def _fetch_hekma_source_records_per_table(
    patient_id: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """One transaction per table — fallback only; see fetch_hekma_source_records."""
    result: Dict[str, List[Dict[str, Any]]] = {}
    for table in list_fastenhealth_tables():
        rows = get_hekma_source_records_from_table(patient_id, table)
        if rows:
            result[table] = rows
    return result


def fetch_hekma_source_records(patient_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return {table_name: [rows]} for every fastenhealth_* table with manual/scan data.

    Issued as a single UNION ALL statement.  This runs on the EHR summary
    cache-hit path, so one transaction per table meant a pool checkout and a
    round trip per FHIR resource type on every request.
    """
    t0 = time.perf_counter()
    try:
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(f"SET LOCAL statement_timeout = {_QUERY_TIMEOUT_MS}")
            tables = _select_tables(cur)
            if not tables:
                return {}
            result = _batch_hekma_source_records(cur, patient_id, tables)
    except Exception as exc:
        logger.warning(
            "Hekma-source batch fetch failed, retrying per table | patient_id=%s | error=%s",
            patient_id, exc,
        )
        result = _fetch_hekma_source_records_per_table(patient_id)

    logger.info(
        "Hekma-source fetch complete | patient_id=%s | tables_with_data=%d | "
        "total_rows=%d | elapsed=%.3fs",
        patient_id, len(result), sum(len(v) for v in result.values()),
        time.perf_counter() - t0,
    )
    return result


def fetch_active_adherence_medications(patient_id: str) -> List[Dict[str, Any]]:
    """
    Active rows from the adherence ``medications`` table for EHR summary overlay.

    Used when app meds are not yet projected into fastenhealth_medicationrequest
    (dual-write pending or backfill not run).
    """
    sql = """
        SELECT
            m.id,
            m.patient_id,
            m.name,
            m.dosage,
            m.how_much_to_take,
            m.strength,
            m.medication_type,
            m.frequency,
            m.start_date,
            m.end_date,
            m.instructions,
            m.status,
            m.notes,
            m.prescription_id,
            m.hekma_id,
            m.doctor_name,
            m.facility_name,
            m.prescription_date,
            m.created_at
        FROM medications m
        WHERE m.patient_id = %s
          AND m.archived_at IS NULL
          AND LOWER(COALESCE(m.status, '')) = 'active'
        ORDER BY m.created_at DESC
        LIMIT 100
    """
    t0 = time.perf_counter()
    try:
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(f"SET LOCAL statement_timeout = {_QUERY_TIMEOUT_MS}")
            cur.execute(sql, (str(patient_id),))
            rows = [dict(r) for r in cur.fetchall()]
        logger.debug(
            "Adherence medications fetch | patient_id=%s | rows=%d | elapsed=%.3fs",
            patient_id,
            len(rows),
            time.perf_counter() - t0,
        )
        return rows
    except Exception as exc:
        logger.warning(
            "Adherence medications fetch FAILED | patient_id=%s | error=%s",
            patient_id,
            exc,
        )
        return []


def fetch_all_patient_records(patient_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return {table_name: [rows]} for every eligible fastenhealth_* table
    that has records for the patient.
    """
    tables = list_fastenhealth_tables()
    logger.info("fetch_all_patient_records | patient_id=%s | tables=%d", patient_id, len(tables))
    result: Dict[str, List[Dict[str, Any]]] = {}
    for table in tables:
        rows = get_patient_records_from_table(patient_id, table)
        if rows:
            result[table] = rows
    logger.info(
        "fetch_all_patient_records complete | patient_id=%s | tables_with_data=%d | total_rows=%d",
        patient_id, len(result), sum(len(v) for v in result.values()),
    )
    return result
