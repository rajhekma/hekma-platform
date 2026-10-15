"""Read-only access to fastenhealth_* tables for trial_gpt_ehr ingest."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils.pg_util import pg_transaction

logger = logging.getLogger(__name__)

_LARGE_TABLES = frozenset({"fastenhealth_binary", "fastenhealth_media"})
_SAFE_TABLE_RE = re.compile(r"^fastenhealth_[a-z0-9_]+$")
HEKMA_CTMS_PAYLOAD_URL = "https://hekma.ai/fhir/StructureDefinition/ctms-payload"
_SKIP_VERIFICATION_STATUS = frozenset({"entered-in-error"})

_ROW_COLUMNS = (
    "id",
    "patient_id",
    "hekma_mail_id",
    "org_connection_id",
    "resource_id",
    "raw_resource",
    "created_at",
)


def list_fastenhealth_tables(*, skip_large_tables: bool = True) -> List[str]:
    """Discover fastenhealth_* tables currently present in public schema."""
    with pg_transaction() as (_, cur):
        cur.execute(
            r"""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename LIKE 'fastenhealth\_%'
            ORDER BY tablename
            """
        )
        tables = [row["tablename"] for row in (cur.fetchall() or [])]
    if skip_large_tables:
        tables = [t for t in tables if t not in _LARGE_TABLES]
    return tables


def _as_utc_naive(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _parse_raw_resource(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _coding_code(resource: Dict[str, Any], field: str) -> str:
    block = resource.get(field) or {}
    if not isinstance(block, dict):
        return ""
    for coding in block.get("coding") or []:
        if isinstance(coding, dict) and coding.get("code"):
            return str(coding["code"]).strip().lower()
    return str(block.get("text") or "").strip().lower()


def _read_ctms_payload(resource: Dict[str, Any]) -> Dict[str, Any]:
    """Original plus/scan fields stamped on FHIR (conditionName, etc.)."""
    for item in resource.get("extension") or []:
        if not isinstance(item, dict) or item.get("url") != HEKMA_CTMS_PAYLOAD_URL:
            continue
        try:
            parsed = json.loads(item.get("valueString") or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def extract_condition_display_name(resource: Dict[str, Any]) -> Optional[str]:
    """
    Disease label from a FHIR Condition.

    Manual/scan rows often only have conditionName on the Hekma ctms-payload
    extension. EHR rows usually have code.text / code.coding.display.
    """
    if not isinstance(resource, dict):
        return None
    payload = _read_ctms_payload(resource)
    for key in ("conditionName", "condition_name", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = payload.get("extractedData") or payload.get("extracted_data")
    if isinstance(nested, dict):
        for key in ("conditionName", "condition_name", "name"):
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    code = resource.get("code") or {}
    if isinstance(code, dict):
        text = code.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        for coding in code.get("coding") or []:
            if not isinstance(coding, dict):
                continue
            display = coding.get("display")
            if isinstance(display, str) and display.strip():
                return display.strip()
    return None


def extract_condition_icd10(resource: Dict[str, Any]) -> Optional[str]:
    code_block = resource.get("code") or {}
    if not isinstance(code_block, dict):
        return None
    for coding in code_block.get("coding") or []:
        if not isinstance(coding, dict):
            continue
        system = str(coding.get("system") or "").lower()
        if "icd-10" not in system and "icd10" not in system:
            continue
        code = str(coding.get("code") or "").strip()
        if code:
            return code.upper()
    return None


def get_fasten_patient_created_at(mysql_patient_id: str) -> Optional[datetime]:
    """Earliest fastenhealth_patient.created_at for this Hekma patient_id."""
    with pg_transaction() as (_, cur):
        cur.execute(
            """
            SELECT MIN(created_at) AS created_at
            FROM fastenhealth_patient
            WHERE patient_id = %s
            """,
            (str(mysql_patient_id),),
        )
        row = cur.fetchone()
    if not row or not row.get("created_at"):
        return None
    return row["created_at"]


def has_clinical_data(mysql_patient_id: str) -> bool:
    """
    True when any fastenhealth_* clinical row exists for the patient.

    EHR, manual plus, and document scan all land in these tables. A
    fastenhealth_patient row is not required (manual/scan often omit it).
    Diagnoses are checked first — that is what Trial Match needs.
    """
    patient_id = str(mysql_patient_id)
    tables = [
        t
        for t in list_fastenhealth_tables(skip_large_tables=True)
        if _SAFE_TABLE_RE.match(t)
    ]
    tables.sort(key=lambda name: 0 if name == "fastenhealth_condition" else 1)
    with pg_transaction() as (_, cur):
        for table_name in tables:
            cur.execute(
                f"SELECT 1 FROM {table_name} WHERE patient_id::text = %s LIMIT 1",
                (patient_id,),
            )
            if cur.fetchone():
                return True
    return False


def get_fasten_clinical_latest_ts(mysql_patient_id: str) -> Optional[datetime]:
    """Latest created_at across all fastenhealth_* clinical tables for the patient."""
    tables = list_fastenhealth_tables(skip_large_tables=True)
    patient_id = str(mysql_patient_id)
    latest: Optional[datetime] = None
    with pg_transaction() as (_, cur):
        for table_name in tables:
            if not _SAFE_TABLE_RE.match(table_name):
                continue
            cur.execute(
                f"""
                SELECT MAX(created_at) AS latest_ts
                FROM {table_name}
                WHERE patient_id::text = %s
                """,
                (patient_id,),
            )
            row = cur.fetchone()
            ts = _as_utc_naive(row["latest_ts"] if row else None)
            if ts is not None and (latest is None or ts > latest):
                latest = ts
    return latest


def clinical_newer_than(
    mysql_patient_id: str,
    last_data_timestamp: Any,
) -> bool:
    """True when Fasten clinical rows were written after last_data_timestamp."""
    last = _as_utc_naive(last_data_timestamp)
    if last is None:
        return False
    latest = get_fasten_clinical_latest_ts(str(mysql_patient_id))
    latest = _as_utc_naive(latest)
    if latest is None:
        return False
    return latest > last


def fetch_condition_diseases(
    mysql_patient_id: str,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Disease names (and ICD when present) from fastenhealth_condition.

    Includes every source: ehr, manual, and scan. Skips entered-in-error.
    Queries the condition table directly so a missing fastenhealth_patient
    row cannot hide plus-button or scan diagnoses.
    """
    icd_entries: List[Dict[str, Any]] = []
    seen: set[str] = set()
    sql = """
        SELECT raw_resource
        FROM fastenhealth_condition
        WHERE patient_id::text = %s
        ORDER BY created_at ASC NULLS LAST, id ASC
    """
    try:
        with pg_transaction() as (_, cur):
            cur.execute("SET LOCAL statement_timeout = 30000")
            cur.execute(sql, (str(mysql_patient_id),))
            rows = cur.fetchall() or []
    except Exception:
        logger.exception(
            "fastenhealth_condition disease lookup failed | patient_id=%s",
            mysql_patient_id,
        )
        return [], []

    for row in rows:
        resource = _parse_raw_resource(dict(row).get("raw_resource"))
        if _coding_code(resource, "verificationStatus") in _SKIP_VERIFICATION_STATUS:
            continue
        name = extract_condition_display_name(resource)
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        icd10 = extract_condition_icd10(resource)
        icd_entries.append(
            {
                "official_name": name,
                "icd10_code": icd10,
                "input": name,
            }
        )

    from services.trial_condition_filter import filter_fasten_condition_entries

    return filter_fasten_condition_entries(icd_entries)


