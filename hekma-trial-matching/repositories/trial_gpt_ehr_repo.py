"""Repository for trial_gpt_ehr — Fasten-derived TrialGPT patient summaries."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from repositories.trialgpt_schema_bootstrap import ensure_trialgpt_schema
from utils.pg_util import pg_transaction

logger = logging.getLogger(__name__)

TABLE_NAME = "trial_gpt_ehr"


def ensure_trial_gpt_ehr_table() -> None:
    """Create trial_gpt_ehr and every other TrialGPT-owned table if missing."""
    ensure_trialgpt_schema()


def ready_llm_flags_for_patient(mysql_patient_id: int) -> Set[bool]:
    """Return llm flags that already have a ready summary for this patient."""
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            SELECT llm
            FROM {TABLE_NAME}
            WHERE mysql_patient_id = %s
              AND summary_status = 'ready'
              AND summary_text IS NOT NULL
              AND BTRIM(summary_text) <> ''
            """,
            (mysql_patient_id,),
        )
        rows = cur.fetchall() or []
    return {bool(row["llm"]) for row in rows}


def has_ready_modes(mysql_patient_id: int, required_llm_flags: Iterable[bool]) -> bool:
    """True when every required llm mode already has a ready row."""
    required = set(required_llm_flags)
    if not required:
        return False
    return required.issubset(ready_llm_flags_for_patient(mysql_patient_id))


def _profile_for_pipeline(structured_json: Any) -> Dict[str, Any]:
    """Strip internal keys and flatten nested block dicts for RAG ingest."""
    if not isinstance(structured_json, dict):
        return {}

    out: Dict[str, Any] = {}
    for key, value in structured_json.items():
        if key in ("_generation", "_icd_diseases"):
            continue
        if isinstance(value, dict):
            parts = []
            for sk, sv in value.items():
                if sv is None:
                    continue
                text = str(sv).strip()
                if text:
                    parts.append(f"{sk}: {text}")
            out[key] = ", ".join(parts) if parts else None
        else:
            out[key] = value
    return out


def fetch_summary_text(
    *,
    subject_id: Optional[str] = None,
    mysql_patient_id: Optional[int] = None,
    llm: bool = True,
) -> Optional[str]:
    """Load ready summary_text for the preferred llm mode."""
    if not subject_id and mysql_patient_id is None:
        raise ValueError("Provide subject_id or mysql_patient_id")

    clauses = ["llm = %s", "summary_status = 'ready'", "summary_text IS NOT NULL"]
    params: List[Any] = [llm]
    if subject_id:
        clauses.append("subject_id = %s")
        params.append(subject_id)
    if mysql_patient_id is not None:
        clauses.append("mysql_patient_id = %s")
        params.append(mysql_patient_id)

    sql = f"""
        SELECT summary_text
        FROM {TABLE_NAME}
        WHERE {' AND '.join(clauses)}
        ORDER BY last_generated_at DESC NULLS LAST
        LIMIT 1
    """
    with pg_transaction() as (_, cur):
        cur.execute(sql, params)
        row = cur.fetchone()
    if not row:
        return None
    text = row.get("summary_text")
    return str(text).strip() if text else None


def fetch_disease_list(
    *,
    subject_id: Optional[str] = None,
    mysql_patient_id: Optional[int] = None,
    llm: bool = True,
) -> List[str]:
    """Load ready disease_list from trial_gpt_ehr for UI condition step."""
    if not subject_id and mysql_patient_id is None:
        raise ValueError("Provide subject_id or mysql_patient_id")

    clauses = ["llm = %s", "summary_status = 'ready'"]
    params: List[Any] = [llm]
    if subject_id:
        clauses.append("subject_id = %s")
        params.append(subject_id)
    if mysql_patient_id is not None:
        clauses.append("mysql_patient_id = %s")
        params.append(mysql_patient_id)

    sql = f"""
        SELECT disease_list
        FROM {TABLE_NAME}
        WHERE {' AND '.join(clauses)}
        ORDER BY last_generated_at DESC NULLS LAST
        LIMIT 1
    """
    with pg_transaction() as (_, cur):
        cur.execute(sql, params)
        row = cur.fetchone()
    if not row or not row.get("disease_list"):
        return []
    diseases = row["disease_list"]
    if isinstance(diseases, str):
        try:
            diseases = json.loads(diseases)
        except json.JSONDecodeError:
            return [diseases] if diseases.strip() else []
    if not isinstance(diseases, (list, tuple)):
        return []
    return [str(d).strip() for d in diseases if d and str(d).strip()]


