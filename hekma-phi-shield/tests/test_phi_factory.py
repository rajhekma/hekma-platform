"""Unit tests for PHI detector factory selection."""

from types import SimpleNamespace

from api.services.phi.disabled_detector import DisabledPhiDetector
from api.services.phi.factory import PhiDetectorFactory
from api.services.phi.local_detector import LocalPhiDetector
from api.services.phi.openai_detector import OpenAIPhiDetector


def _settings(**overrides):
    base = {
        "PHI_DETECTOR_BACKEND": "openai",
        "OPENAI_API_KEY": "",
        "OPENAI_PHI_MODEL": "gpt-4o-mini",
        "OPENAI_TIMEOUT_SECONDS": 30.0,
        "PHI_LOCAL_MODEL_PATH": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_factory_openai_without_key_is_disabled():
    """Missing API key must fail closed with a disabled detector."""
    detector = PhiDetectorFactory().create(_settings(OPENAI_API_KEY=""))
    assert isinstance(detector, DisabledPhiDetector)
    assert detector.status().ready is False


def test_factory_openai_with_key():
    """Valid key selects the OpenAI implementation."""
    detector = PhiDetectorFactory().create(_settings(OPENAI_API_KEY="sk-test"))
    assert isinstance(detector, OpenAIPhiDetector)
    assert detector.status().ready is True
    assert detector.status().model == "gpt-4o-mini"


def test_factory_local_backend():
    """local backend returns the stub for the future trained model."""
    detector = PhiDetectorFactory().create(
        _settings(PHI_DETECTOR_BACKEND="local", PHI_LOCAL_MODEL_PATH="/tmp/phi")
    )
    assert isinstance(detector, LocalPhiDetector)
    assert detector.status().ready is False
