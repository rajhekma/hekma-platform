"""
Tests for Patient Study Summary generation and caching powered by Groq LPU.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from trialgpt_lite.app import app
from trialgpt_lite.schemas.study import TrialStudy
from trialgpt_lite.schemas.match_result import PatientStudySummaryResponse, TermExplanation
from trialgpt_lite.parser.groq_rephraser import generate_patient_study_summary
from trialgpt_lite.service import TrialGPTLiteService


@pytest.fixture
def mock_study():
    return TrialStudy(
        nct_id="NCT03443024",
        brief_title="A Study of Lebrikizumab (LY3650150) in Participants With Moderate-to-Severe Atopic Dermatitis",
        official_title="A Randomized, Double-Blind, Placebo-Controlled Trial of Lebrikizumab",
        conditions=["Atopic Dermatitis", "Eczema"],
        interventions=["BIOLOGICAL: Lebrikizumab", "DRUG: Placebo"],
        phases=["PHASE2"],
        brief_summary="This study evaluates the safety and efficacy of lebrikizumab in patients with atopic dermatitis.",
    )


def test_patient_study_summary_schema():
    term = TermExplanation(term="Lebrikizumab", plain_english="A targeted eczema antibody medication.")
    assert term.term == "Lebrikizumab"
    assert "eczema" in term.plain_english

    summary = PatientStudySummaryResponse(
        nct_id="NCT03443024",
        trial_title="Lebrikizumab Study",
        plain_title="Testing a New Injection to Help With Eczema",
        what_this_study_is_about="Testing if a new medicine helps severe skin itching.",
        treatment_and_how_it_works="Lebrikizumab blocks proteins causing inflammation.",
        what_participation_involves="Clinic visits every 2 weeks.",
        who_can_join_overview="Adults with severe eczema.",
        plain_inclusions=["Must be 18 years or older.", "Diagnosed with eczema for 1+ year."],
        plain_exclusions=["Currently taking oral steroid pills."],
        complex_terms_explained=[term],
        engine="GROQ",
        cached=False,
    )
    assert summary.nct_id == "NCT03443024"
    assert len(summary.complex_terms_explained) == 1
    assert len(summary.plain_inclusions) == 2
    assert len(summary.plain_exclusions) == 1
    assert summary.engine == "GROQ"


def test_generate_patient_study_summary_mocked(mock_study):
    mock_json = """
    {
      "plain_title": "Testing a New Injection (Lebrikizumab) to Help Calm Down Severe Eczema",
      "what_this_study_is_about": "This study tests whether lebrikizumab can reduce severe eczema flare-ups.",
      "treatment_and_how_it_works": "Lebrikizumab is an antibody injection targeting inflammation.",
      "what_participation_involves": "Regular clinic check-ups and injections over 12 weeks.",
      "who_can_join_overview": "Adults age 18+ with long-term moderate-to-severe eczema.",
      "plain_inclusions": ["Must be age 18 or older.", "Diagnosed with moderate-to-severe eczema."],
      "plain_exclusions": ["Taking strong immune suppressants."],
      "complex_terms_explained": [
        {"term": "Lebrikizumab", "plain_english": "A targeted injection drug for skin inflammation."},
        {"term": "Atopic Dermatitis", "plain_english": "The medical term for eczema."}
      ]
    }
    """
    mock_choice = MagicMock()
    mock_choice.message.content = mock_json

    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]

    with patch("groq.Groq") as mock_groq_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        mock_groq_class.return_value = mock_client

        res = generate_patient_study_summary(mock_study)
        assert res.nct_id == "NCT03443024"
        assert "Lebrikizumab" in res.plain_title
        assert len(res.plain_inclusions) == 2
        assert len(res.plain_exclusions) == 1
        assert len(res.complex_terms_explained) == 2
        assert res.complex_terms_explained[0].term == "Lebrikizumab"
        assert res.engine == "GROQ"


def test_service_get_patient_study_summary_caching(mock_study):
    service = TrialGPTLiteService()
    service.cache = MagicMock()
    service.get_study_details = MagicMock(return_value=mock_study)

    # 1. Cache Miss
    service.cache.get_cached_summary.return_value = None

    with patch("trialgpt_lite.service.generate_patient_study_summary") as mock_gen:
        mock_gen.return_value = PatientStudySummaryResponse(
            nct_id="NCT03443024",
            trial_title="Test Title",
            plain_title="Plain Title",
            what_this_study_is_about="About",
            treatment_and_how_it_works="Treatment",
            what_participation_involves="Involves",
            who_can_join_overview="Who",
            complex_terms_explained=[],
            engine="GROQ",
            cached=False,
        )

        res1 = service.get_patient_study_summary("NCT03443024")
        assert res1.engine == "GROQ"
        assert res1.cached is False
        service.cache.set_cached_summary.assert_called_once()

    # 2. Cache Hit
    service.cache.get_cached_summary.return_value = {
        "nct_id": "NCT03443024",
        "trial_title": "Test Title",
        "plain_title": "Cached Plain Title",
        "what_this_study_is_about": "About",
        "treatment_and_how_it_works": "Treatment",
        "what_participation_involves": "Involves",
        "who_can_join_overview": "Who",
        "complex_terms_explained": [],
        "engine": "GROQ",
        "cached": False,
        "execution_time_ms": 100,
    }

    res2 = service.get_patient_study_summary("NCT03443024")
    assert res2.cached is True
    assert res2.engine == "CACHE_HIT"
    assert res2.plain_title == "Cached Plain Title"


def test_api_patient_summary_endpoint(mock_study):
    client = TestClient(app)

    with patch("trialgpt_lite.app.service.get_patient_study_summary") as mock_get:
        mock_get.return_value = PatientStudySummaryResponse(
            nct_id="NCT03443024",
            trial_title="A Study of Lebrikizumab",
            plain_title="Testing a New Injection for Eczema",
            what_this_study_is_about="Testing eczema relief.",
            treatment_and_how_it_works="Works by targeting skin swelling.",
            what_participation_involves="Attending clinic visits.",
            who_can_join_overview="Adults with eczema.",
            complex_terms_explained=[
                TermExplanation(term="Lebrikizumab", plain_english="A targeted prescription medicine.")
            ],
            engine="GROQ",
            cached=False,
            execution_time_ms=250,
        )

        response = client.get("/api/trials/NCT03443024/patient-summary")
        assert response.status_code == 200
        data = response.json()
        assert data["nct_id"] == "NCT03443024"
        assert data["plain_title"] == "Testing a New Injection for Eczema"
        assert len(data["complex_terms_explained"]) == 1
        assert data["complex_terms_explained"][0]["term"] == "Lebrikizumab"
