"""Unit tests for PhiDetectionService orchestration."""

from __future__ import annotations

import pytest

from api.services.phi.base import DetectedEntity, DetectorStatus, PhiDetector
from api.services.phi.service import PhiDetectionService


class FakeDetector(PhiDetector):
    def __init__(self, entities):
        self._entities = entities

    @property
    def backend_name(self) -> str:
        return "fake"

    def status(self) -> DetectorStatus:
        return DetectorStatus(ready=True, backend="fake", model="fake")

    async def detect(self, text: str, min_confidence: float = 0.0):
        return [
            e
            for e in self._entities
            if e.confidence >= min_confidence and e.text in text
        ]


@pytest.mark.asyncio
async def test_validate_filters_entity_types():
    """Validate keeps only requested PHI types."""
    detector = FakeDetector(
        [
            DetectedEntity("DIAGNOSIS", "diabetes", 0, 8, 0.9, label="Diagnosis"),
            DetectedEntity("MEDICATION", "metformin", 9, 18, 0.9, label="Medication"),
        ]
    )
    service = PhiDetectionService(detector)
    entities = await service.validate("diabetes metformin", entity_types=["DIAGNOSIS"])
    assert len(entities) == 1
    assert entities[0]["entity"] == "DIAGNOSIS"
    assert entities[0]["label"] == "Diagnosis"


def test_mask_type_style():
    """Mask replaces spans with [ENTITY] tokens."""
    service = PhiDetectionService(FakeDetector([]))
    text = "Patient has diabetes"
    entities = [{"entity": "DIAGNOSIS", "start": 12, "end": 20}]
    assert service.mask(text, entities, style="type") == "Patient has [DIAGNOSIS]"


@pytest.mark.asyncio
async def test_predict_batch_returns_per_text_results():
    """Batch returns one result dict per input line."""
    detector = FakeDetector(
        [
            DetectedEntity("DIAGNOSIS", "diabetes", 0, 8, 0.9, label="Diagnosis"),
        ]
    )
    service = PhiDetectionService(detector)
    results = await service.predict_batch(["diabetes note", "clean note"])
    assert len(results) == 2
    assert results[0]["contains_phi"] is True
    assert results[1]["contains_phi"] is False


@pytest.mark.asyncio
async def test_anonymize_returns_mappings():
    """Anonymize redacts text and returns mapping rows."""
    detector = FakeDetector(
        [DetectedEntity("MEDICATION", "metformin", 0, 9, 0.9, label="Medication")]
    )
    service = PhiDetectionService(detector)
    text, mappings = await service.anonymize("metformin daily", mask_style="type")
    assert text == "[MEDICATION] daily"
    assert mappings[0]["original_value"] == "metformin"
    assert mappings[0]["tokenized_value"] == "[MEDICATION]"


def test_list_entity_types_includes_labels():
    """Catalog entries expose human-readable PHI labels."""
    service = PhiDetectionService(FakeDetector([]))
    types = service.list_entity_types()
    names = {t["entity"] for t in types}
    assert "MEDICAL_RECORD_NUMBER" in names
    mrn = next(t for t in types if t["entity"] == "MEDICAL_RECORD_NUMBER")
    assert mrn["label"] == "MRN"
    assert mrn["category"] == "phi"
