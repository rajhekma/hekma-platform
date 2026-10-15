"""Unit tests for one-shot startup trialgpt_corpus seed."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.trialgpt_corpus_seed_service import (
    maybe_seed_trialgpt_corpus_from_dev,
    reset_corpus_seed_once_for_tests,
)


class _FakeCursor:
    def __init__(self, fetchone_values=None):
        self.fetchone_values = list(fetchone_values or [])

    def execute(self, _sql, _params=None):
        return None

    def fetchone(self):
        if not self.fetchone_values:
            return None
        return self.fetchone_values.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.autocommit = False

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class CorpusSeedServiceTests(unittest.TestCase):
    def setUp(self):
        reset_corpus_seed_once_for_tests()

    def tearDown(self):
        reset_corpus_seed_once_for_tests()

    @patch.dict("os.environ", {"TRIALGPT_CORPUS_SEED_FROM_DEV": "false"}, clear=False)
    def test_disabled_skips(self):
        result = maybe_seed_trialgpt_corpus_from_dev()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "disabled")

    @patch.dict("os.environ", {"TRIALGPT_CORPUS_SEED_FROM_DEV": "false"}, clear=False)
    def test_second_call_in_process_does_not_run_again(self):
        first = maybe_seed_trialgpt_corpus_from_dev()
        second = maybe_seed_trialgpt_corpus_from_dev()
        self.assertEqual(first["reason"], "disabled")
        self.assertEqual(second["reason"], "already_ran")
        self.assertEqual(second["first_status"], "skipped")

    @patch.dict(
        "os.environ",
        {
            "TRIALGPT_CORPUS_SEED_FROM_DEV": "true",
            "TRIALGPT_CORPUS_SEED_EXPECTED_ROWS": "2508",
        },
        clear=False,
    )
    @patch("services.trialgpt_corpus_seed_service.load_target")
    @patch("services.trialgpt_corpus_seed_service.TrialgptCorpusMigrator")
    def test_skips_when_count_is_2508(self, mock_migrator_cls, mock_load):
        mock_load.side_effect = [MagicMock(), MagicMock()]
        migrator = mock_migrator_cls.return_value
        migrator.count_rows.return_value = 2508
        cursor = _FakeCursor(fetchone_values=[None])
        migrator.connect.return_value = _FakeConn(cursor)

        result = maybe_seed_trialgpt_corpus_from_dev()

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "expected_count")
        migrator.copy_rows.assert_not_called()

    @patch.dict(
        "os.environ",
        {
            "TRIALGPT_CORPUS_SEED_FROM_DEV": "true",
            "TRIALGPT_CORPUS_SEED_EXPECTED_ROWS": "2508",
        },
        clear=False,
    )
    @patch("services.trialgpt_corpus_seed_service.load_target")
    @patch("services.trialgpt_corpus_seed_service.TrialgptCorpusMigrator")
    def test_skips_when_marker_already_written(self, mock_migrator_cls, mock_load):
        mock_load.side_effect = [MagicMock(), MagicMock()]
        migrator = mock_migrator_cls.return_value
        cursor = _FakeCursor(fetchone_values=[(1,)])
        migrator.connect.return_value = _FakeConn(cursor)

        result = maybe_seed_trialgpt_corpus_from_dev()

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "already_seeded")
        migrator.copy_rows.assert_not_called()
        migrator.count_rows.assert_not_called()

    @patch.dict(
        "os.environ",
        {
            "TRIALGPT_CORPUS_SEED_FROM_DEV": "true",
            "TRIALGPT_CORPUS_SEED_EXPECTED_ROWS": "2508",
        },
        clear=False,
    )
    @patch("services.trialgpt_corpus_seed_service.load_target")
    @patch("services.trialgpt_corpus_seed_service.TrialgptCorpusMigrator")
    def test_copies_once_when_count_not_2508(self, mock_migrator_cls, mock_load):
        mock_load.side_effect = [MagicMock(), MagicMock()]
        migrator = mock_migrator_cls.return_value
        migrator.count_rows.side_effect = [0, 2508]
        migrator.copy_rows.return_value = 2508
        cursor = _FakeCursor(fetchone_values=[None])
        migrator.connect.return_value = _FakeConn(cursor)

        first = maybe_seed_trialgpt_corpus_from_dev()
        second = maybe_seed_trialgpt_corpus_from_dev()

        self.assertEqual(first["status"], "seeded")
        self.assertEqual(second["reason"], "already_ran")
        migrator.copy_rows.assert_called_once_with(truncate=True)
        self.assertEqual(mock_migrator_cls.call_count, 1)
