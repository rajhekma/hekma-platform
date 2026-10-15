"""Detector contract for PHI extraction (OpenAI now, local model later)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DetectedEntity:
    """Normalized entity span shared by all PHI detectors."""

    entity: str
    text: str
    start: int
    end: int
    confidence: float
    category: str = "phi"
    label: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize for API responses."""
        return {
            "entity": self.entity,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence,
            "category": self.category,
            "label": self.label,
        }


@dataclass
class DetectorStatus:
    """Runtime readiness for /health and UI badges."""

    ready: bool
    backend: str
    detail: Optional[str] = None
    model: Optional[str] = None


class PhiDetector(ABC):
    """Abstract PHI detector; swap implementations without changing API routes."""

    @abstractmethod
    async def detect(self, text: str, min_confidence: float = 0.0) -> List[DetectedEntity]:
        """Find PHI spans in text."""

    @abstractmethod
    def status(self) -> DetectorStatus:
        """Return whether this detector can serve requests."""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Stable backend id (openai, local, stub)."""
