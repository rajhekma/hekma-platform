"""Unit tests for insight patient-summary lookup (EHR first, eligible fallback)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories.inference_repo import fetch_patient_summary_for_inference


class _Cursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append((sql, params))

    def fetchone(self):
        if not self.responses:
            return None
        return self.responses.pop(0)


class InferencePatientSummaryTests(unittest.TestCase):
    def test_prefers_ehr_ready_summary(self):
        cur = _Cursor([{"summary_text": "  EHR story  "}])
        with patch(
            "repositories.inference_repo._preferred_llm_flag",
            return_value=True,
        ):
            row = fetch_patient_summary_for_inference(cur, "subj-1")
        self.assertEqual(row, {"summary_text": "EHR story"})
        self.assertIn("trial_gpt_ehr", cur.sql[0][0])
        self.assertEqual(cur.sql[0][1], ("subj-1", True))

    def test_falls_back_to_other_llm_flag(self):
        cur = _Cursor([None, {"summary_text": "rule based"}])
        with patch(
            "repositories.inference_repo._preferred_llm_flag",
            return_value=True,
        ):
            row = fetch_patient_summary_for_inference(cur, "subj-1")
        self.assertEqual(row, {"summary_text": "rule based"})
        self.assertEqual(cur.sql[1][1], ("subj-1", False))

    def test_falls_back_to_eligible_patients(self):
        cur = _Cursor([None, None, {"summary_text": "cohort summary"}])
        with patch(
            "repositories.inference_repo._preferred_llm_flag",
            return_value=True,
        ):
            row = fetch_patient_summary_for_inference(cur, "subj-1")
        self.assertEqual(row, {"summary_text": "cohort summary"})
        self.assertIn("trialgpt_eligible_patients", cur.sql[2][0])

    def test_blank_ehr_then_eligible(self):
        cur = _Cursor(
            [
                {"summary_text": "   "},
                {"summary_text": ""},
                {"summary_text": "from eligible"},
            ]
        )
        with patch(
            "repositories.inference_repo._preferred_llm_flag",
            return_value=True,
        ):
            row = fetch_patient_summary_for_inference(cur, "subj-1")
        self.assertEqual(row, {"summary_text": "from eligible"})

    def test_missing_everywhere_returns_none(self):
        cur = _Cursor([None, None, None])
        with patch(
            "repositories.inference_repo._preferred_llm_flag",
            return_value=True,
        ):
            self.assertIsNone(fetch_patient_summary_for_inference(cur, "subj-1"))

    def test_empty_subject_skips_queries(self):
        cur = _Cursor([])
        self.assertIsNone(fetch_patient_summary_for_inference(cur, "  "))
        self.assertEqual(cur.sql, [])


if __name__ == "__main__":
    unittest.main()