def count_patient_rows(table_name: str, mysql_patient_id: str) -> int:
    """Count rows for patient_id in one Fasten table (table from pg_tables)."""
    sql = f"SELECT COUNT(*) AS row_count FROM {table_name} WHERE patient_id::text = %s"
    with pg_transaction() as (_, cur):
        cur.execute(sql, (str(mysql_patient_id),))
        row = cur.fetchone()
    return int(row["row_count"]) if row else 0


def fetch_patient_rows(table_name: str, mysql_patient_id: str) -> List[Dict[str, Any]]:
    """Fetch all Fasten rows for a patient from one table."""
    columns = ", ".join(_ROW_COLUMNS)
    sql = f"""
        SELECT {columns}
        FROM {table_name}
        WHERE patient_id::text = %s
        ORDER BY created_at ASC NULLS LAST, id ASC
    """
    with pg_transaction() as (_, cur):
        # Fasten tables can be large; keep timeout local to this query.
        cur.execute("SET LOCAL statement_timeout = 30000")
        cur.execute(sql, (str(mysql_patient_id),))
        rows = cur.fetchall() or []
    return [dict(row) for row in rows]


def export_fasten_patient_data(
    mysql_patient_id: str,
    *,
    skip_large_tables: bool = True,
    tables: Optional[Sequence[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Build {table_name: [rows]} for every Fasten table with count > 0.

    Table names come from pg_tables (or caller-provided list), never raw user input.
    """
    table_list = list(tables) if tables is not None else list_fastenhealth_tables(
        skip_large_tables=skip_large_tables
    )
    payload: Dict[str, List[Dict[str, Any]]] = {}
    for table_name in table_list:
        if skip_large_tables and table_name in _LARGE_TABLES:
            continue
        row_count = count_patient_rows(table_name, mysql_patient_id)
        if row_count <= 0:
            continue
        rows = fetch_patient_rows(table_name, mysql_patient_id)
        if rows:
            payload[table_name] = rows
            logger.info(
                "Fasten export table | patient_id=%s | table=%s | rows=%d",
                mysql_patient_id,
                table_name,
                len(rows),
            )
    return payload
