"""Tests for trial_condition_filter (Fasten /diseases UI list)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.trial_condition_filter import filter_fasten_condition_entries


class TrialConditionFilterTests(unittest.TestCase):
    def test_excludes_admin_social_and_screening(self):
        entries = [
            {"official_name": "Homeless", "icd10_code": None, "input": "Homeless"},
            {"official_name": "Discharge Planning", "icd10_code": None, "input": "Discharge Planning"},
            {
                "official_name": "ENCOUNTER FOR SCREENING FOR RESPIRATORY TUBERCULOSIS",
                "icd10_code": "Z11.1",
                "input": "ENCOUNTER FOR SCREENING FOR RESPIRATORY TUBERCULOSIS",
            },
            {
                "official_name": "PT NONCOMPL WITH DIETARY REGIMEN DUE TO FINANCL HARDSHIP",
                "icd10_code": "Z91.110",
                "input": "PT NONCOMPL WITH DIETARY REGIMEN DUE TO FINANCL HARDSHIP",
            },
            {
                "official_name": "Migraine without aura, not intractable, with status migrainosus",
                "icd10_code": "G43.001",
                "input": "Migraine without aura, not intractable, with status migrainosus",
            },
            {"official_name": "MIGRAINE", "icd10_code": "G43", "input": "MIGRAINE"},
            {
                "official_name": "SPINAL MUSCULAR ATROPHY AND RELATED SYNDROMES",
                "icd10_code": "G12",
                "input": "SPINAL MUSCULAR ATROPHY AND RELATED SYNDROMES",
            },
        ]
        names, kept = filter_fasten_condition_entries(entries)
        self.assertNotIn("Homeless", names)
        self.assertNotIn("Discharge Planning", names)
        self.assertTrue(any("migraine" in n.lower() for n in names))
        self.assertEqual(sum(1 for n in names if "migraine" in n.lower()), 1)
        self.assertTrue(any("G12" in str(e.get("icd10_code")) for e in kept))


if __name__ == "__main__":
    unittest.main()