def fetch_icd_diseases(
    *,
    subject_id: Optional[str] = None,
    mysql_patient_id: Optional[int] = None,
    llm: bool = True,
) -> List[Dict[str, Any]]:
    """Load structured_json._icd_diseases when present on a ready EHR row."""
    if not subject_id and mysql_patient_id is None:
        raise ValueError("Provide subject_id or mysql_patient_id")

    clauses = [
        "llm = %s",
        "summary_status = 'ready'",
        "structured_json IS NOT NULL",
    ]
    params: List[Any] = [llm]
    if subject_id:
        clauses.append("subject_id = %s")
        params.append(subject_id)
    if mysql_patient_id is not None:
        clauses.append("mysql_patient_id = %s")
        params.append(mysql_patient_id)

    sql = f"""
        SELECT structured_json
        FROM {TABLE_NAME}
        WHERE {' AND '.join(clauses)}
        ORDER BY last_generated_at DESC NULLS LAST
        LIMIT 1
    """
    with pg_transaction() as (_, cur):
        cur.execute(sql, params)
        row = cur.fetchone()
    if not row or not row.get("structured_json"):
        return []
    data = row["structured_json"]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return []
    if not isinstance(data, dict):
        return []
    entries = data.get("_icd_diseases")
    return entries if isinstance(entries, list) else []


def fetch_structured_profile(
    *,
    subject_id: Optional[str] = None,
    mysql_patient_id: Optional[int] = None,
    llm: bool = True,
) -> Optional[Dict[str, Any]]:
    """Load ready structured_json for RAG / matching (pipeline-normalized)."""
    if not subject_id and mysql_patient_id is None:
        raise ValueError("Provide subject_id or mysql_patient_id")

    clauses = [
        "llm = %s",
        "summary_status = 'ready'",
        "structured_json IS NOT NULL",
    ]
    params: List[Any] = [llm]
    if subject_id:
        clauses.append("subject_id = %s")
        params.append(subject_id)
    if mysql_patient_id is not None:
        clauses.append("mysql_patient_id = %s")
        params.append(mysql_patient_id)

    sql = f"""
        SELECT structured_json
        FROM {TABLE_NAME}
        WHERE {' AND '.join(clauses)}
        ORDER BY last_generated_at DESC NULLS LAST
        LIMIT 1
    """
    with pg_transaction() as (_, cur):
        cur.execute(sql, params)
        row = cur.fetchone()
    if not row or not row.get("structured_json"):
        return None
    data = row["structured_json"]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return _profile_for_pipeline(data)


def fetch_ready_subject_ids(
    *,
    llm: bool = True,
    limit: Optional[int] = None,
) -> List[str]:
    """Subject IDs with ready summary + structured_json for the given llm mode."""
    sql = f"""
        SELECT subject_id
        FROM {TABLE_NAME}
        WHERE llm = %s
          AND summary_status = 'ready'
          AND structured_json IS NOT NULL
          AND summary_text IS NOT NULL
          AND BTRIM(summary_text) <> ''
        ORDER BY subject_id
    """
    params: List[Any] = [llm]
    if limit and limit > 0:
        sql += " LIMIT %s"
        params.append(limit)
    with pg_transaction() as (_, cur):
        cur.execute(sql, tuple(params))
        rows = cur.fetchall() or []
    return [str(r["subject_id"]).strip() for r in rows if r.get("subject_id")]


def fetch_profiles_by_subject_ids(
    subject_ids: Sequence[str],
    *,
    llm: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """Return {subject_id: pipeline profile} for ready trial_gpt_ehr rows."""
    if not subject_ids:
        return {}
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            SELECT subject_id, structured_json
            FROM {TABLE_NAME}
            WHERE subject_id = ANY(%s)
              AND llm = %s
              AND summary_status = 'ready'
              AND structured_json IS NOT NULL
            """,
            (list(subject_ids), llm),
        )
        rows = cur.fetchall() or []

    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        sid = str(row.get("subject_id") or "").strip()
        profile = row.get("structured_json")
        if not sid:
            continue
        if isinstance(profile, str):
            try:
                profile = json.loads(profile)
            except json.JSONDecodeError:
                continue
        if isinstance(profile, dict):
            out[sid] = _profile_for_pipeline(profile)
    return out


def sync_subject_id(mysql_patient_id: int, subject_id: str) -> None:
    """Update subject_id on all trial_gpt_ehr rows for this MySQL patient."""
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            UPDATE {TABLE_NAME}
            SET subject_id = %s, updated_at = NOW()
            WHERE mysql_patient_id = %s
              AND subject_id IS DISTINCT FROM %s
            """,
            (subject_id, mysql_patient_id, subject_id),
        )


