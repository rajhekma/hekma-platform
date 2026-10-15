#!/usr/bin/env python3
"""
Copy trialgpt_corpus schema + all rows from Dev Postgres to QA Postgres.

Does not use pg_dump. Reads Dev and writes QA over psycopg2.

Usage (from repo root):
  # preview counts / columns
  python scripts/migrate_trialgpt_corpus_dev_to_qa.py

  # create table on QA and copy all rows (truncates QA table first)
  python scripts/migrate_trialgpt_corpus_dev_to_qa.py --apply --truncate

Env (required):
  DEV_PG_HOST DEV_PG_DB DEV_PG_USER DEV_PG_PASSWORD  [DEV_PG_PORT=5432]
  QA_PG_HOST  QA_PG_DB  QA_PG_USER  QA_PG_PASSWORD   [QA_PG_PORT=5432]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

import psycopg2
from psycopg2.extras import Json, execute_values

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

logger = logging.getLogger("migrate_trialgpt_corpus")

TABLE_NAME = "trialgpt_corpus"
_DDL_PATH = ROOT / "migration" / "002_trialgpt_corpus.sql"
_ALLOWED_TABLES = frozenset({TABLE_NAME})
DEFAULT_BATCH_SIZE = 200


@dataclass(frozen=True)
class PgTarget:
    """Postgres connection settings for one environment."""

    label: str
    host: str
    port: int
    dbname: str
    user: str
    password: str

    def fingerprint(self) -> tuple[str, int, str]:
        """Host/port/db identity used to block Dev==QA accidents."""
        return (self.host, self.port, self.dbname)

    def safe_dsn(self) -> str:
        """Loggable DSN without password."""
        return f"{self.user}@{self.host}:{self.port}/{self.dbname}"


class TrialgptCorpusMigrator:
    """Create trialgpt_corpus on QA (if needed) and copy every Dev row."""

    def __init__(
        self,
        source: PgTarget,
        target: PgTarget,
        *,
        table: str = TABLE_NAME,
        batch_size: int = DEFAULT_BATCH_SIZE,
        allow_same_db: bool = False,
    ) -> None:
        if table not in _ALLOWED_TABLES:
            raise ValueError(f"Refusing unknown table {table!r}")
        if source.fingerprint() == target.fingerprint() and not allow_same_db:
            raise ValueError(
                "Dev and QA point at the same host/db. "
                "Pass --allow-same-db only if that is intentional."
            )
        self.source = source
        self.target = target
        self.table = table
        self.batch_size = max(1, batch_size)

    def connect(self, target: PgTarget):
        """Open a short-lived connection; caller must close it."""
        return psycopg2.connect(
            host=target.host,
            port=target.port,
            dbname=target.dbname,
            user=target.user,
            password=target.password,
            connect_timeout=15,
            application_name="trialgpt-corpus-migrator",
        )

    def ensure_schema(self) -> None:
        """Apply repo DDL, then add any extra Dev columns missing on QA."""
        ddl = _DDL_PATH.read_text(encoding="utf-8")
        with self.connect(self.target) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(ddl)
            extra = self._dev_columns_missing_on_qa()
            if extra:
                with conn.cursor() as cur:
                    for col in extra:
                        ident = _quote_ident(col["column_name"])
                        typ = col["udt_type"]
                        cur.execute(
                            f"ALTER TABLE {_quote_ident(self.table)} "
                            f"ADD COLUMN IF NOT EXISTS {ident} {typ}"
                        )
                        logger.info("Added missing QA column | name=%s type=%s", col["column_name"], typ)
        logger.info("QA schema ready | table=%s | target=%s", self.table, self.target.safe_dsn())

    def copy_rows(self, *, truncate: bool) -> int:
        """Copy all Dev rows into QA. Returns inserted row count."""
        columns = self._shared_columns()
        if not columns:
            raise RuntimeError("No shared columns between Dev and QA")

        col_sql = ", ".join(_quote_ident(c) for c in columns)
        select_sql = f"SELECT {col_sql} FROM {_quote_ident(self.table)}"
        insert_sql = (
            f"INSERT INTO {_quote_ident(self.table)} ({col_sql}) VALUES %s"
        )

        copied = 0
        with self.connect(self.source) as src, self.connect(self.target) as dst:
            dst.autocommit = False
            with src.cursor(name="trialgpt_corpus_src") as src_cur, dst.cursor() as dst_cur:
                if truncate:
                    dst_cur.execute(f"TRUNCATE TABLE {_quote_ident(self.table)}")
                src_cur.itersize = self.batch_size
                src_cur.execute(select_sql)
                while True:
                    batch = src_cur.fetchmany(self.batch_size)
                    if not batch:
                        break
                    adapted = [_adapt_row(row) for row in batch]
                    execute_values(dst_cur, insert_sql, adapted, page_size=self.batch_size)
                    copied += len(batch)
                    logger.info("Copied batch | rows=%s total=%s", len(batch), copied)
            dst.commit()
        return copied

    def count_rows(self, target: PgTarget) -> int:
        """Return row count for trialgpt_corpus on the given env."""
        with self.connect(target) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {_quote_ident(self.table)}")
            return int(cur.fetchone()[0])

    def preview(self) -> Dict[str, Any]:
        """Counts and column lists for a dry-run report."""
        return {
            "table": self.table,
            "dev": self.source.safe_dsn(),
            "qa": self.target.safe_dsn(),
            "dev_rows": self.count_rows(self.source),
            "qa_rows_before": self._safe_count(self.target),
            "dev_columns": [c["column_name"] for c in self._columns(self.source)],
        }

    def _safe_count(self, target: PgTarget) -> int | None:
        try:
            return self.count_rows(target)
        except Exception:
            return None

    def _columns(self, target: PgTarget) -> List[Dict[str, str]]:
        with self.connect(target) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, udt_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (self.table,),
            )
            return [
                {
                    "column_name": row[0],
                    "udt_type": _pg_udt_to_ddl(row[1], row[2]),
                }
                for row in cur.fetchall()
            ]

    def _shared_columns(self) -> List[str]:
        src = [c["column_name"] for c in self._columns(self.source)]
        dst = {c["column_name"] for c in self._columns(self.target)}
        return [name for name in src if name in dst]

    def _dev_columns_missing_on_qa(self) -> List[Dict[str, str]]:
        qa_names = {c["column_name"] for c in self._columns(self.target)}
        return [c for c in self._columns(self.source) if c["column_name"] not in qa_names]


def _adapt_value(value: Any) -> Any:
    """Wrap dict/list so psycopg2 can write JSONB columns."""
    if isinstance(value, (dict, list)):
        return Json(value)
    return value


def _adapt_row(row: Sequence[Any]) -> tuple[Any, ...]:
    """Adapt one Dev row for QA insert."""
    return tuple(_adapt_value(value) for value in row)


def _quote_ident(name: str) -> str:
    """Quote a SQL identifier; reject anything that is not a simple name."""
    if not name or not all(ch.isalnum() or ch == "_" for ch in name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return f'"{name}"'


def _pg_udt_to_ddl(udt_name: str, data_type: str) -> str:
    """Map information_schema types to an ADD COLUMN type clause."""
    mapping = {
        "uuid": "UUID",
        "text": "TEXT",
        "int4": "INTEGER",
        "int8": "BIGINT",
        "bool": "BOOLEAN",
        "jsonb": "JSONB",
        "json": "JSON",
        "timestamp": "TIMESTAMP",
        "timestamptz": "TIMESTAMPTZ",
        "varchar": "TEXT",
        "float8": "DOUBLE PRECISION",
    }
    if udt_name in mapping:
        return mapping[udt_name]
    if data_type == "ARRAY":
        return "JSONB"
    return "TEXT"


def load_target(prefix: str, label: str) -> PgTarget:
    """Build a PgTarget from DEV_PG_* or QA_PG_* env vars."""
    host = os.getenv(f"{prefix}_HOST", "").strip()
    dbname = os.getenv(f"{prefix}_DB", "").strip()
    user = os.getenv(f"{prefix}_USER", "").strip()
    password = os.getenv(f"{prefix}_PASSWORD", "")
    port = int(os.getenv(f"{prefix}_PORT", "5432"))
    missing = [k for k, v in {
        f"{prefix}_HOST": host,
        f"{prefix}_DB": dbname,
        f"{prefix}_USER": user,
        f"{prefix}_PASSWORD": password,
    }.items() if not v]
    if missing:
        raise RuntimeError("Missing env: " + ", ".join(missing))
    return PgTarget(
        label=label,
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write schema/data to QA")
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="TRUNCATE QA trialgpt_corpus before insert (full replace)",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument(
        "--allow-same-db",
        action="store_true",
        help="Allow Dev and QA env to point at the same database",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    migrator = TrialgptCorpusMigrator(
        load_target("DEV_PG", "dev"),
        load_target("QA_PG", "qa"),
        batch_size=args.batch_size,
        allow_same_db=args.allow_same_db,
    )
    preview = migrator.preview()
    logger.info("Preview | %s", preview)
    if not args.apply:
        logger.info("Dry-run only. Re-run with --apply --truncate to copy Dev → QA.")
        return 0

    migrator.ensure_schema()
    copied = migrator.copy_rows(truncate=args.truncate)
    qa_after = migrator.count_rows(migrator.target)
    logger.info(
        "Done | copied=%s | qa_rows=%s | dev_rows=%s",
        copied,
        qa_after,
        preview["dev_rows"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
