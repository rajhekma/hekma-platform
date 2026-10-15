"""
Unit tests for 100% offline rule-based and heuristic criteria matcher.
Verifies all clinical edge cases: age limits, biological sex, pregnancy,
biomarkers, negation detection, contraindications, and sentence attribution.
"""

import unittest
from trialgpt_lite.schemas.study import TrialStudy, DemographicCriteria, ParsedCriteria
from trialgpt_lite.schemas.request import PatientProfile
from trialgpt_lite.matcher.llm_matcher import RuleBasedCriteriaMatcher, _is_negated_in_sentence, _evaluate_age_criterion


class TestRuleMatcher(unittest.TestCase):

    def setUp(self):
        self.matcher = RuleBasedCriteriaMatcher()

    def test_age_evaluation_utility(self):
        lbl, rsn = _evaluate_age_criterion("Patients must be between 18 and 75 years old", "inclusion", 50)
        self.assertEqual(lbl, "included")

        lbl2, rsn2 = _evaluate_age_criterion("Patients must be between 18 and 75 years old", "inclusion", 80)
        self.assertEqual(lbl2, "not included")

        lbl3, rsn3 = _evaluate_age_criterion("Age >= 18 years of age", "inclusion", 15)
        self.assertEqual(lbl3, "not included")

        lbl4, rsn4 = _evaluate_age_criterion("Pediatric patients under 18 years", "exclusion", 15)
        self.assertEqual(lbl4, "excluded")


    def test_negation_detection(self):
        s1 = "Patient has no evidence of active brain metastases."
        self.assertTrue(_is_negated_in_sentence(s1, "brain metastases"))

        s2 = "Patient underwent MRI which confirmed active brain metastases."
        self.assertFalse(_is_negated_in_sentence(s2, "brain metastases"))

        s3 = "Biopsy was negative for EGFR mutation."
        self.assertTrue(_is_negated_in_sentence(s3, "egfr"))

        s4 = "Patient is positive for EGFR L858R mutation."
        self.assertFalse(_is_negated_in_sentence(s4, "egfr"))

    def test_age_criteria_matching(self):
        study = TrialStudy(
            nct_id="NCT1001",
            brief_title="Adult Oncology Protocol",
            overall_status="RECRUITING",
            criteria=ParsedCriteria(
                inclusion_criteria=["Age >= 18 years of age or older."],
                exclusion_criteria=["Patients older than 75 years."],
            )
        )

        # Case 1: In range (55 years)
        p1 = PatientProfile(age=55, condition="Melanoma", clinical_note="55 yo patient with melanoma.")
        evals1 = self.matcher.match_criteria(study, p1)
        inc_eval = [e for e in evals1 if e.criterion_type == "inclusion"][0]
        exc_eval = [e for e in evals1 if e.criterion_type == "exclusion"][0]
        self.assertEqual(inc_eval.label, "included")
        self.assertEqual(exc_eval.label, "not excluded")

        # Case 2: Underage (15 years)
        p2 = PatientProfile(age=15, condition="Melanoma", clinical_note="15 yo pediatric patient.")
        evals2 = self.matcher.match_criteria(study, p2)
        inc_eval2 = [e for e in evals2 if e.criterion_type == "inclusion"][0]
        self.assertEqual(inc_eval2.label, "not included")

        # Case 3: Overage for exclusion (80 years)
        p3 = PatientProfile(age=80, condition="Melanoma", clinical_note="80 yo geriatric patient.")
        evals3 = self.matcher.match_criteria(study, p3)
        exc_eval3 = [e for e in evals3 if e.criterion_type == "exclusion"][0]
        self.assertEqual(exc_eval3.label, "excluded")

        # Case 4: Missing age
        p4 = PatientProfile(condition="Melanoma", clinical_note="Patient with melanoma.")
        evals4 = self.matcher.match_criteria(study, p4)
        inc_eval4 = [e for e in evals4 if e.criterion_type == "inclusion"][0]
        self.assertEqual(inc_eval4.label, "not enough information")

    def test_pregnancy_rules(self):
        study = TrialStudy(
            nct_id="NCT1002",
            brief_title="Safety Trial",
            overall_status="RECRUITING",
            criteria=ParsedCriteria(
                exclusion_criteria=["Pregnant or breastfeeding women."],
            )
        )

        # Male patient -> Not Applicable
        p_male = PatientProfile(sex="MALE", clinical_note="Male patient with lung cancer.")
        evals_m = self.matcher.match_criteria(study, p_male)
        self.assertEqual(evals_m[0].label, "not applicable")

        # Female non-pregnant patient -> Not Excluded
        p_female = PatientProfile(sex="FEMALE", clinical_note="Female patient with stage IV cancer. Denies pregnancy.")
        evals_f = self.matcher.match_criteria(study, p_female)
        self.assertEqual(evals_f[0].label, "not excluded")

        # Female pregnant patient -> Excluded
        p_preg = PatientProfile(sex="FEMALE", clinical_note="Patient is currently pregnant in first trimester.")
        evals_p = self.matcher.match_criteria(study, p_preg)
        self.assertEqual(evals_p[0].label, "excluded")

    def test_contraindications_with_negation(self):
        study = TrialStudy(
            nct_id="NCT1003",
            brief_title="Immunotherapy Protocol",
            overall_status="RECRUITING",
            criteria=ParsedCriteria(
                exclusion_criteria=["Active brain metastases or leptomeningeal disease."],
            )
        )

        # Note says "No evidence of brain metastases" -> MUST NOT be excluded
        p_clean = PatientProfile(
            clinical_note="Brain MRI performed yesterday showed no evidence of brain metastases."
        )
        evals = self.matcher.match_criteria(study, p_clean)
        self.assertEqual(evals[0].label, "not excluded")

        # Note confirms active brain metastases -> MUST be excluded
        p_positive = PatientProfile(
            clinical_note="Brain MRI revealed active brain metastases in right frontal lobe."
        )
        evals_pos = self.matcher.match_criteria(study, p_positive)
        self.assertEqual(evals_pos[0].label, "excluded")

    def test_biomarker_inclusion_and_sentence_citation(self):
        study = TrialStudy(
            nct_id="NCT1004",
            brief_title="Targeted NSCLC Study",
            overall_status="RECRUITING",
            criteria=ParsedCriteria(
                inclusion_criteria=[
                    "Histologically confirmed non-small cell lung cancer.",
                    "Documented activating EGFR mutation (exon 19 del or L858R).",
                ]
            )
        )

        note = "Patient has stage IV non-small cell lung cancer. Molecular profiling confirms presence of EGFR exon 19 deletion. ECOG is 1."
        patient = PatientProfile(condition="non-small cell lung cancer", clinical_note=note)
        evals = self.matcher.match_criteria(study, patient)

        self.assertEqual(len(evals), 2)
        # Both criteria should match
        self.assertEqual(evals[0].label, "included")
        self.assertEqual(evals[1].label, "included")
        # Evidence sentence ID should cite sentence 1 ("Molecular profiling confirms presence of EGFR exon 19 deletion.")
        self.assertIn(1, evals[1].sentence_ids)


if __name__ == "__main__":
    unittest.main()