def upsert_trial_gpt_ehr_row(
    *,
    subject_id: str,
    mysql_patient_id: int,
    llm: bool,
    summary_text: str,
    structured_json: Dict[str, Any],
    disease_list: Sequence[str],
    has_pg_patient: bool,
    clinical_latest_ts: Optional[datetime],
    last_data_timestamp: Optional[datetime],
    summary_status: str = "ready",
) -> None:
    """Insert or update one (mysql_patient_id, llm) summary row."""
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            INSERT INTO {TABLE_NAME} (
                subject_id,
                mysql_patient_id,
                has_pg_patient,
                clinical_latest_ts,
                summary_text,
                structured_json,
                disease_list,
                last_data_timestamp,
                last_generated_at,
                summary_status,
                llm,
                identified_at,
                updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s::jsonb, %s, %s, NOW(), %s, %s, NOW(), NOW()
            )
            ON CONFLICT (mysql_patient_id, llm)
            DO UPDATE SET
                subject_id = EXCLUDED.subject_id,
                has_pg_patient = EXCLUDED.has_pg_patient,
                clinical_latest_ts = EXCLUDED.clinical_latest_ts,
                summary_text = EXCLUDED.summary_text,
                structured_json = EXCLUDED.structured_json,
                disease_list = EXCLUDED.disease_list,
                last_data_timestamp = EXCLUDED.last_data_timestamp,
                last_generated_at = NOW(),
                summary_status = EXCLUDED.summary_status,
                updated_at = NOW()
            """,
            (
                subject_id,
                mysql_patient_id,
                has_pg_patient,
                clinical_latest_ts,
                summary_text,
                json.dumps(structured_json, default=str),
                list(disease_list),
                last_data_timestamp,
                summary_status,
                llm,
            ),
        )


def fetch_ehr_status_row(
    *,
    mysql_patient_id: int,
    llm: bool,
) -> Optional[Dict[str, Any]]:
    """Load summary_status and timestamps for UI polling."""
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            SELECT summary_status, updated_at, structured_json, disease_list,
                   last_data_timestamp
            FROM {TABLE_NAME}
            WHERE mysql_patient_id = %s AND llm = %s
            """,
            (mysql_patient_id, llm),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def mark_ingesting(
    *,
    subject_id: str,
    mysql_patient_id: int,
    llm: bool,
) -> None:
    """Mark row as ingesting without clearing an existing ready summary."""
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            INSERT INTO {TABLE_NAME} (
                subject_id,
                mysql_patient_id,
                has_pg_patient,
                summary_status,
                llm,
                structured_json,
                identified_at,
                updated_at
            )
            VALUES (%s, %s, FALSE, 'ingesting', %s, '{{}}'::jsonb, NOW(), NOW())
            ON CONFLICT (mysql_patient_id, llm)
            DO UPDATE SET
                subject_id = EXCLUDED.subject_id,
                summary_status = CASE
                    WHEN {TABLE_NAME}.summary_status = 'ready' THEN {TABLE_NAME}.summary_status
                    ELSE 'ingesting'
                END,
                updated_at = NOW()
            """,
            (subject_id, mysql_patient_id, llm),
        )


def mark_failed(
    *,
    subject_id: str,
    mysql_patient_id: int,
    llm: bool,
    error_note: str,
) -> None:
    """Persist a failed status row without wiping prior ready text if present."""
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            INSERT INTO {TABLE_NAME} (
                subject_id,
                mysql_patient_id,
                has_pg_patient,
                summary_status,
                llm,
                structured_json,
                identified_at,
                updated_at
            )
            VALUES (%s, %s, FALSE, 'failed', %s, %s::jsonb, NOW(), NOW())
            ON CONFLICT (mysql_patient_id, llm)
            DO UPDATE SET
                summary_status = 'failed',
                structured_json = COALESCE({TABLE_NAME}.structured_json, '{{}}'::jsonb)
                    || EXCLUDED.structured_json,
                updated_at = NOW()
            """,
            (
                subject_id,
                mysql_patient_id,
                llm,
                json.dumps({"error": error_note[:500]}, default=str),
            ),
        )
