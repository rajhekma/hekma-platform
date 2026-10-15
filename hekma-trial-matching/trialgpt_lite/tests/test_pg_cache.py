"""
Unit tests for PostgreSQL Cache-Aside subsystem in TrialGPT Lite.
Tests query normalization, single-flight locking, fail-open resilience,
and Cache Miss vs. Cache Hit cycles.
"""

import time
from unittest.mock import MagicMock
import pytest

from trialgpt_lite.cache.pg_cache import (
    compute_query_hash,
    PostgreSQLCache,
)
from trialgpt_lite.service import TrialGPTLiteService
from trialgpt_lite.schemas.request import MatchRequest, PatientProfile
from trialgpt_lite.schemas.study import TrialStudy


def test_query_normalization_and_hash():
    """Ensure different whitespace and casing produce identical canonical hashes."""
    h1 = compute_query_hash("Lung Cancer", ["RECRUITING"], page_size=10)
    h2 = compute_query_hash("  lung   cancer  ", ["recruiting"], page_size=10)
    h3 = compute_query_hash("LUNG CANCER", ["RECRUITING"], page_size=10)
    h4 = compute_query_hash("breast cancer", ["RECRUITING"], page_size=10)

    assert h1 == h2
    assert h1 == h3
    assert h1 != h4


def test_status_sorting_in_hash():
    """Ensure different status order produces the same hash."""
    h1 = compute_query_hash("melanoma", ["RECRUITING", "ACTIVE_NOT_RECRUITING"])
    h2 = compute_query_hash("melanoma", ["ACTIVE_NOT_RECRUITING", "RECRUITING"])
    assert h1 == h2


def test_fail_open_when_disconnected():
    """Ensure cache operations fail open gracefully without raising exceptions."""
    # Initialize a cache with invalid connection parameters
    cache = PostgreSQLCache(
        host="invalid-host-999.local",
        port=5432,
        dbname="dummy",
        user="nobody",
        password="bad",
        enabled=True,
    )
    assert not cache._connected

    # Reads must return None or empty dict without error
    assert cache.get_cached_query("fakehash") is None
    assert cache.get_cached_study("NCT00000000") is None
    assert cache.get_cached_studies(["NCT00000000"]) == {}

    # Writes must return False/0 without error
    assert cache.set_cached_query("fakehash", "cond", 10, None, [], 0, None) is False
    assert cache.set_cached_study({"nct_id": "NCT00000000"}) is False
    assert cache.invalidate_study("NCT00000000") == 0


