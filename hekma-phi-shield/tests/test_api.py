import json
import pytest
from starlette.testclient import TestClient

from api.main import app

TEST_TEXT = (
    "Afton574 Casper496 is a white female born on September 9, 1922, whose mother’s maiden name is Leonia336 Gaylord332. "
    "She is never married, resides at 183 Hagenes Stravenue Suite 78 in Plymouth, Massachusetts (postal code 02360), and speaks English. "
    "Her medical record number is b7672a45-fe62-d8e3-9721-809e3ede1700, and she has a Social Security Number of 999-91-1291, "
    "a driver’s license number of S99944180, and a passport number of X35482474X. She has received care primarily from Dr. Isaac321 Kub800 "
    "at Plymouth Carver Primary Care, P.C., and her insurance is provided by Medicaid, Medicare, and Dual Eligible programs."
)


def test_api():
    with TestClient(app) as client:
        response = client.post("/predict", json={"text": TEST_TEXT})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        output = response.json()

        entities = output.get("entities", [])
        assert output.get("contains_pii") is True, "Expected contains_pii=True"
        assert len(entities) > 0, "Expected at least one entity"

        def has_entity(etype, substring):
            return any(e["entity"] == etype and substring in e["text"] for e in entities)

        def entity_not_tagged_as(substring, wrong_type):
            return not any(e["entity"] == wrong_type and substring in e["text"] for e in entities)

        errors = []

        # Expected entities must be detected
        expected = [
            ("PERSON", "Afton574 Casper496"),
            ("PERSON", "Leonia336 Gaylord332"),
            ("GENDER", "female"),
            ("DATE", "September 9, 1922"),
            ("US_SSN", "999-91-1291"),
            ("US_DRIVER_LICENSE", "S99944180"),
            ("US_PASSPORT", "X35482474X"),
        ]
        for etype, text_substr in expected:
            if not has_entity(etype, text_substr):
                errors.append(f"FN: Expected {etype} for '{text_substr}' but not found")

        # False Positive prevention
        fp_checks = [
            ("white", "GENDER", "white should be RACE not GENDER"),
            ("English", "RACE", "English is a language not RACE"),
            ("b7672a45-fe62-d8e3-9721-809e3ede1700", "US_DRIVER_LICENSE", "MRN UUID is not a DL"),
            ("b7672a45-fe62-d8e3-9721-809e3ede1700", "US_SSN", "MRN UUID is not SSN"),
            ("X35482474X", "US_SSN", "Passport should be US_PASSPORT not US_SSN"),
        ]
        for text_substr, wrong_type, msg in fp_checks:
            if not entity_not_tagged_as(text_substr, wrong_type):
                errors.append(f"FP: {msg}")

        assert len(errors) == 0, f"Assertion failures: {errors}"
