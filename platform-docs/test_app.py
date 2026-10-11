from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_health_and_docs_page():
    assert client.get("/health").json()["service"] == "hekma-platform-docs"
    page = client.get("/docs")
    assert page.status_code == 200
    assert "All extracted services" in page.text
    assert "Patient Health" in page.text
    assert "Scanner" in page.text


def test_services_catalog_lists_extracted_and_legacy():
    data = client.get("/services").json()
    ids = {row["id"] for row in data["extracted"]}
    assert ids == {"patient-health", "scanner", "ai-usage"}
    names = {row["name"] for row in data["not_extracted"]}
    assert "Identity & Access" in names
    assert "CTMS" in names
