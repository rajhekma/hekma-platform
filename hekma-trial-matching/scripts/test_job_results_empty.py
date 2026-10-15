"""Empty P2T results must include a terminal status so the UI stops polling."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.response_builders import _results_envelope, build_job_results_response


class EmptyJobResultsTests(unittest.TestCase):
    @patch("core.response_builders.fetch_job_results", return_value=[])
    def test_empty_completed_job_is_done(self, _mock_fetch):
        payload = build_job_results_response(
            "job-1",
            flow_type="P2T",
            job={
                "status": "COMPLETED",
                "query_id": "subj-1",
                "compose_status": "COMPLETED",
                "retrieve_status": "COMPLETED",
                "evaluate_status": "COMPLETED",
                "rank_status": "COMPLETED",
            },
        )
        self.assertEqual(payload["evaluations"], [])
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertTrue(payload["done"])
        self.assertEqual(payload["total_count"], 0)
        self.assertEqual(payload["patient_id"], "subj-1")

    @patch("core.response_builders.fetch_job_results", return_value=[])
    def test_empty_running_job_is_not_done(self, _mock_fetch):
        payload = build_job_results_response(
            "job-2",
            flow_type="P2T",
            job={"status": "RUNNING", "rank_status": "RUNNING", "query_id": "subj-2"},
        )
        self.assertFalse(payload["done"])
        self.assertEqual(payload["status"], "RUNNING")

    @patch("core.response_builders.fetch_job_results", return_value=[])
    def test_failed_job_is_done_with_error(self, _mock_fetch):
        payload = build_job_results_response(
            "job-3",
            flow_type="P2T",
            job={
                "status": "FAILED",
                "query_id": "subj-3",
                "error": "no trials",
                "error_stage": "rank",
            },
        )
        self.assertTrue(payload["done"])
        self.assertEqual(payload["error"], "no trials")

    def test_envelope_marks_cancelled_done(self):
        env = _results_envelope("j", {"status": "CANCELLED"}, flow_type="T2P")
        self.assertTrue(env["done"])
        self.assertEqual(env["nct_id"], None)

    @patch("core.response_builders.fetch_locations_by_nct_ids")
    @patch("core.response_builders.fetch_job_results")
    def test_completed_job_with_trials_keeps_evaluations(self, mock_fetch, mock_locs):
        mock_fetch.return_value = [
            {
                "query_id": "subj-9",
                "candidate_id": "NCT00000001",
                "rank_position": 1,
                "final_score": 0.8,
                "relevance_score_R": 0.5,
                "eligibility_score_E": 0.6,
                "inclusion_results": {},
                "exclusion_results": {},
                "parameters": {"selected_region": ["Karachi, Sindh, Pakistan"]},
            }
        ]
        mock_locs.return_value = {
            "NCT00000001": {
                "title": "Example trial",
                "locations": ["Karachi, Sindh, Pakistan"],
                "locations_detailed": [],
                "enrollment": {},
                "overall_status": "Recruiting",
                "phase": "Phase 2",
                "start_date": None,
                "completion_date": None,
            }
        }
        payload = build_job_results_response(
            "job-9",
            flow_type="P2T",
            job={"status": "COMPLETED", "query_id": "subj-9"},
        )
        self.assertTrue(payload["done"])
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["total_count"], 1)
        self.assertEqual(payload["evaluations"][0]["trial_id"], "NCT00000001")
        self.assertEqual(payload["evaluations"][0]["trial_title"], "Example trial")
        self.assertEqual(payload["patient_id"], "subj-9")


if __name__ == "__main__":
    unittest.main()
