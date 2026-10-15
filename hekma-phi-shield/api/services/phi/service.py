"""Orchestrates PHI detect / validate / mask against a PhiDetector."""

from __future__ import annotations

from typing import List, Optional, Sequence

from api.services.phi.base import DetectedEntity, DetectorStatus, PhiDetector
from api.services.phi.types import PHI_ENTITY_TYPES, PHI_ENTITY_TYPE_NAMES, label_for


class PhiDetectionService:
    """Application service for PHI API routes."""

    def __init__(self, detector: PhiDetector) -> None:
        self._detector = detector

    @property
    def detector(self) -> PhiDetector:
        return self._detector

    def status(self) -> DetectorStatus:
        """Delegate readiness to the configured detector."""
        return self._detector.status()

    def list_entity_types(self) -> List[dict]:
        """Return PHI types with display labels for the UI catalog."""
        return [
            {
                "entity": t.name,
                "label": t.label,
                "description": t.description,
                "category": "phi",
            }
            for t in PHI_ENTITY_TYPES
        ]

    def entity_type_names(self) -> List[str]:
        """Machine names used by filters and admin policies."""
        return list(PHI_ENTITY_TYPE_NAMES)

    async def predict(
        self,
        text: str,
        min_confidence: float = 0.0,
    ) -> List[dict]:
        """Detect PHI and return API-ready entity dicts."""
        entities = await self._detector.detect(text, min_confidence=min_confidence)
        return [self._enrich(e) for e in entities]

    async def validate(
        self,
        text: str,
        entity_types: Optional[Sequence[str]] = None,
        min_confidence: float = 0.0,
    ) -> List[dict]:
        """Detect PHI, optionally filtered to selected types."""
        entities = await self.predict(text, min_confidence=min_confidence)
        if entity_types:
            allowed = {t.upper() for t in entity_types}
            entities = [e for e in entities if e["entity"] in allowed]
        return entities

    async def predict_batch(
        self,
        texts: Sequence[str],
        min_confidence: float = 0.0,
    ) -> List[dict]:
        """Run PHI detection on multiple texts."""
        results = []
        for text in texts:
            entities = await self.predict(text, min_confidence=min_confidence)
            results.append(
                {
                    "text": text,
                    "entities": entities,
                    "entity_count": len(entities),
                    "contains_phi": len(entities) > 0,
                }
            )
        return results

    async def anonymize(
        self,
        text: str,
        min_confidence: float = 0.0,
        mask_style: str = "type",
    ) -> tuple[str, List[dict]]:
        """Detect PHI and return redacted text plus mapping summary."""
        entities = await self.predict(text, min_confidence=min_confidence)
        anonymized = self.mask(text, entities, style=mask_style)
        mappings = []
        for ent in entities:
            if mask_style == "type":
                token = f"[{ent['entity']}]"
            elif mask_style == "placeholder":
                token = "<REDACTED>"
            else:
                token = "*" * max(0, ent["end"] - ent["start"])
            mappings.append(
                {
                    "entity_type": ent["entity"],
                    "label": ent.get("label") or label_for(ent["entity"]),
                    "original_value": ent["text"],
                    "tokenized_value": token,
                    "policy_applied": "redact",
                }
            )
        return anonymized, mappings

    def mask(self, text: str, entities: List[dict], style: str = "type") -> str:
        """Redact PHI spans using the same styles as the PII mask endpoint."""
        if not entities:
            return text
        ordered = sorted(entities, key=lambda e: e["start"])
        pieces: List[str] = []
        cursor = 0
        for ent in ordered:
            pieces.append(text[cursor : ent["start"]])
            if style == "type":
                pieces.append(f"[{ent['entity']}]")
            elif style == "placeholder":
                pieces.append("<REDACTED>")
            elif style == "ignore":
                pieces.append(text[ent["start"] : ent["end"]])
            else:
                pieces.append("*" * max(0, ent["end"] - ent["start"]))
            cursor = ent["end"]
        pieces.append(text[cursor:])
        return "".join(pieces)

    @staticmethod
    def _enrich(entity: DetectedEntity) -> dict:
        """Ensure label/category are always present on API entities."""
        data = entity.to_dict()
        if not data.get("label"):
            data["label"] = label_for(data["entity"])
        data["category"] = "phi"
        return data
