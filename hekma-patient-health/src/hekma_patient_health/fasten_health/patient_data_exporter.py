"""
Export all Fasten Health PostgreSQL rows for one Hekma patient_id.

Discovers every `fastenhealth_*` table, counts rows per table, and fetches
`raw_resource` (plus row metadata) only where count > 0.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)

_PATIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Tables that can contain very large binary payloads.
_LARGE_TABLES = frozenset({"fastenhealth_binary", "fastenhealth_media"})

_ROW_COLUMNS = (
    "id",
    "patient_id",
    "hekma_mail_id",
    "org_connection_id",
    "resource_id",
    "raw_resource",
    "created_at",
)


class FastenTableReader(Protocol):
    """Minimal DB surface used by the exporter (mockable in tests)."""

    def list_fastenhealth_tables(self) -> List[str]:
        ...

    def count_patient_rows(self, table_name: str, patient_id: str) -> int:
        ...

    def fetch_patient_rows(self, table_name: str, patient_id: str) -> List[Dict[str, Any]]:
        ...


@dataclass(frozen=True)
class TableExportSummary:
    """Row count for one Fasten table."""

    table_name: str
    row_count: int


@dataclass
class PatientFastenExport:
    """Full export payload for one patient."""

    patient_id: str
    exported_at: str
    patient_summary: Optional[Dict[str, Any]] = None
    tables_with_data: List[str] = field(default_factory=list)
    skipped_tables: List[str] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    data: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    def to_json_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict."""
        payload: Dict[str, Any] = {
            "patient_id": self.patient_id,
            "exported_at": self.exported_at,
            "tables_with_data": self.tables_with_data,
            "skipped_tables": self.skipped_tables,
            "summary": self.summary,
            "data": self.data,
        }
        if self.patient_summary is not None:
            payload = {
                "patient_id": self.patient_id,
                "exported_at": self.exported_at,
                "patient_summary": self.patient_summary,
                "tables_with_data": self.tables_with_data,
                "skipped_tables": self.skipped_tables,
                "summary": self.summary,
                "data": self.data,
            }
        return payload


def validate_patient_id(patient_id: str) -> str:
    """Reject malformed patient ids before they reach SQL."""
    cleaned = (patient_id or "").strip()
    if not cleaned or not _PATIENT_ID_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "patient_id must be 1-64 characters and contain only letters, digits, '_' or '-'."
        )
    return cleaned


def serialize_json_value(value: Any) -> Any:
    """Convert DB/Python values into JSON-safe primitives."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): serialize_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_json_value(item) for item in value]
    return str(value)


def serialize_fasten_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one Fasten table row for JSON output."""
    return {key: serialize_json_value(row.get(key)) for key in _ROW_COLUMNS if key in row}


class PostgresFastenTableReader:
    """Read-only access to Fasten Health tables in PostgreSQL."""

    def list_fastenhealth_tables(self) -> List[str]:
        from ..awsutils.postgresql_utils import pg_transaction

        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                r"""
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename LIKE 'fastenhealth\_%'
                ORDER BY tablename
                """
            )
            return [row["tablename"] for row in cur.fetchall()]

    def count_patient_rows(self, table_name: str, patient_id: str) -> int:
        from ..awsutils.postgresql_utils import pg_transaction

        sql = f"SELECT COUNT(*) AS row_count FROM {table_name} WHERE patient_id = %s"
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(sql, (patient_id,))
            row = cur.fetchone()
        return int(row["row_count"]) if row else 0

    def fetch_patient_rows(self, table_name: str, patient_id: str) -> List[Dict[str, Any]]:
        from ..awsutils.postgresql_utils import pg_transaction

        columns = ", ".join(_ROW_COLUMNS)
        sql = f"""
            SELECT {columns}
            FROM {table_name}
            WHERE patient_id = %s
            ORDER BY created_at ASC NULLS LAST, id ASC
        """
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(sql, (patient_id,))
            rows = cur.fetchall()
        return [dict(row) for row in rows]


