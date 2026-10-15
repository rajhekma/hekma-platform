"""OpenAI-backed PHI detector (temporary until a local model is trained)."""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional, Set, Tuple

from api.services.phi.base import DetectedEntity, DetectorStatus, PhiDetector
from api.services.phi.span_resolver import SpanResolver
from api.services.phi.types import PHI_ENTITY_TYPE_NAMES, label_for

logger = logging.getLogger("phi-openai")

SYSTEM_PROMPT = """You are a clinical PHI (Protected Health Information) extraction engine.
Extract PHI spans from the user text for HIPAA / healthcare compliance.

Return ONLY valid JSON with this shape:
{{
  "entities": [
    {{
      "entity": "<TYPE from the allowed list>",
      "text": "<exact substring from the input>",
      "start": <optional character offset if known>,
      "confidence": <0.0-1.0>
    }}
  ]
}}

Rules:
- Use ONLY these entity types: {types}
- `text` MUST be copied exactly from the input (same spelling/casing).
- Prefer clinical PHI: diagnoses, medications, procedures, MRNs, DOB, providers, facilities.
- Do not invent spans that are not present.
- If nothing is found, return {{"entities": []}}.
"""


class OpenAIPhiDetector(PhiDetector):
    """Calls OpenAI chat completions with JSON output for PHI NER."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 45.0,
        client: Any = None,
        span_resolver: Optional[SpanResolver] = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("OPENAI_API_KEY is required for the OpenAI PHI detector")
        self._api_key = api_key.strip()
        self._model = model
        self._timeout = timeout_seconds
        self._client = client
        self._resolver = span_resolver or SpanResolver()

    @property
    def backend_name(self) -> str:
        return "openai"

    def status(self) -> DetectorStatus:
        """OpenAI backend is ready when an API key is configured."""
        return DetectorStatus(
            ready=True,
            backend=self.backend_name,
            model=self._model,
            detail=None,
        )

    def _get_client(self) -> Any:
        """Lazy-create the OpenAI client so imports stay optional until used."""
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai package is not installed. Run: pip install openai"
            ) from exc
        self._client = AsyncOpenAI(api_key=self._api_key, timeout=self._timeout)
        return self._client

    async def detect(self, text: str, min_confidence: float = 0.0) -> List[DetectedEntity]:
        """Ask OpenAI for PHI spans, then re-align offsets against source text."""
        client = self._get_client()
        allowed = ", ".join(PHI_ENTITY_TYPE_NAMES)
        system = SYSTEM_PROMPT.format(types=allowed)
        response = await client.chat.completions.create(
            model=self._model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
        )
        content = response.choices[0].message.content or "{}"
        raw_entities = self._parse_entities(content)
        return self._materialize(text, raw_entities, min_confidence)

    def _parse_entities(self, content: str) -> List[dict]:
        """Parse model JSON; tolerate minor shape drift."""
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("OpenAI PHI response was not valid JSON")
            return []
        entities = payload.get("entities", [])
        if not isinstance(entities, list):
            return []
        return [e for e in entities if isinstance(e, dict)]

    def _materialize(
        self,
        text: str,
        raw_entities: List[dict],
        min_confidence: float,
    ) -> List[DetectedEntity]:
        """Convert raw LLM entities into offset-aligned DetectedEntity list."""
        results: List[DetectedEntity] = []
        used: Set[Tuple[int, int]] = set()

        for item in raw_entities:
            mention = str(item.get("text") or "").strip()
            etype = str(item.get("entity") or "").strip().upper()
            if not mention or etype not in PHI_ENTITY_TYPE_NAMES:
                continue

            try:
                confidence = float(item.get("confidence", 0.85))
            except (TypeError, ValueError):
                confidence = 0.85
            confidence = max(0.0, min(1.0, confidence))
            if confidence < min_confidence:
                continue

            try:
                hinted_start = int(item["start"]) if item.get("start") is not None else None
            except (TypeError, ValueError):
                hinted_start = None

            span = self._find_unused_span(text, mention, hinted_start, used)
            if span is None:
                continue
            used.add(span)
            start, end = span
            results.append(
                DetectedEntity(
                    entity=etype,
                    text=text[start:end],
                    start=start,
                    end=end,
                    confidence=round(confidence, 4),
                    category="phi",
                    label=label_for(etype),
                )
            )

        results.sort(key=lambda e: (e.start, e.end))
        return results

    def _find_unused_span(
        self,
        text: str,
        mention: str,
        hinted_start: Optional[int],
        used: Set[Tuple[int, int]],
    ) -> Optional[Tuple[int, int]]:
        """Resolve mention to an unused (start, end) in the source text."""
        candidates = []
        direct = self._resolver.resolve(text, mention, hinted_start)
        if direct:
            candidates.append(direct)

        start = 0
        while True:
            idx = text.find(mention, start)
            if idx < 0:
                break
            candidates.append((idx, idx + len(mention)))
            start = idx + 1

        if not candidates:
            lower_text = text.lower()
            lower_mention = mention.lower()
            start = 0
            while True:
                idx = lower_text.find(lower_mention, start)
                if idx < 0:
                    break
                candidates.append((idx, idx + len(mention)))
                start = idx + 1

        for span in candidates:
            if span not in used:
                return span
        return None
