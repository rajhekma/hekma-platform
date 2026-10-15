"""Unit tests for trial_gpt_ehr ingest progress payloads."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.trial_gpt_ehr_ingest_service import format_worker_error
from services.trial_gpt_ehr_progress import (
    AUTO_RETRY_COOLDOWN_SECONDS,
    build_ingest_progress,
    normalize_stored_error,
)


class IngestProgressTests(unittest.TestCase):
    def test_ready_stage_is_100_percent(self):
        progress = build_ingest_progress(
            mysql_patient_id=203578,
            llm=True,
            in_flight=False,
            has_ready=True,
            summary_row={"summary_status": "ready"},
            fasten_present=True,
            fasten_rows=100,
        )
        self.assertEqual(progress["stage"], "ready")
        self.assertEqual(progress["progress_percent"], 100)

    @patch("services.trial_gpt_ehr_ingest_service.is_stale_ingesting_row", return_value=False)
    def test_failed_maps_to_retrying_preparing(self, mock_stale):
        progress = build_ingest_progress(
            mysql_patient_id=203578,
            llm=True,
            in_flight=False,
            has_ready=False,
            summary_row={
                "summary_status": "failed",
                "structured_json": {"error": "temporary"},
                "updated_at": datetime.utcnow(),
            },
            fasten_present=True,
            fasten_rows=50,
        )
        self.assertEqual(progress["ehr_status"], "preparing")
        self.assertEqual(progress["stage"], "retrying")
        self.assertEqual(progress["error_display"], "temporary")

    @patch("services.trial_gpt_ehr_ingest_service.is_stale_ingesting_row", return_value=False)
    def test_legacy_index_error_three_is_readable(self, mock_stale):
        progress = build_ingest_progress(
            mysql_patient_id=203578,
            llm=True,
            in_flight=False,
            has_ready=False,
            summary_row={
                "summary_status": "failed",
                "structured_json": {"error": "3"},
                "updated_at": datetime.utcnow(),
            },
            fasten_present=True,
            fasten_rows=50,
            retry_cooldown_seconds_remaining=45,
        )
        self.assertIn("Docker", progress["error_display"])
        self.assertIn("45 seconds", progress["message"])
        self.assertGreater(progress["progress_percent"], 30)
        self.assertLess(progress["progress_percent"], 45)

    @patch("services.trial_gpt_ehr_ingest_service.is_stale_ingesting_row", return_value=False)
    def test_retrying_in_flight_shows_active_retry(self, mock_stale):
        progress = build_ingest_progress(
            mysql_patient_id=203578,
            llm=True,
            in_flight=True,
            has_ready=False,
            summary_row={"summary_status": "failed", "structured_json": {"error": "3"}},
            fasten_present=True,
            fasten_rows=50,
            retry_scheduled=True,
        )
        self.assertEqual(progress["progress_percent"], 45)
        self.assertIn("now", progress["message"])


class WorkerErrorFormatTests(unittest.TestCase):
    def test_index_error_digit_becomes_readable(self):
        msg = format_worker_error(IndexError(3))
        self.assertIn("Docker", msg)

    def test_normalize_stored_error_maps_digit(self):
        self.assertIn("Docker", normalize_stored_error("3"))


if __name__ == "__main__":
    unittest.main()
