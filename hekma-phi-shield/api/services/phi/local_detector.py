"""Placeholder for a future fine-tuned local PHI model."""

from __future__ import annotations

from typing import List

from api.services.phi.base import DetectedEntity, DetectorStatus, PhiDetector


class LocalPhiDetector(PhiDetector):
    """Reserved backend for the upcoming trained PHI model."""

    def __init__(self, model_path: str = "") -> None:
        self._model_path = model_path

    @property
    def backend_name(self) -> str:
        return "local"

    def status(self) -> DetectorStatus:
        """Local PHI model is not shipped yet."""
        return DetectorStatus(
            ready=False,
            backend=self.backend_name,
            model=self._model_path or None,
            detail="Local PHI model is not trained yet. Use PHI_DETECTOR_BACKEND=openai.",
        )

    async def detect(self, text: str, min_confidence: float = 0.0) -> List[DetectedEntity]:
        """Reject until a trained local model is wired in."""
        raise RuntimeError(
            "Local PHI detector is not available yet. "
            "Set PHI_DETECTOR_BACKEND=openai and OPENAI_API_KEY in .env."
        )
