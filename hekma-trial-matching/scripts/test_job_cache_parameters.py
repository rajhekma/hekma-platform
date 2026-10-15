"""Unit tests for P2T/T2P job-parameter cache fingerprinting."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories.matching_jobs_repo import canonical_job_parameters


class CanonicalJobParametersTests(unittest.TestCase):
    def test_strips_force_rerun(self):
        params = {
            "patient_id": "203563",
            "selected_disease": [],
            "selected_region": ["US"],
            "force_rerun": True,
            "debug": True,
        }
        out = canonical_job_parameters(params)
        self.assertNotIn("force_rerun", out)
        self.assertEqual(out["patient_id"], "203563")
        self.assertTrue(out["debug"])

    def test_force_rerun_true_and_false_share_fingerprint(self):
        a = canonical_job_parameters({"patient_id": "1", "force_rerun": True, "corpus": "sigir"})
        b = canonical_job_parameters({"patient_id": "1", "force_rerun": False, "corpus": "sigir"})
        self.assertEqual(a, b)

    def test_non_dict_returns_empty(self):
        self.assertEqual(canonical_job_parameters(None), {})


if __name__ == "__main__":
    unittest.main()