def test_service_cache_aside_lifecycle():
    """
    Test end-to-end Cache Miss -> Cache Hit -> Force Refresh flow.
    Uses an in-memory/mock cache to isolate service logic.
    """
    # Create in-memory mock cache
    mock_cache = MagicMock()
    stored_queries = {}
    stored_studies = {}

    def mock_get_query(q_hash, allow_expired=False):
        return stored_queries.get(q_hash)

    def mock_set_query(query_hash, condition_raw, page_size, page_token, nct_ids, total_in_registry, next_page_token, ttl_seconds=None):
        stored_queries[query_hash] = {
            "condition_raw": condition_raw,
            "page_size": page_size,
            "page_token": page_token,
            "nct_ids": nct_ids,
            "total_in_registry": total_in_registry,
            "next_page_token": next_page_token,
        }
        return True

    def mock_get_studies(nct_ids, allow_expired=False):
        return {nid: stored_studies[nid] for nid in nct_ids if nid in stored_studies}

    def mock_set_studies(studies_data, ttl_seconds=None):
        for s in studies_data:
            stored_studies[s["nct_id"]] = s
        return len(studies_data)

    def mock_get_study(nct_id, allow_expired=False):
        return stored_studies.get(nct_id)

    def mock_set_study(study_data, ttl_seconds=None):
        stored_studies[study_data["nct_id"]] = study_data
        return True

    import threading
    flight_lock = threading.Lock()
    mock_cache.get_flight_lock.return_value = flight_lock
    mock_cache.get_cached_query.side_effect = mock_get_query
    mock_cache.set_cached_query.side_effect = mock_set_query
    mock_cache.get_cached_studies.side_effect = mock_get_studies
    mock_cache.set_cached_studies.side_effect = mock_set_studies
    mock_cache.get_cached_study.side_effect = mock_get_study
    mock_cache.set_cached_study.side_effect = mock_set_study

    # Mock CT.gov client
    mock_client = MagicMock()
    mock_client.search_by_condition.return_value = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT12345678",
                        "briefTitle": "Phase 2 Trial for Non-Small Cell Lung Cancer",
                    },
                    "statusModule": {
                        "overallStatus": "RECRUITING",
                    },
                    "designModule": {
                        "studyType": "INTERVENTIONAL",
                        "phases": ["PHASE2"],
                    },
                    "conditionsModule": {
                        "conditions": ["Non-Small Cell Lung Cancer"],
                    },
                    "armsInterventionsModule": {
                        "interventions": [{"name": "Osimertinib", "type": "DRUG"}],
                    },
                    "eligibilityModule": {
                        "eligibilityCriteria": "Inclusion Criteria:\n- Age >= 18\nExclusion Criteria:\n- Prior treatment",
                        "minimumAge": "18 Years",
                        "sex": "ALL",
                    },
                }
            }
        ],
        "total_count": 1,
        "next_page_token": "TOKEN_PAGE2",
        "query_used": "non-small cell lung cancer",
    }

    service = TrialGPTLiteService(client=mock_client, cache=mock_cache)
    req = MatchRequest(condition="non-small cell lung cancer", page_size=10)

    # 1. First invocation: Cache Miss
    report_miss = service.search_and_match(req)
    assert not report_miss.cache_hit
    assert mock_client.search_by_condition.call_count == 1
    assert len(report_miss.trials) == 1
    assert report_miss.trials[0].nct_id == "NCT12345678"

    # Verify query and study were populated in cache
    assert len(stored_queries) == 1
    assert "NCT12345678" in stored_studies

    # 2. Second invocation: Cache Hit!
    report_hit = service.search_and_match(req)
    assert report_hit.cache_hit
    # Client should NOT have been called a second time
    assert mock_client.search_by_condition.call_count == 1
    assert len(report_hit.trials) == 1
    assert report_hit.trials[0].nct_id == "NCT12345678"

    # 3. Third invocation with force_refresh=True: Cache Bypass
    req_force = MatchRequest(condition="non-small cell lung cancer", page_size=10, force_refresh=True)
    report_force = service.search_and_match(req_force)
    assert not report_force.cache_hit
    # Client should be called again because cache was bypassed
    assert mock_client.search_by_condition.call_count == 2


def test_study_details_cache_aside():
    """Test get_study_details Cache Miss and Hit."""
    mock_cache = MagicMock()
    stored = {}
    mock_cache.get_cached_study.side_effect = lambda nid, allow_expired=False: stored.get(nid)
    mock_cache.set_cached_study.side_effect = lambda data, ttl_seconds=None: stored.update({data["nct_id"]: data})

    mock_client = MagicMock()
    mock_client.get_study.return_value = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT88888888",
                "briefTitle": "Detailed Study for Cache Test",
            },
            "statusModule": {"overallStatus": "RECRUITING"},
            "eligibilityModule": {
                "eligibilityCriteria": "Inclusion Criteria:\n- Age >= 18\nExclusion Criteria:\n- Pregnancy",
                "minimumAge": "18 Years",
                "sex": "ALL",
            },
        }
    }

    service = TrialGPTLiteService(client=mock_client, cache=mock_cache)

    # Miss
    study1 = service.get_study_details("NCT88888888")
    assert study1.nct_id == "NCT88888888"
    assert mock_client.get_study.call_count == 1
    assert "NCT88888888" in stored

    # Hit
    study2 = service.get_study_details("NCT88888888")
    assert study2.nct_id == "NCT88888888"
    # Should not call client again
    assert mock_client.get_study.call_count == 1


def test_30_day_ttl_configuration():
    """Verify that all caching tiers default to 30 days (2,592,000 seconds)."""
    from trialgpt_lite.config import PG_CACHE_QUERY_TTL, PG_CACHE_STUDY_TTL, PG_CACHE_MATCH_TTL, CACHE_RETENTION_DAYS
    assert CACHE_RETENTION_DAYS == 30
    assert PG_CACHE_QUERY_TTL == 30 * 86400
    assert PG_CACHE_STUDY_TTL == 30 * 86400
    assert PG_CACHE_MATCH_TTL == 30 * 86400


