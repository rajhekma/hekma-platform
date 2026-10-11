"""Idempotent PostgreSQL schema setup for the standard lab catalog."""

import logging
from pathlib import Path
from typing import Optional

from ..awsutils.postgresql_utils import pg_transaction


MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "029_create_standard_lab_catalog.sql"
)
_logger = logging.getLogger(__name__)


def apply_lab_catalog_migration(
    logger: Optional[logging.Logger] = None,
) -> None:
    log = logger or _logger
    if not MIGRATION_PATH.exists():
        log.warning("Lab catalog migration file missing: %s", MIGRATION_PATH)
        return

    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
    log.info("Ensured standard lab catalog schema and seed data")
