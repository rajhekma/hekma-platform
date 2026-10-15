"""Isolated tests for the main Trial Matching & Search router."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.trial_matching_api import router
from trialgpt_lite.schemas.match_result import PatientStudySummaryResponse, TermExplanation
from trialgpt_lite.schemas.study import TrialStudy


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_patient_summary_endpoint_success():
    client = _client()
    payload = PatientStudySummaryResponse(
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

    with patch("api.trial_matching_api.service.get_patient_study_summary", return_value=payload) as mock_get:
        response = client.get("/api/trials/NCT03443024/patient-summary")

    assert response.status_code == 200
    data = response.json()
    assert data["nct_id"] == "NCT03443024"
    assert data["plain_title"] == "Testing a New Injection for Eczema"
    assert data["complex_terms_explained"][0]["term"] == "Lebrikizumab"
    mock_get.assert_called_once_with("NCT03443024", force_refresh=False)


def test_patient_summary_rejects_invalid_nct_id():
    client = _client()
    with patch("api.trial_matching_api.service.get_patient_study_summary") as mock_get:
        response = client.get("/api/trials/not-an-nct/patient-summary")

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "ERR_NCT_ID_INVALID"
    mock_get.assert_not_called()


def test_existing_matching_routes_still_registered():
    client = _client()
    paths = set(client.app.openapi()["paths"])
    assert "/api/match" in paths
    assert "/api/trials/{nct_id}" in paths
    assert "/api/trials/{nct_id}/questionnaire" in paths
    assert "/api/trials/{nct_id}/evaluate-eligibility" in paths
    assert "/api/trials/{nct_id}/patient-summary" in paths
    assert "/api/cache/stats" in paths


def test_generic_trial_details_route_still_resolves():
    client = _client()
    study = TrialStudy(nct_id="NCT03443024", brief_title="Lebrikizumab Study")

    with patch("api.trial_matching_api.service.get_study_details", return_value=study) as mock_get:
        response = client.get("/api/trials/NCT03443024")

    assert response.status_code == 200
    assert response.json()["nct_id"] == "NCT03443024"
    mock_get.assert_called_once()


def test_match_request_openapi_schema_contains_city_and_radius():
    client = _client()
    schema = client.app.openapi()
    match_request_schema = schema["components"]["schemas"]["MatchRequest"]["properties"]
    assert "city_or_zip" in match_request_schema
    assert "search_radius_miles" in match_request_schema
    assert "geo_filter" in match_request_schema

    geo_filter_schema = schema["components"]["schemas"]["GeoFilter"]["properties"]
    assert "city_or_zip" in geo_filter_schema


def test_match_with_city_or_zip_resolves_and_calls_service():
    client = _client()
    from trialgpt_lite.schemas.match_result import ConditionMatchReport

    mock_report = ConditionMatchReport(
        searched_condition="melanoma",
        retrieved_trials_count=0,
        evaluated_trials_count=0,
        trials=[],
    )

    with patch("api.trial_matching_api.service.search_and_match", return_value=mock_report) as mock_match:
        response = client.post(
            "/api/match",
            json={
                "condition": "melanoma",
                "city_or_zip": "Boston, MA",
                "search_radius_miles": 25.0,
            },
        )

    assert response.status_code == 200
    mock_match.assert_called_once()
    req = mock_match.call_args[0][0]
    assert req.city_or_zip == "Boston, MA"
    assert req.geo_filter is not None
    assert req.geo_filter.latitude == 42.3601
    assert req.geo_filter.longitude == -71.0589
    assert req.geo_filter.radius_miles == 25.0
