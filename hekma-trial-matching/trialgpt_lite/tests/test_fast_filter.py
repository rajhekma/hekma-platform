"""
Unit tests for fast demographic and status filter.
"""

import unittest
from trialgpt_lite.schemas.study import TrialStudy, DemographicCriteria, ParsedCriteria
from trialgpt_lite.schemas.request import PatientProfile
from trialgpt_lite.matcher.fast_filter import evaluate_fast_filter


class TestFastFilter(unittest.TestCase):

    def setUp(self):
        self.study = TrialStudy(
            nct_id="NCT12345678",
            brief_title="Test Trial",
            overall_status="RECRUITING",
            demographics=DemographicCriteria(
                minimum_age_years=18.0,
                maximum_age_years=65.0,
                sex="FEMALE",
            ),
            criteria=ParsedCriteria(),
        )

    def test_matching_patient(self):
        patient = PatientProfile(age=35.0, sex="FEMALE")
        res = evaluate_fast_filter(self.study, patient, recruiting_only=True)
        self.assertTrue(res.passed)
        self.assertEqual(len(res.reasons), 0)

    def test_age_below_minimum(self):
        patient = PatientProfile(age=16.0, sex="FEMALE")
        res = evaluate_fast_filter(self.study, patient, recruiting_only=True)
        self.assertFalse(res.passed)
        self.assertTrue(any("below minimum" in r for r in res.reasons))

    def test_age_above_maximum(self):
        patient = PatientProfile(age=72.0, sex="FEMALE")
        res = evaluate_fast_filter(self.study, patient, recruiting_only=True)
        self.assertFalse(res.passed)
        self.assertTrue(any("exceeds maximum" in r for r in res.reasons))

    def test_sex_mismatch(self):
        patient = PatientProfile(age=30.0, sex="MALE")
        res = evaluate_fast_filter(self.study, patient, recruiting_only=True)
        self.assertFalse(res.passed)
        self.assertTrue(any("Sex mismatch" in r for r in res.reasons))

    def test_status_filter_rejection(self):
        self.study.overall_status = "TERMINATED"
        patient = PatientProfile(age=35.0, sex="FEMALE")
        res = evaluate_fast_filter(self.study, patient, recruiting_only=True)
        self.assertFalse(res.passed)
        self.assertTrue(any("not recruiting" in r for r in res.reasons))


if __name__ == "__main__":
    unittest.main()
