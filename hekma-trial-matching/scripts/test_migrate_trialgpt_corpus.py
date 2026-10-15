"""Unit tests for Dev → QA trialgpt_corpus migrator helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from migrate_trialgpt_corpus_dev_to_qa import (
    PgTarget,
    TrialgptCorpusMigrator,
    _adapt_value,
    _pg_udt_to_ddl,
    _quote_ident,
    load_target,
)
from psycopg2.extras import Json


def _target(label: str, host: str) -> PgTarget:
    return PgTarget(label=label, host=host, port=5432, dbname="hekmaai", user="u", password="p")


class QuoteIdentTests(unittest.TestCase):
    def test_quotes_safe_name(self):
        self.assertEqual(_quote_ident("trialgpt_corpus"), '"trialgpt_corpus"')

    def test_rejects_injection(self):
        with self.assertRaises(ValueError):
            _quote_ident("trialgpt_corpus; drop table x")


class AdaptJsonTests(unittest.TestCase):
    def test_wraps_dict_and_list(self):
        self.assertIsInstance(_adapt_value({"a": 1}), Json)
        self.assertIsInstance(_adapt_value(["US"]), Json)

    def test_leaves_scalars(self):
        self.assertEqual(_adapt_value("NCT1"), "NCT1")
        self.assertIsNone(_adapt_value(None))


class PgUdtTests(unittest.TestCase):
    def test_maps_jsonb(self):
        self.assertEqual(_pg_udt_to_ddl("jsonb", "jsonb"), "JSONB")


class MigratorGuardTests(unittest.TestCase):
    def test_rejects_unknown_table(self):
        with self.assertRaises(ValueError):
            TrialgptCorpusMigrator(_target("dev", "a"), _target("qa", "b"), table="other")

    def test_rejects_same_db(self):
        src = _target("dev", "same")
        with self.assertRaises(ValueError):
            TrialgptCorpusMigrator(src, src)

    def test_allow_same_db(self):
        src = _target("dev", "same")
        migrator = TrialgptCorpusMigrator(src, src, allow_same_db=True)
        self.assertEqual(migrator.table, "trialgpt_corpus")


class LoadTargetTests(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            "DEV_PG_HOST": "dev.example",
            "DEV_PG_DB": "hekmaai",
            "DEV_PG_USER": "app",
            "DEV_PG_PASSWORD": "secret",
            "DEV_PG_PORT": "5433",
        },
        clear=False,
    )
    def test_loads_dev_env(self):
        target = load_target("DEV_PG", "dev")
        self.assertEqual(target.host, "dev.example")
        self.assertEqual(target.port, 5433)
        self.assertNotIn("secret", target.safe_dsn())


if __name__ == "__main__":
    unittest.main()
