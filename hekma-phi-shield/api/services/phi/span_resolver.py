"""Locate LLM-reported PHI mentions in the original text for reliable offsets."""

from __future__ import annotations

from typing import List, Optional, Tuple


class SpanResolver:
    """Maps extracted mention strings back to character offsets in source text."""

    def resolve(
        self,
        text: str,
        mention: str,
        hinted_start: Optional[int] = None,
    ) -> Optional[Tuple[int, int]]:
        """Find `mention` in `text`; prefer a hinted start when it matches."""
        if not mention:
            return None
        if hinted_start is not None and hinted_start >= 0:
            end = hinted_start + len(mention)
            if text[hinted_start:end] == mention:
                return hinted_start, end
            # Case-insensitive hint check
            if text[hinted_start:end].lower() == mention.lower():
                return hinted_start, end

        idx = text.find(mention)
        if idx >= 0:
            return idx, idx + len(mention)

        lower_text = text.lower()
        lower_mention = mention.lower()
        idx = lower_text.find(lower_mention)
        if idx >= 0:
            return idx, idx + len(mention)

        return None

    def resolve_all(
        self,
        text: str,
        mentions: List[Tuple[str, Optional[int]]],
    ) -> List[Tuple[str, int, int]]:
        """Resolve many mentions without reusing the same span twice."""
        used: set[Tuple[int, int]] = set()
        resolved: List[Tuple[str, int, int]] = []
        for mention, hinted_start in mentions:
            span = self._next_unused(text, mention, hinted_start, used)
            if span is None:
                continue
            used.add(span)
            resolved.append((mention, span[0], span[1]))
        return resolved

    def _next_unused(
        self,
        text: str,
        mention: str,
        hinted_start: Optional[int],
        used: set[Tuple[int, int]],
    ) -> Optional[Tuple[int, int]]:
        """Return the first unused occurrence of mention in text."""
        if not mention:
            return None
        # Prefer exact hint when free
        direct = self.resolve(text, mention, hinted_start)
        if direct and direct not in used:
            return direct

        start = 0
        while True:
            idx = text.find(mention, start)
            if idx < 0:
                break
            span = (idx, idx + len(mention))
            if span not in used:
                return span
            start = idx + 1

        lower_text = text.lower()
        lower_mention = mention.lower()
        start = 0
        while True:
            idx = lower_text.find(lower_mention, start)
            if idx < 0:
                return None
            span = (idx, idx + len(mention))
            if span not in used:
                return span
            start = idx + 1
