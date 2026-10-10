from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.pricing import ModelPrice
from app.repository import InMemoryUsageRepository

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
PRICES = [
    ModelPrice(
        provider="openai",
        model="gpt-4o",
        input_usd_per_1m=Decimal("2.5"),
        output_usd_per_1m=Decimal("10"),
        effective_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
    ),
    ModelPrice(
        provider="anthropic",
        model="claude-sonnet-4-6",
        input_usd_per_1m=Decimal("3"),
        output_usd_per_1m=Decimal("15"),
        effective_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
    ),
]


def _client() -> TestClient:
    repo = InMemoryUsageRepository(PRICES)
    app = create_app(
        repo=repo,
        settings=Settings(ai_cost_api_key=None, ai_usage_sqs_enabled=False),
        start_sqs=False,
    )
    return TestClient(app)


def _event(**overrides):
    body = {
        "schema_version": 1,
        "request_id": str(uuid4()),
        "occurred_at": NOW.isoformat(),
        "tenant_id": 1,
        "patient_id": "203664",
        "product": "scan_ai",
        "feature": "smart_scan.allergies",
        "provider": "openai",
        "model": "gpt-4o",
        "prompt_tokens": 4000,
        "completion_tokens": 400,
        "source_service": "hekma-core",
    }
    body.update(overrides)
    return body


def test_ingest_and_patient_cost_breakdown():
    client = _client()
    scan = client.post("/internal/v1/ai-usage/events", json=_event())
    assert scan.status_code == 200
    assert scan.json()["accepted"] is True
    assert scan.json()["duplicate"] is False
    assert scan.json()["pricing_status"] == "priced"

    claude = client.post(
        "/internal/v1/ai-usage/events",
        json=_event(
            request_id=str(uuid4()),
            product="trial_match",
            feature="trial_match.matching",
            provider="claude",
            model="claude-sonnet-4-6",
            prompt_tokens=10000,
            completion_tokens=2000,
            source_service="hekma-trialgpt",
        ),
    )
    assert claude.status_code == 200

    summary = client.post(
        "/internal/v1/ai-usage/events",
        json=_event(
            request_id=str(uuid4()),
            product="patient_summary",
            feature="patient_summary.overview",
            prompt_tokens=1000,
            completion_tokens=200,
        ),
    )
    assert summary.status_code == 200

    cost = client.get("/v1/patients/203664/ai-cost")
    assert cost.status_code == 200
    body = cost.json()
    assert body["patient_id"] == "203664"
    assert body["totals"]["llm_calls"] == 3
    assert body["totals"]["prompt_tokens"] == 15000
    assert body["totals"]["completion_tokens"] == 2600
    products = {row["product"]: row for row in body["by_product"]}
    assert set(products) == {"scan_ai", "trial_match", "patient_summary"}
    providers = {row["provider"]: row for row in body["by_provider"]}
    assert "openai" in providers
    assert "anthropic" in providers
    assert providers["anthropic"]["models"][0]["model"] == "claude-sonnet-4-6"


def test_duplicate_request_id_is_idempotent():
    client = _client()
    rid = str(uuid4())
    first = client.post("/internal/v1/ai-usage/events", json=_event(request_id=rid))
    second = client.post("/internal/v1/ai-usage/events", json=_event(request_id=rid))
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    cost = client.get("/v1/patients/203664/ai-cost").json()
    assert cost["totals"]["llm_calls"] == 1


def test_cached_event_is_dropped():
    client = _client()
    resp = client.post("/internal/v1/ai-usage/events", json=_event(cached=True))
    assert resp.json()["accepted"] is False
    cost = client.get("/v1/patients/203664/ai-cost").json()
    assert cost["totals"]["llm_calls"] == 0


def test_product_filter_and_event_drilldown():
    client = _client()
    client.post("/internal/v1/ai-usage/events", json=_event())
    client.post(
        "/internal/v1/ai-usage/events",
        json=_event(request_id=str(uuid4()), product="patient_summary"),
    )
    filtered = client.get("/v1/patients/203664/ai-cost", params={"product": "scan_ai"}).json()
    assert filtered["totals"]["llm_calls"] == 1
    assert filtered["by_product"][0]["product"] == "scan_ai"

    events = client.get("/v1/patients/203664/ai-cost/events").json()
    assert events["total"] == 2
    assert len(events["events"]) == 2


def test_unknown_patient_returns_zero_totals():
    client = _client()
    body = client.get("/v1/patients/missing/ai-cost").json()
    assert body["totals"]["llm_calls"] == 0
    assert body["by_product"] == []
    assert body["by_provider"] == []


def test_health():
    client = _client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
