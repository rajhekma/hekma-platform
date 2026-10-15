from typing import List
import asyncio


class Entity:
    def __init__(self, entity: str, text: str, start: int, end: int, confidence: float):
        self.entity = entity
        self.text = text
        self.start = start
        self.end = end
        self.confidence = confidence


class EntityDetector:
    def __init__(self, min_confidence: float = 0.5):
        self.min_confidence = min_confidence

    async def detect(self, text: str) -> List[Entity]:
        from api.main import detect_entities
        entities = await detect_entities(text, self.min_confidence)
        return [
            Entity(
                entity=e["entity"],
                text=e["text"],
                start=e["start"],
                end=e["end"],
                confidence=e["confidence"]
            )
            for e in entities
        ]


entity_detector = EntityDetector()