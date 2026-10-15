import pytest
from starlette.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_and_healthz(client):
    r1 = client.get("/health")
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["status"] in ("ok", "degraded")
    assert "domain" in data1

    r2 = client.get("/healthz")
    assert r2.status_code == 200


def test_readiness_probe(client):
    r = client.get("/ready")
    assert r.status_code == 200
    data = r.json()
    assert data["ready"] is True
    assert data["model_warm"] is True


def test_prometheus_metrics(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "http_requests_total" in r.text


def test_unified_anonymize_endpoint(client):
    r = client.post(
        "/anonymize",
        json={"text": "Patient John Doe visited the hospital today."},
    )
    assert r.status_code == 200
    data = r.json()
    assert "anonymized_text" in data
    assert "entities" in data