class FastenHealthPatientDataExporter:
    """Export Fasten Health rows for a single Hekma patient_id."""

    def __init__(
        self,
        reader: Optional[FastenTableReader] = None,
        *,
        skip_large_tables: bool = False,
        include_trial_summary: bool = True,
        use_llm_summary: bool = True,
        include_disease_llm: bool = False,
        table_filter: Optional[Callable[[str], bool]] = None,
    ):
        self._reader = reader or PostgresFastenTableReader()
        self._skip_large_tables = skip_large_tables
        self._include_trial_summary = include_trial_summary
        self._use_llm_summary = use_llm_summary
        self._include_disease_llm = include_disease_llm
        self._table_filter = table_filter

    def export(self, patient_id: str) -> PatientFastenExport:
        """Discover tables, count rows, and fetch data where count > 0."""
        resolved_patient_id = validate_patient_id(patient_id)
        exported_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        payload = PatientFastenExport(
            patient_id=resolved_patient_id,
            exported_at=exported_at,
        )

        tables = self._reader.list_fastenhealth_tables()
        logger.info(
            "Fasten export start | patient_id=%s | tables=%d | skip_large=%s",
            resolved_patient_id,
            len(tables),
            self._skip_large_tables,
        )

        for table_name in tables:
            if self._table_filter and not self._table_filter(table_name):
                continue
            if self._skip_large_tables and table_name in _LARGE_TABLES:
                payload.skipped_tables.append(table_name)
                logger.info("Skipping large table | table=%s", table_name)
                continue

            row_count = self._reader.count_patient_rows(table_name, resolved_patient_id)
            if row_count <= 0:
                logger.debug(
                    "No rows | table=%s | patient_id=%s",
                    table_name,
                    resolved_patient_id,
                )
                continue

            rows = self._reader.fetch_patient_rows(table_name, resolved_patient_id)
            serialized_rows = [serialize_fasten_row(row) for row in rows]

            payload.summary[table_name] = len(serialized_rows)
            payload.tables_with_data.append(table_name)
            payload.data[table_name] = serialized_rows
            logger.info(
                "Exported table | table=%s | patient_id=%s | rows=%d",
                table_name,
                resolved_patient_id,
                len(serialized_rows),
            )

        if self._include_trial_summary and payload.data:
            from .trial_patient_summary import generate_trial_patient_summary

            trial_summary = generate_trial_patient_summary(
                payload.data,
                use_llm=self._use_llm_summary,
                include_disease_llm=self._include_disease_llm,
            )
            payload.patient_summary = trial_summary.to_dict()
            logger.info(
                "Trial summary generated | patient_id=%s | generated_by=%s | diseases=%d",
                resolved_patient_id,
                trial_summary.generated_by,
                len(trial_summary.disease_list),
            )

        logger.info(
            "Fasten export complete | patient_id=%s | tables_with_data=%d | total_rows=%d",
            resolved_patient_id,
            len(payload.tables_with_data),
            sum(payload.summary.values()),
        )
        return payload

    def summarize(self, patient_id: str) -> List[TableExportSummary]:
        """Return per-table row counts without fetching full payloads."""
        resolved_patient_id = validate_patient_id(patient_id)
        summaries: List[TableExportSummary] = []

        for table_name in self._reader.list_fastenhealth_tables():
            if self._table_filter and not self._table_filter(table_name):
                continue
            if self._skip_large_tables and table_name in _LARGE_TABLES:
                continue
            row_count = self._reader.count_patient_rows(table_name, resolved_patient_id)
            if row_count > 0:
                summaries.append(
                    TableExportSummary(table_name=table_name, row_count=row_count)
                )

        return summaries


def dumps_patient_export(
    payload: PatientFastenExport,
    *,
    indent: Optional[int] = 2,
) -> str:
    """Serialize export payload to a JSON string."""
    return json.dumps(payload.to_json_dict(), indent=indent, ensure_ascii=False)


def export_patient_fasten_data(
    patient_id: str,
    *,
    skip_large_tables: bool = False,
    include_trial_summary: bool = True,
    use_llm_summary: bool = True,
    include_disease_llm: bool = False,
) -> PatientFastenExport:
    """Convenience wrapper used by the CLI script."""
    return FastenHealthPatientDataExporter(
        skip_large_tables=skip_large_tables,
        include_trial_summary=include_trial_summary,
        use_llm_summary=use_llm_summary,
        include_disease_llm=include_disease_llm,
    ).export(patient_id)
