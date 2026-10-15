import pytest
from api.services.fhir_anonymizer import FHIRAnonymizer


@pytest.mark.asyncio
async def test_fhir_anonymize_patient():
    anonymizer = FHIRAnonymizer()
    patient_resource = {
        "resourceType": "Patient",
        "id": "patient-uuid-12345",
        "name": [
            {
                "family": "Smith",
                "given": ["Jane", "Marie"],
                "text": "Jane Marie Smith",
            }
        ],
        "telecom": [
            {"system": "phone", "value": "555-123-4567"},
            {"system": "email", "value": "jane.smith@example.com"},
        ],
        "address": [
            {
                "line": ["123 Main Street"],
                "city": "Boston",
                "postalCode": "02115",
                "state": "MA",
            }
        ],
        "identifier": [
            {"system": "http://hospital.org/mrn", "value": "MRN-998877"}
        ],
    }

    anon_patient, mappings = await anonymizer.anonymize_fhir_resource(
        patient_resource, org_id="test-org"
    )

    assert anon_patient["id"].startswith("PAT_")
    assert anon_patient["id"] != "patient-uuid-12345"
    assert anon_patient["name"][0]["family"].startswith("FAM_")
    assert anon_patient["name"][0]["family"] != "Smith"
    assert anon_patient["name"][0]["given"][0].startswith("GIVEN_")
    assert anon_patient["telecom"][0]["value"].startswith("PHONE_")
    assert anon_patient["telecom"][1]["value"].startswith("EMAIL_")
    assert anon_patient["address"][0]["postalCode"] == "021XX"
    assert anon_patient["address"][0]["line"] == ["[REDACTED STREET ADDRESS]"]
    assert len(mappings) > 0


@pytest.mark.asyncio
async def test_fhir_preserves_clinical_vocabularies():
    anonymizer = FHIRAnonymizer()
    observation_resource = {
        "resourceType": "Observation",
        "id": "obs-999",
        "status": "final",
        "subject": {"reference": "Patient/patient-uuid-12345"},
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "8480-6",
                    "display": "Systolic blood pressure",
                }
            ]
        },
        "valueQuantity": {
            "value": 120,
            "unit": "mmHg",
            "system": "http://unitsofmeasure.org",
            "code": "mm[Hg]",
        },
    }

    anon_obs, mappings = await anonymizer.anonymize_fhir_resource(
        observation_resource, org_id="test-org"
    )

    # Subject reference is anonymized
    assert anon_obs["subject"]["reference"].startswith("Patient/PAT_")

    # LOINC code and units are preserved untouched!
    assert anon_obs["code"]["coding"][0]["code"] == "8480-6"
    assert anon_obs["code"]["coding"][0]["display"] == "Systolic blood pressure"
    assert anon_obs["valueQuantity"]["value"] == 120
    assert anon_obs["valueQuantity"]["unit"] == "mmHg"
