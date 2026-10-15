"""
Unit tests for 100% Offline Question Generator and Eligibility Evaluator.
"""

import pytest
from trialgpt_lite.schemas.study import TrialStudy, DemographicCriteria, ParsedCriteria
from trialgpt_lite.parser.question_generator import (
    generate_offline_questions,
    evaluate_offline_questionnaire,
)
from trialgpt_lite.schemas.match_result import OverallEligibility


@pytest.fixture
def sample_study():
    return TrialStudy(
        nct_id="NCT05801029",
        brief_title="Study of Osimertinib in Advanced NSCLC",
        official_title="A Phase 2 Study of Osimertinib in Patients with EGFR-Mutated Metastatic NSCLC",
        overall_status="RECRUITING",
        study_type="INTERVENTIONAL",
        conditions=["Non-Small Cell Lung Cancer", "Carcinoma, Non-Small-Cell Lung"],
        demographics=DemographicCriteria(
            minimum_age_years=18.0,
            minimum_age_text="18 Years",
            sex="ALL",
        ),
        criteria=ParsedCriteria(
            inclusion_criteria=[
                "Histologically or cytologically confirmed Stage IV metastatic NSCLC.",
                "Prior systemic chemotherapy completed at least 4 weeks prior.",
                "ECOG performance status 0 or 1.",
                "Absolute Neutrophil Count (ANC) >= 1.5 x 10^9/L, Platelets >= 100 x 10^9/L.",  # Lab noise
                "Signed written informed consent.",  # Legal boilerplate
            ],
            exclusion_criteria=[
                "Active or untreated central nervous system (CNS) metastases.",
                "Pregnant, nursing, or breastfeeding females.",
                "Serum creatinine > 1.5x ULN or total bilirubin > 2.0x ULN.",  # Lab noise
                "Known active Hepatitis B, Hepatitis C, or HIV infection.",
            ],
            raw_text="Raw criteria text...",
        ),
    )


def test_generate_offline_questions_filters_noise(sample_study):
    resp = generate_offline_questions(sample_study)
    assert resp.nct_id == "NCT05801029"
    assert resp.total_questions > 0
    assert len(resp.questions) <= 7

    # Ensure lab numbers and consent were filtered out
    all_q_texts = " ".join(q.question_text for q in resp.questions).lower()
    import re
    assert re.search(r"\banc\b", all_q_texts) is None
    assert "platelet" not in all_q_texts
    assert "informed consent" not in all_q_texts
    assert "creatinine" not in all_q_texts


    # Check that demographic summary is pre-answered
    assert resp.pre_answered_demographics["minimum_age"] == "18 Years"
    assert resp.pre_answered_demographics["sex_restriction"] == "ALL"

    # Check favorable answers
    for q in resp.questions:
        if q.category == "INCLUSION":
            assert q.favorable_answer == "YES"
        elif q.category == "EXCLUSION":
            assert q.favorable_answer == "NO"
        assert set(q.options) == {"YES", "NO", "NOT_SURE"}


def test_evaluate_offline_questionnaire_eligible(sample_study):
    questionnaire = generate_offline_questions(sample_study)
    
    # Patient provides all favorable answers
    answers = {}
    for q in questionnaire.questions:
        answers[q.id] = q.favorable_answer

    result = evaluate_offline_questionnaire(sample_study, questionnaire.questions, answers)
    assert result.verdict == OverallEligibility.ELIGIBLE
    assert result.score >= 0.90
    assert "meet all major eligibility criteria" in result.summary.lower()
    assert len(result.criteria_evaluations) == len(questionnaire.questions)


def test_evaluate_offline_questionnaire_ineligible(sample_study):
    questionnaire = generate_offline_questions(sample_study)
    
    # Patient triggers an exclusion (e.g. Yes to brain metastases)
    answers = {}
    for q in questionnaire.questions:
        if "brain" in q.question_text.lower():
            answers[q.id] = "YES"  # Disqualifier!
        else:
            answers[q.id] = q.favorable_answer

    result = evaluate_offline_questionnaire(sample_study, questionnaire.questions, answers)
    assert result.verdict == OverallEligibility.INELIGIBLE
    assert result.score <= 0.30
    assert "ineligible" in result.summary.lower()


def test_evaluate_offline_questionnaire_uncertain(sample_study):
    questionnaire = generate_offline_questions(sample_study)
    
    # Patient is not sure on one question
    answers = {}
    for idx, q in enumerate(questionnaire.questions):
        if idx == 0:
            answers[q.id] = "NOT_SURE"
        else:
            answers[q.id] = q.favorable_answer

    result = evaluate_offline_questionnaire(sample_study, questionnaire.questions, answers)
    assert result.verdict == OverallEligibility.LIKELY_ELIGIBLE
    assert any("confirm with doctor" in item.lower() for item in result.doctor_checklist)
