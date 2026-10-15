"""Fallback detector when PHI is not configured."""

from __future__ import annotations

from typing import List

from api.services.phi.base import DetectedEntity, DetectorStatus, PhiDetector


class DisabledPhiDetector(PhiDetector):
    """Used when OpenAI is selected but no API key is present."""

    def __init__(self, detail: str) -> None:
        self._detail = detail

    @property
    def backend_name(self) -> str:
        return "disabled"

    def status(self) -> DetectorStatus:
        """Not ready — configuration missing."""
        return DetectorStatus(
            ready=False,
            backend=self.backend_name,
            detail=self._detail,
        )

    async def detect(self, text: str, min_confidence: float = 0.0) -> List[DetectedEntity]:
        """Fail closed until PHI is configured."""
        raise RuntimeError(self._detail)
