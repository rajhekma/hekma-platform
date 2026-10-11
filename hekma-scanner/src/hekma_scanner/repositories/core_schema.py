"""Idempotent PostgreSQL core schema upgrades for fresh / new-region databases.

Applies EHR + Fasten + EHR-summary DDL that was historically applied by hand.
Medication (013+) and lab catalog (029) stay on their own startup runners.
MySQL-only files (009, 010, 024_mysql, 025_mysql) are intentionally excluded.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from ..awsutils.postgresql_utils import pg_transaction

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# Ordered Postgres DDL for empty-region bootstrap. All files must be idempotent.
CORE_MIGRATIONS: List[str] = [
    "001_create_healthkit.sql",
    "002_create_condition.sql",
    "003_create_allergy.sql",
    "004_create_medication_order.sql",
    "005_create_immunization.sql",
    "006_create_observation.sql",
    "007_create_procedure.sql",
    "008_create_patient.sql",
    "011_create_fasten_controller.sql",
    "020_create_ehr_summary_cache.sql",
    "021_add_slim_json_to_ehr_summary_cache.sql",
    "022_fasten_controller_tefca_columns.sql",
    "023_fastenhealth_org_connection_id.sql",
    "031_create_account_deletion_archive.sql",
    "032_hekma_fhir_identity.sql",
    "033_add_archived_at.sql",
    "034_create_fastenhealth_bmi_data.sql",
]

_logger = logging.getLogger(__name__)


def apply_core_migrations(logger: Optional[logging.Logger] = None) -> None:
    """Apply core Postgres migrations; safe to re-run on every startup."""
    log = logger or _logger
    for name in CORE_MIGRATIONS:
        path = MIGRATIONS_DIR / name
        if not path.exists():
            log.warning("Core migration file missing: %s", path)
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            with pg_transaction(dict_cursor=True) as (_, cur):
                # 022 needs fasten_controller; skip cleanly if create failed earlier.
                if name == "022_fasten_controller_tefca_columns.sql":
                    cur.execute(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name = 'fasten_controller'"
                        ") AS exists"
                    )
                    row = cur.fetchone()
                    exists = row["exists"] if isinstance(row, dict) else row[0]
                    if not exists:
                        log.warning(
                            "Skipping %s (fasten_controller missing)",
                            name,
                        )
                        continue
                # 021 needs ehr_summary_cache.
                if name == "021_add_slim_json_to_ehr_summary_cache.sql":
                    cur.execute(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name = 'ehr_summary_cache'"
                        ") AS exists"
                    )
                    row = cur.fetchone()
                    exists = row["exists"] if isinstance(row, dict) else row[0]
                    if not exists:
                        log.warning(
                            "Skipping %s (ehr_summary_cache missing)",
                            name,
                        )
                        continue
                log.info("Applying core migration %s", name)
                cur.execute(sql)
                log.info("Applied core migration %s", name)
        except Exception:
            log.warning(
                "Core migration %s failed (continuing with remaining files)",
                name,
                exc_info=True,
            )
