"""
Create every TrialGPT-owned Postgres table on API startup.

Does not create external warehouse tables (Fasten, FHIR patient/condition,
MIMIC, MySQL). Those are owned by other services.

Each SQL statement is committed on its own so a slow GIN index or a
pgcrypto permission error cannot roll back matching_jobs.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Sequence

from utils.pg_util import pg_transaction

logger = logging.getLogger(__name__)

_MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migration"
# Index builds on a seeded corpus can exceed the default 5s request timeout.
_DDL_TIMEOUT_MS = 120000

# Apply in FK-safe order. Two files share the 003 prefix.
TRIALGPT_MIGRATION_FILES: Sequence[str] = (
    "001_compose_table.sql",
    "002_trialgpt_corpus.sql",
    "003_matching_jobs.sql",
    "003_compose_summary_block.sql",
    "004_retrieval_results.sql",
    "005_matching_results.sql",
    "006_aggregation_results.sql",
    "007_final_ranking.sql",
    "008_patient_annotations.sql",
    "009_patient_summary_validations.sql",
    "010_trialgpt_eligible_patients.sql",
    "011_trialgpt_eligible_patients_summary.sql",
    "012_trial_gpt_ehr.sql",
)

TRIALGPT_OWNED_TABLES: Sequence[str] = (
    "compose",
    "trialgpt_corpus",
    "matching_jobs",
    "compose_summary_block",
    "retrieval_results",
    "matching_results",
    "aggregation_results",
    "final_ranking",
    "patient_annotations",
    "patient_summary_validations",
    "trialgpt_eligible_patients",
    "trial_gpt_ehr",
)


def split_sql_statements(ddl: str) -> List[str]:
    """Split a migration file into executable statements. Skips -- comments."""
    cleaned_lines: List[str] = []
    for raw in ddl.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("--"):
            continue
        cleaned_lines.append(raw)
    blob = "\n".join(cleaned_lines)
    return [part.strip() for part in blob.split(";") if part.strip()]


def _statement_kind(statement: str) -> str:
    """Classify a DDL statement for skip-vs-fail policy."""
    head = statement.lstrip().split(None, 2)
    if not head:
        return "unknown"
    if len(head) >= 2 and head[0].upper() == "CREATE":
        return f"CREATE {head[1].upper()}"
    return head[0].upper()


def _is_optional_ddl(statement: str) -> bool:
    """Index/extension failures must not block table create."""
    kind = _statement_kind(statement)
    return kind in {"CREATE EXTENSION", "CREATE INDEX", "CREATE UNIQUE"}


class TrialgptSchemaBootstrap:
    """Apply idempotent TrialGPT DDL once per process."""

    def __init__(self, migration_dir: Path = _MIGRATION_DIR) -> None:
        self._migration_dir = migration_dir
        self._lock = threading.Lock()
        self._ready = False

    def reset_for_tests(self) -> None:
        """Clear the in-process cache. Tests only."""
        with self._lock:
            self._ready = False

    def ensure(self) -> None:
        """Create missing TrialGPT tables. Later calls in this process no-op."""
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            for name in TRIALGPT_MIGRATION_FILES:
                path = self._migration_dir / name
                ddl = path.read_text(encoding="utf-8")
                for statement in split_sql_statements(ddl):
                    self._apply_statement(name, statement)
            self._ready = True
            logger.info(
                "Ensured TrialGPT tables | tables=%s",
                ",".join(TRIALGPT_OWNED_TABLES),
            )

    def _apply_statement(self, file_name: str, statement: str) -> None:
        """Run one DDL statement; optional kinds are logged and skipped on error."""
        try:
            with pg_transaction() as (_, cur):
                cur.execute(f"SET statement_timeout = {_DDL_TIMEOUT_MS}")
                cur.execute(statement)
        except Exception:
            if _is_optional_ddl(statement):
                logger.warning(
                    "Optional DDL skipped | file=%s | kind=%s | sql=%s",
                    file_name,
                    _statement_kind(statement),
                    statement[:160],
                    exc_info=True,
                )
                return
            logger.exception(
                "Required DDL failed | file=%s | sql=%s",
                file_name,
                statement[:160],
            )
            raise


_BOOTSTRAP = TrialgptSchemaBootstrap()


def ensure_trialgpt_schema() -> None:
    """Startup/lazy entrypoint: create all TrialGPT-owned tables if missing."""
    _BOOTSTRAP.ensure()


def reset_trialgpt_schema_for_tests() -> None:
    """Clear the process schema cache between unit tests."""
    _BOOTSTRAP.reset_for_tests()


def schema_status() -> Dict[str, Any]:
    """Which TrialGPT tables exist in public. Does not expose row data."""
    try:
        ensure_trialgpt_schema()
    except Exception as exc:
        logger.exception("schema_status ensure failed | error=%s", exc)
    existing: List[str] = []
    try:
        with pg_transaction() as (_, cur):
            cur.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename = ANY(%s)
                ORDER BY tablename
                """,
                (list(TRIALGPT_OWNED_TABLES),),
            )
            existing = [row["tablename"] for row in (cur.fetchall() or [])]
    except Exception as exc:
        logger.exception("schema_status list failed | error=%s", exc)
        return {
            "ok": False,
            "error": "schema_lookup_failed",
            "existing": [],
            "missing": list(TRIALGPT_OWNED_TABLES),
        }
    missing = [name for name in TRIALGPT_OWNED_TABLES if name not in existing]
    return {
        "ok": not missing,
        "existing": existing,
        "missing": missing,
    }
