"""
Unit tests for eligibility scorer and verdict aggregation.
"""

import unittest
from trialgpt_lite.schemas.study import TrialStudy, DemographicCriteria, ParsedCriteria
from trialgpt_lite.schemas.match_result import (
    CriterionEvaluation,
    FastFilterResult,
    OverallEligibility,
)
from trialgpt_lite.matcher.scorer import score_and_aggregate_trial


class TestScorer(unittest.TestCase):

    def setUp(self):
        self.study = TrialStudy(
            nct_id="NCT99999999",
            brief_title="Immunotherapy Trial",
            overall_status="RECRUITING",
            demographics=DemographicCriteria(),
            criteria=ParsedCriteria(
                inclusion_criteria=["Histologically confirmed melanoma"],
                exclusion_criteria=["Active brain metastases"],
                raw_text="Inclusion Criteria:\n- Histologically confirmed melanoma\nExclusion Criteria:\n- Active brain metastases",
            ),
        )

    def test_filtered_out_pre_screening(self):
        fast_res = FastFilterResult(passed=False, reasons=["Age below minimum"])
        result = score_and_aggregate_trial(
            study=self.study,
            fast_filter=fast_res,
            evaluations=[],
            has_patient_context=True,
        )
        self.assertEqual(result.verdict, OverallEligibility.FILTERED_OUT)
        self.assertEqual(result.eligibility_score, 0.0)

    def test_condition_only_search(self):
        fast_res = FastFilterResult(passed=True, reasons=[])
        result = score_and_aggregate_trial(
            study=self.study,
            fast_filter=fast_res,
            evaluations=[],
            has_patient_context=False,
        )
        self.assertEqual(result.verdict, OverallEligibility.RETRIEVED_ONLY)
        self.assertEqual(result.eligibility_score, 1.0)
        self.assertEqual(result.participation_criteria.inclusion_criteria, ["Histologically confirmed melanoma"])
        self.assertEqual(result.participation_criteria.exclusion_criteria, ["Active brain metastases"])

    def test_fully_eligible(self):
        fast_res = FastFilterResult(passed=True, reasons=[])
        evals = [
            CriterionEvaluation(
                criterion_index=0,
                criterion_type="inclusion",
                criterion_text="Diagnosis of melanoma",
                reasoning="Patient has melanoma",
                sentence_ids=[0],
                label="included",
            ),
            CriterionEvaluation(
                criterion_index=0,
                criterion_type="exclusion",
                criterion_text="Active brain metastases",
                reasoning="No brain mets",
                sentence_ids=[],
                label="not excluded",
            ),
        ]
        result = score_and_aggregate_trial(
            study=self.study,
            fast_filter=fast_res,
            evaluations=evals,
            has_patient_context=True,
        )
        self.assertEqual(result.verdict, OverallEligibility.ELIGIBLE)
        self.assertGreaterEqual(result.eligibility_score, 0.95)

    def test_disqualified_by_exclusion(self):
        fast_res = FastFilterResult(passed=True, reasons=[])
        evals = [
            CriterionEvaluation(
                criterion_index=0,
                criterion_type="inclusion",
                criterion_text="Diagnosis of melanoma",
                reasoning="Patient has melanoma",
                sentence_ids=[0],
                label="included",
            ),
            CriterionEvaluation(
                criterion_index=0,
                criterion_type="exclusion",
                criterion_text="Active brain metastases",
                reasoning="Patient MRI shows active cerebral lesions",
                sentence_ids=[2],
                label="excluded",
            ),
        ]
        result = score_and_aggregate_trial(
            study=self.study,
            fast_filter=fast_res,
            evaluations=evals,
            has_patient_context=True,
        )
        self.assertEqual(result.verdict, OverallEligibility.INELIGIBLE)
        self.assertLessEqual(result.eligibility_score, 0.2)
        self.assertIn("ineligible", result.summary_reasoning.lower())

    def test_likely_eligible_with_pending_info(self):
        fast_res = FastFilterResult(passed=True, reasons=[])
        evals = [
            CriterionEvaluation(
                criterion_index=0,
                criterion_type="inclusion",
                criterion_text="Confirmed NSCLC",
                reasoning="Biopsy confirmed NSCLC",
                sentence_ids=[0],
                label="included",
            ),
            CriterionEvaluation(
                criterion_index=1,
                criterion_type="inclusion",
                criterion_text="PD-L1 expression >= 50%",
                reasoning="PD-L1 IHC not mentioned in note",
                sentence_ids=[],
                label="not enough information",
            ),
            CriterionEvaluation(
                criterion_index=0,
                criterion_type="exclusion",
                criterion_text="Prior EGFR TKI therapy",
                reasoning="No prior TKI documented",
                sentence_ids=[],
                label="not excluded",
            ),
        ]
        result = score_and_aggregate_trial(
            study=self.study,
            fast_filter=fast_res,
            evaluations=evals,
            has_patient_context=True,
        )
        self.assertEqual(result.verdict, OverallEligibility.LIKELY_ELIGIBLE)
        self.assertGreaterEqual(result.eligibility_score, 0.6)


if __name__ == "__main__":
    unittest.main()
