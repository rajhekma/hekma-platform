"""Unit tests for OpenAI PHI detector with a mocked client."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.phi.openai_detector import OpenAIPhiDetector


def _mock_client(entities):
    content = json.dumps({"entities": entities})
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    response = SimpleNamespace(choices=[choice])
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=response)))
    )
    return client


@pytest.mark.asyncio
async def test_detect_aligns_spans_and_labels():
    """LLM mentions are remapped to source offsets with PHI labels."""
    text = "Patient Jane Doe (MRN 998877) has Type 2 diabetes."
    client = _mock_client(
        [
            {"entity": "PATIENT_NAME", "text": "Jane Doe", "confidence": 0.95},
            {"entity": "MEDICAL_RECORD_NUMBER", "text": "MRN 998877", "confidence": 0.9},
            {"entity": "DIAGNOSIS", "text": "Type 2 diabetes", "confidence": 0.88},
            {"entity": "NOT_A_TYPE", "text": "Jane Doe", "confidence": 0.99},
        ]
    )
    detector = OpenAIPhiDetector(api_key="sk-test", client=client)
    entities = await detector.detect(text)

    assert [e.entity for e in entities] == [
        "PATIENT_NAME",
        "MEDICAL_RECORD_NUMBER",
        "DIAGNOSIS",
    ]
    assert entities[0].text == "Jane Doe"
    assert text[entities[0].start : entities[0].end] == "Jane Doe"
    assert entities[0].label == "Patient Name"
    assert entities[0].category == "phi"
    assert entities[2].label == "Diagnosis"


@pytest.mark.asyncio
async def test_detect_respects_min_confidence():
    """Low-confidence entities are dropped."""
    text = "metformin 500mg"
    client = _mock_client(
        [{"entity": "MEDICATION", "text": "metformin 500mg", "confidence": 0.2}]
    )
    detector = OpenAIPhiDetector(api_key="sk-test", client=client)
    entities = await detector.detect(text, min_confidence=0.5)
    assert entities == []


def test_missing_api_key_raises():
    """Constructor rejects empty keys."""
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIPhiDetector(api_key="  ")
