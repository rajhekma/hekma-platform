"""
One-shot trialgpt_corpus seed from Dev Postgres.

Only startup should call maybe_seed_trialgpt_corpus_from_dev(). The seeder
runs at most once per process. After a successful copy or a 2508-row skip it
writes a DB marker so later restarts never copy again.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Optional

from scripts.migrate_trialgpt_corpus_dev_to_qa import (
    TrialgptCorpusMigrator,
    load_target,
)

logger = logging.getLogger(__name__)

DEFAULT_EXPECTED_ROWS = 2508
# Session advisory lock so multiple uvicorn workers cannot copy in parallel.
_SEED_ADVISORY_LOCK_KEY = 7202508
_MARKER_TABLE = "trialgpt_corpus_seed_marker"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes")


def _expected_rows() -> int:
    raw = os.getenv("TRIALGPT_CORPUS_SEED_EXPECTED_ROWS", str(DEFAULT_EXPECTED_ROWS))
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_EXPECTED_ROWS


class TrialgptCorpusStartupSeeder:
    """Run Dev→local corpus copy at most once per process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._result: Optional[Dict[str, Any]] = None

    def reset_for_tests(self) -> None:
        """Clear the in-process once-guard. Tests only."""
        with self._lock:
            self._result = None

    def run_once(self) -> Dict[str, Any]:
        """Seed if needed; later calls in this process return the first result."""
        with self._lock:
            if self._result is not None:
                logger.info(
                    "trialgpt_corpus seed skipped | reason=already_ran | first_status=%s",
                    self._result.get("status"),
                )
                return {
                    **self._result,
                    "status": "skipped",
                    "reason": "already_ran",
                    "first_status": self._result.get("status"),
                }
            self._result = self._seed()
            return dict(self._result)

    def _seed(self) -> Dict[str, Any]:
        """Copy Dev corpus unless disabled, already marked, or count == expected."""
        if not _env_bool("TRIALGPT_CORPUS_SEED_FROM_DEV"):
            logger.info("trialgpt_corpus seed skipped | reason=disabled")
            return {"status": "skipped", "reason": "disabled"}

        expected = _expected_rows()
        try:
            source = load_target("DEV_PG", "dev")
            target = load_target("PG", "app")
            migrator = TrialgptCorpusMigrator(source, target)
        except Exception as exc:
            return _handle_seed_failure("config", exc)

        try:
            return self._seed_with_lock(migrator, target, expected)
        except Exception as exc:
            return _handle_seed_failure("copy", exc)

    def _seed_with_lock(
        self,
        migrator: TrialgptCorpusMigrator,
        target: Any,
        expected: int,
    ) -> Dict[str, Any]:
        """Hold a PG advisory lock so only one worker can seed."""
        with migrator.connect(target) as lock_conn:
            lock_conn.autocommit = True
            with lock_conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_lock(%s)", (_SEED_ADVISORY_LOCK_KEY,))
            try:
                with lock_conn.cursor() as cur:
                    _ensure_marker_table(cur)
                    if _marker_present(cur):
                        logger.info("trialgpt_corpus seed skipped | reason=already_seeded")
                        return {"status": "skipped", "reason": "already_seeded"}
                try:
                    local_count = migrator.count_rows(target)
                except Exception:
                    local_count = 0
                if local_count == expected:
                    with lock_conn.cursor() as cur:
                        _write_marker(cur, local_count, "expected_count")
                    logger.info(
                        "trialgpt_corpus seed skipped | reason=expected_count | rows=%s",
                        local_count,
                    )
                    return {
                        "status": "skipped",
                        "reason": "expected_count",
                        "local_rows": local_count,
                        "expected_rows": expected,
                    }

                logger.info(
                    "trialgpt_corpus seed start | local_rows=%s | expected=%s | source=%s | target=%s",
                    local_count,
                    expected,
                    migrator.source.safe_dsn(),
                    target.safe_dsn(),
                )
                migrator.ensure_schema()
                copied = migrator.copy_rows(truncate=True)
                after = migrator.count_rows(target)
                with lock_conn.cursor() as cur:
                    _write_marker(cur, after, "seeded")
                logger.info(
                    "trialgpt_corpus seed done | copied=%s | local_rows=%s",
                    copied,
                    after,
                )
                return {
                    "status": "seeded",
                    "copied": copied,
                    "local_rows": after,
                    "expected_rows": expected,
                }
            finally:
                with lock_conn.cursor() as cur:
                    cur.execute(
                        "SELECT pg_advisory_unlock(%s)",
                        (_SEED_ADVISORY_LOCK_KEY,),
                    )


def _ensure_marker_table(cur: Any) -> None:
    """Create the one-row table that records a completed seed."""
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_MARKER_TABLE} (
            id smallint PRIMARY KEY CHECK (id = 1),
            seeded_at timestamptz NOT NULL DEFAULT now(),
            reason text NOT NULL,
            row_count integer
        )
        """
    )


def _marker_present(cur: Any) -> bool:
    """True when this database already finished the one-shot seed."""
    cur.execute(f"SELECT 1 FROM {_MARKER_TABLE} WHERE id = 1")
    return cur.fetchone() is not None


def _write_marker(cur: Any, row_count: int, reason: str) -> None:
    """Persist that seed already ran so later boots never copy again."""
    cur.execute(
        f"""
        INSERT INTO {_MARKER_TABLE} (id, reason, row_count)
        VALUES (1, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (reason, row_count),
    )


def _handle_seed_failure(stage: str, exc: Exception) -> Dict[str, Any]:
    """Log seed failure; raise only when seed is required to boot."""
    logger.exception("trialgpt_corpus seed failed | stage=%s | error=%s", stage, exc)
    if _env_bool("TRIALGPT_CORPUS_SEED_REQUIRED"):
        raise
    return {"status": "failed", "stage": stage, "error": str(exc)}


_SEEDER = TrialgptCorpusStartupSeeder()


def maybe_seed_trialgpt_corpus_from_dev() -> Dict[str, Any]:
    """
    Startup-only entrypoint. Safe to call twice; the second call is a no-op.

    Do not wire this to request handlers.
    """
    return _SEEDER.run_once()


def reset_corpus_seed_once_for_tests() -> None:
    """Clear the process once-guard between unit tests."""
    _SEEDER.reset_for_tests()
