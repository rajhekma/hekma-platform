"""
Format trial inclusion/exclusion criteria from DB / JSONL for matching and aggregation.
"""

from __future__ import annotations

import json
from typing import Any


_CRITERIA_HEADERS = {
    "inclusion criteria:",
    "exclusion criteria:",
    "inclusion criteria",
    "exclusion criteria",
}


def _sorted_dict_keys(keys: list) -> list:
    def _key(k):
        s = str(k)
        return int(s) if s.isdigit() else s

    return sorted(keys, key=_key)


def _is_real_criterion(text: str) -> bool:
    """Reject punctuation-only / empty fragments (e.g. a lone ':') that are not real
    criteria. These leak in from source formatting and, if kept, misalign the
    displayed criterion text with the criteria the LLM actually scored (the matching
    parser drops them and re-indexes)."""
    return any(ch.isalnum() for ch in (text or ""))


def criteria_to_list(value: Any) -> list[str]:
    """
    Ordered criterion strings for indexing (inference UI, criterion text lookup).
    """
    if not value:
        return []

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            return criteria_to_list(json.loads(text))
        except (json.JSONDecodeError, ValueError):
            parts = [p.strip() for p in text.split("\n\n") if p.strip()]
            if len(parts) <= 1:
                parts = [p.strip() for p in text.split("\n") if p.strip()]
            return [
                p
                for p in parts
                if p.lower() not in _CRITERIA_HEADERS and len(p) >= 3
            ]

    if isinstance(value, dict):
        return [
            str(value[k]).strip()
            for k in _sorted_dict_keys(list(value.keys()))
            if value[k] and str(value[k]).strip() and _is_real_criterion(str(value[k]))
        ]

    if isinstance(value, list):
        return [
            str(c).strip()
            for c in value
            if c
            and str(c).strip().lower() not in _CRITERIA_HEADERS
            and _is_real_criterion(str(c))
        ]

    return [str(value).strip()] if str(value).strip() and _is_real_criterion(str(value)) else []


def criteria_to_matching_text(value: Any) -> str:
    """
    Newline-separated criteria blocks for TrialGPT.parse_criteria / Claude parse_criteria.
    """
    parts = criteria_to_list(value)
    return "\n\n".join(parts)


def _coerce_index(idx_str: Any) -> int:
    """Extract an integer index from a criterion key.

    Keys are normally "0".."N" but some pipelines suffix them (e.g. "0_excl",
    "1_incl") or wrap them ("inclusion_2"). Pull the first integer found and fall
    back to 0 so the inference builder never hard-crashes on a malformed key.
    """
    try:
        return int(idx_str)
    except (TypeError, ValueError):
        import re

        m = re.search(r"\d+", str(idx_str))
        return int(m.group()) if m else 0


def resolve_criterion_index(idx_str: str, criteria_list: list[str]) -> int:
    """
    Map LLM criterion key to list index (handles 1-based keys "1".."N" and
    suffixed keys such as "0_excl").
    """
    idx = _coerce_index(idx_str)
    if not criteria_list:
        return idx
    # Matching prompts emit 0-based criterion keys ("0".."N-1"), so prefer 0-based
    # mapping. Only fall back to 1-based ("1".."N") when idx is out of 0-based range.
    if 0 <= idx < len(criteria_list):
        return idx
    if 1 <= idx <= len(criteria_list):
        return idx - 1
    return idx
