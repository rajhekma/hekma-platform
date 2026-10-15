"""Unit tests for full TrialGPT schema auto-create."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories import trialgpt_schema_bootstrap
from repositories.trialgpt_schema_bootstrap import (
    TRIALGPT_MIGRATION_FILES,
    TRIALGPT_OWNED_TABLES,
    ensure_trialgpt_schema,
    reset_trialgpt_schema_for_tests,
    schema_status,
    split_sql_statements,
)


class SplitSqlTests(unittest.TestCase):
    def test_skips_comments_and_splits_statements(self):
        ddl = """
        -- heading
        CREATE TABLE IF NOT EXISTS matching_jobs (job_id UUID PRIMARY KEY);
        CREATE INDEX IF NOT EXISTS idx_matching_jobs_status ON matching_jobs (status);
        """
        parts = split_sql_statements(ddl)
        self.assertEqual(len(parts), 2)
        self.assertIn("CREATE TABLE IF NOT EXISTS matching_jobs", parts[0])
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_matching_jobs_status", parts[1])


class TrialgptSchemaBootstrapTests(unittest.TestCase):
    def setUp(self):
        reset_trialgpt_schema_for_tests()

    def tearDown(self):
        reset_trialgpt_schema_for_tests()

    @patch("repositories.trialgpt_schema_bootstrap.pg_transaction")
    def test_ensure_applies_every_owned_table_once(self, mock_txn):
        cur = MagicMock()
        mock_txn.return_value.__enter__.return_value = (None, cur)

        ensure_trialgpt_schema()
        ensure_trialgpt_schema()

        ddl = "\n".join(call.args[0] for call in cur.execute.call_args_list)
        for table in TRIALGPT_OWNED_TABLES:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", ddl)
        self.assertIn("ADD COLUMN IF NOT EXISTS summary_text", ddl)
        self.assertIn("ADD COLUMN IF NOT EXISTS site_id", ddl)

    @patch("repositories.trialgpt_schema_bootstrap.pg_transaction")
    def test_optional_index_failure_does_not_block_tables(self, mock_txn):
        cur = MagicMock()
        mock_txn.return_value.__enter__.return_value = (None, cur)

        def execute(sql, params=None):
            if "SET statement_timeout" in sql:
                return None
            if "CREATE INDEX" in sql.upper() or "CREATE UNIQUE" in sql.upper():
                raise RuntimeError("index timeout")
            if "CREATE EXTENSION" in sql.upper():
                raise RuntimeError("permission denied")
            return None

        cur.execute.side_effect = execute
        ensure_trialgpt_schema()

    def test_migration_files_exist(self):
        migration_dir = ROOT / "migration"
        for name in TRIALGPT_MIGRATION_FILES:
            self.assertTrue((migration_dir / name).is_file(), name)

    def test_owned_table_list_matches_bootstrap_module(self):
        self.assertEqual(
            list(TRIALGPT_OWNED_TABLES),
            list(trialgpt_schema_bootstrap.TRIALGPT_OWNED_TABLES),
        )

    @patch("repositories.trialgpt_schema_bootstrap.ensure_trialgpt_schema")
    @patch("repositories.trialgpt_schema_bootstrap.pg_transaction")
    def test_schema_status_lists_missing(self, mock_txn, _mock_ensure):
        cur = MagicMock()
        mock_txn.return_value.__enter__.return_value = (None, cur)
        cur.fetchall.return_value = [{"tablename": "trialgpt_corpus"}]

        status = schema_status()

        self.assertIn("trialgpt_corpus", status["existing"])
        self.assertIn("matching_jobs", status["missing"])
        self.assertFalse(status["ok"])


if __name__ == "__main__":
    unittest.main()