def test_patient_match_cache_lifecycle():
    """Verify that patient-level match reports are cached for 30 days and bypassable with force_refresh."""
    mock_cache = MagicMock()
    stored_matches = {}

    mock_cache.get_cached_match.side_effect = lambda h, allow_expired=False: stored_matches.get(h)
    def mock_set_match(match_hash, condition_raw, patient_profile, page_size, page_token, nct_ids, report_data, ttl_seconds=None):
        stored_matches[match_hash] = report_data
        return True
    mock_cache.set_cached_match.side_effect = mock_set_match

    import threading
    mock_cache.get_flight_lock.return_value = threading.Lock()
    mock_cache.get_cached_query_with_studies.return_value = None
    mock_cache.get_cached_query.return_value = None

    mock_client = MagicMock()
    mock_client.search_by_condition.return_value = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT55555555", "briefTitle": "Patient Match Test Study"},
                    "statusModule": {"overallStatus": "RECRUITING"},
                    "conditionsModule": {"conditions": ["Breast Cancer"]},
                    "eligibilityModule": {
                        "eligibilityCriteria": "Inclusion:\n- Age >= 18\nExclusion:\n- None",
                        "minimumAge": "18 Years",
                        "sex": "FEMALE",
                    }
                }
            }
        ],
        "total_count": 1,
        "next_page_token": None,
    }

    service = TrialGPTLiteService(client=mock_client, cache=mock_cache)
    patient = PatientProfile(age=45, sex="FEMALE", clinical_note="Stage 2 breast cancer patient.")
    req = MatchRequest(condition="Breast Cancer", patient=patient, page_size=10)

    # 1. First call: Miss -> stores in match cache
    res1 = service.search_and_match(req)
    assert not res1.cache_hit
    assert len(stored_matches) == 1
    assert mock_client.search_by_condition.call_count == 1

    # 2. Second call: Hit -> returns from match cache in ~2ms without calling client
    res2 = service.search_and_match(req)
    assert res2.cache_hit
    assert mock_client.search_by_condition.call_count == 1
    assert res2.trials[0].nct_id == "NCT55555555"

    # 3. Third call: Force refresh -> bypasses match cache
    req_force = MatchRequest(condition="Breast Cancer", patient=patient, page_size=10, force_refresh=True)
    res3 = service.search_and_match(req_force)
    assert not res3.cache_hit
    assert mock_client.search_by_condition.call_count == 2


def test_hydrates_participation_criteria_from_stale_cache():
    """Cached studies without eligibility text are refreshed from ClinicalTrials.gov."""
    import threading

    stale_study = TrialStudy(
        nct_id="NCT07463456",
        brief_title="Inter-Device Concordance of Plantar Thermal Asymmetry Measurement",
        overall_status="RECRUITING",
    ).model_dump()

    mock_cache = MagicMock()
    stored_studies = {"NCT07463456": stale_study}
    mock_cache.get_flight_lock.return_value = threading.Lock()
    mock_cache.get_cached_query_with_studies.return_value = (
        {
            "total_in_registry": 1,
            "next_page_token": None,
            "nct_ids": ["NCT07463456"],
        },
        [stale_study],
    )
    mock_cache.set_cached_studies.side_effect = lambda studies_data, ttl_seconds=None: stored_studies.update(
        {s["nct_id"]: s for s in studies_data}
    )

    mock_client = MagicMock()
    mock_client.get_study.return_value = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT07463456",
                "briefTitle": "Inter-Device Concordance of Plantar Thermal Asymmetry Measurement",
            },
            "statusModule": {"overallStatus": "RECRUITING"},
            "eligibilityModule": {
                "eligibilityCriteria": (
                    "Inclusion Criteria:\n"
                    "* Age 18 years or older.\n"
                    "* Confirmed diagnosis of type 1 or type 2 diabetes mellitus.\n"
                    "Exclusion Criteria:\n"
                    "* Active ulcers or open wounds in the plantar area."
                ),
                "minimumAge": "18 Years",
                "sex": "ALL",
            },
        }
    }

    service = TrialGPTLiteService(client=mock_client, cache=mock_cache)
    report = service.search_and_match(MatchRequest(condition="diabetes", page_size=10))

    assert mock_client.search_by_condition.call_count == 0
    assert mock_client.get_study.call_count == 1
    trial = report.trials[0]
    assert trial.nct_id == "NCT07463456"
    assert "Age 18 years or older" in trial.participation_criteria.inclusion_criteria[0]
    assert any("Active ulcers" in item for item in trial.participation_criteria.exclusion_criteria)
    assert "NCT07463456" in stored_studies
    assert stored_studies["NCT07463456"]["criteria"]["inclusion_criteria"]

