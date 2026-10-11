"""Idempotent PostgreSQL medication schema upgrades (startup + first-use)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from ..awsutils.postgresql_utils import pg_transaction

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# (file, tables that must NOT exist yet — None means always attempt; SQL must be idempotent)
MIGRATIONS: List[Tuple[str, Optional[List[str]]]] = [
    ("013.create_prescription.sql", ["prescriptions"]),
    ("014.create_medication.sql", ["medications"]),
    ("015.create_medication_reminders.sql", ["medication_reminders"]),
    ("016.create_medication_history.sql", ["medication_history"]),
    ("017_medication_enhancements.sql", None),
    ("018_medication_medicine_details.sql", None),
    ("019_patient_timezone.sql", None),
    ("024_prescription_content_hash.sql", None),
    ("026_medication_daily_counts.sql", None),
    ("027_medication_doctor_name.sql", None),
    ("028_medication_facility_and_prescription_date.sql", None),
    ("029_medication_hekma_id.sql", None),
    ("033_add_archived_at.sql", None),
]

_medication_schema_ready = False
# Backward-compatible alias used by older tests / callers.
_daily_count_schema_ready = False
_logger = logging.getLogger(__name__)


def _table_exists(cur, table_name: str) -> bool:
    """Return True when the named table already exists in the public schema."""
    cur.execute(
        "SELECT EXISTS ("
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s"
        ") AS exists",
        (table_name,),
    )
    row = cur.fetchone()
    return row["exists"] if isinstance(row, dict) else row[0]


def _column_exists(cur, table_name: str, column_name: str) -> bool:
    """Return True when a table column is already present."""
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table_name, column_name),
    )
    return cur.fetchone() is not None


def apply_medication_migrations(logger: Optional[logging.Logger] = None) -> None:
    """Apply all registered medication migrations; safe to re-run on every startup."""
    log = logger or _logger
    for name, guard_tables in MIGRATIONS:
        path = MIGRATIONS_DIR / name
        if not path.exists():
            log.warning("Medication migration file missing: %s", path)
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            with pg_transaction(dict_cursor=True) as (_, cur):
                if guard_tables and all(_table_exists(cur, t) for t in guard_tables):
                    log.info("Skipping %s (already applied)", name)
                    continue
                # patient.timezone needs a patient table; skip cleanly on empty DBs.
                if name == "019_patient_timezone.sql" and not _table_exists(cur, "patient"):
                    log.warning(
                        "Skipping %s (patient table missing — create core patient schema first)",
                        name,
                    )
                    continue
                log.info("Applying medication migration %s", name)
                cur.execute(sql)
                log.info("Applied medication migration %s", name)
        except Exception:
            # Continue so one optional migration (e.g. timezone) cannot block doctor_name.
            log.warning(
                "Medication migration %s failed (continuing with remaining files)",
                name,
                exc_info=True,
            )


def ensure_medication_schema() -> None:
    """
    Ensure full medication schema before any meds API use.

    Covers create/read/update so QA/empty DBs self-heal even when startup
    migration was skipped or failed non-fatally.
    """
    global _medication_schema_ready, _daily_count_schema_ready
    if _medication_schema_ready:
        return
    apply_medication_migrations()
    _medication_schema_ready = True
    _daily_count_schema_ready = True


def ensure_medication_daily_count_schema() -> None:
    """Backward-compatible entry point; applies the full medication migration set."""
    ensure_medication_schema()
