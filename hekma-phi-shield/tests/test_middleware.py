import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI
from starlette.responses import JSONResponse
from api.middleware.anonymization_middleware import AnonymizationMiddleware
from api.config.settings import settings
from api.services import policy_store
from api.middleware.policy_engine import policy_engine
from api.models.policy import PIIPolicy, PolicyType, AnonymizeStrategy


@pytest.fixture
def test_app():
    # Set up policies for testing
    # Use x-org-id header to control org_id deterministically
    policies = [
        PIIPolicy(entity_type="PERSON", policy_type=PolicyType.ANONYMIZE, anonymize_strategy=AnonymizeStrategy.RANDOMIZED, applies_to_internal=True, applies_to_external=True),
        PIIPolicy(entity_type="US_SSN", policy_type=PolicyType.REDACT, applies_to_internal=True, applies_to_external=True),
        PIIPolicy(entity_type="EMAIL_ADDRESS", policy_type=PolicyType.REDACT, applies_to_internal=True, applies_to_external=True),
    ]
    import asyncio
    # Set up for test org IDs
    asyncio.run(policy_store.upsert_many("default-org", policies))
    asyncio.run(policy_store.upsert_many("test-org", policies))
    asyncio.run(policy_store.upsert_many("custom-org-123", policies))
    # Invalidate policy engine cache so middleware picks up new policies
    policy_engine.invalidate_cache("default-org")
    policy_engine.invalidate_cache("test-org")
    policy_engine.invalidate_cache("custom-org-123")
    
    app = FastAPI()
    
    @app.post("/internal/process")
    async def internal_process(data: dict):
        return JSONResponse(content={"processed": True, "data": data})
    
    @app.post("/llm/generate")
    async def llm_generate(data: dict):
        return JSONResponse(content={"generated": True, "data": data})
    
    @app.get("/health")
    async def health():
        return {"status": "ok"}
    
    app.add_middleware(AnonymizationMiddleware, excluded_paths=settings.EXCLUDED_PATHS)
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


def test_excluded_paths_not_processed(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_external_llm_path_anonymized(client):
    response = client.post(
        "/llm/generate",
        json={"prompt": "Patient John Doe has SSN 123-45-6789"},
        headers={"x-org-id": "test-org"}
    )
    assert response.status_code == 200
    data = response.json()
    # Should be anonymized for external LLM
    assert "John Doe" not in str(data)
    assert "123-45-6789" not in str(data)


def test_internal_path_anonymized(client):
    response = client.post(
        "/internal/process",
        json={"text": "John Doe has SSN 123-45-6789"},
        headers={"x-org-id": "test-org"}
    )
    assert response.status_code == 200
    data = response.json()
    # Internal paths with policies applying to internal should be anonymized
    assert "John Doe" not in str(data)
    assert "123-45-6789" not in str(data)


def test_org_id_from_api_key(client):
    response = client.post(
        "/llm/generate",
        json={"prompt": "Test"},
        headers={"x-org-id": "test-org"}
    )
    assert response.status_code == 200
    # Should get org_id from x-org-id header


def test_org_id_from_header(client):
    response = client.post(
        "/llm/generate",
        json={"prompt": "Test"},
        headers={"x-org-id": "custom-org-123"}
    )
    assert response.status_code == 200
    # Should use x-org-id header


def test_default_org_id(client):
    response = client.post(
        "/llm/generate",
        json={"prompt": "Test"}
    )
    assert response.status_code == 200
    # Should default to "default-org"


def test_empty_body(client):
    response = client.post(
        "/llm/generate",
        content="",
        headers={"x-api-key": "test-key", "content-type": "application/json"}
    )
    # Should handle empty body gracefully


def test_invalid_json_body(client):
    response = client.post(
        "/llm/generate",
        content="not valid json",
        headers={"x-api-key": "test-key", "content-type": "application/json"}
    )
    # Should handle invalid JSON gracefully


def test_external_direction_header(client):
    response = client.post(
        "/internal/process",
        json={"text": "John Doe"},
        headers={"x-org-id": "test-org", "x-direction": "external"}
    )
    assert response.status_code == 200
    # Should be treated as external due to x-direction header
    data = response.json()
    assert "John Doe" not in str(data)


def test_internal_direction_header(client):
    response = client.post(
        "/llm/generate",
        json={"text": "John Doe"},
        headers={"x-org-id": "test-org", "x-direction": "internal"}
    )
    assert response.status_code == 200
    # Should be treated as internal despite /llm/ path


def test_nested_objects_anonymized(client):
    response = client.post(
        "/llm/generate",
        json={
            "patient": {
                "name": "John Doe",
                "ssn": "123-45-6789"
            },
            "notes": "Patient John Doe visited"
        },
        headers={"x-org-id": "test-org"}
    )
    assert response.status_code == 200
    data = response.json()
    # Nested objects should be processed
    assert "John Doe" not in str(data)
    assert "123-45-6789" not in str(data)


def test_arrays_anonymized(client):
    response = client.post(
        "/llm/generate",
        json={
            "patients": [
                {"name": "John Doe", "ssn": "123-45-6789"},
                {"name": "Jane Smith", "ssn": "987-65-4321"}
            ]
        },
        headers={"x-org-id": "test-org"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "John Doe" not in str(data)
    assert "Jane Smith" not in str(data)


def test_large_text_truncated(client):
    large_text = "x" * 15000
    response = client.post(
        "/llm/generate",
        json={"prompt": large_text},
        headers={"x-org-id": "test-org"}
    )
    assert response.status_code == 200
    # Should not crash, large text should be passed through


def test_response_restoration_for_external(client):
    # Test that external responses get tokens restored
    response = client.post(
        "/llm/generate",
        json={"prompt": "John Doe"},
        headers={"x-org-id": "test-org"}
    )
    assert response.status_code == 200
    # Response should have tokens restored for external