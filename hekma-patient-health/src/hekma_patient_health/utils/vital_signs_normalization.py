"""Normalize vital-sign payloads, especially blood pressure systolic/diastolic pairs."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

_BP_VALUE_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*[/\-]\s*(\d+(?:\.\d+)?)"
)
_FIRST_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")


def is_blood_pressure(vital_type: str) -> bool:
    text = " ".join((vital_type or "").lower().split())
    if not text:
        return False
    if text in {"bp", "b p"}:
        return True
    return "blood pressure" in text


def _first_number(value: str) -> str:
    match = _FIRST_NUMBER_RE.search(value or "")
    return match.group(1) if match else ""


def split_bp_values(v1: str, v2: str = "") -> Tuple[str, Optional[str]]:
    """Split combined BP strings like ``128/82`` or ``128/82 mmHg`` into two values."""
    left = (v1 or "").strip()
    right = (v2 or "").strip()
    if right:
        return _first_number(left) or left, _first_number(right) or right

    match = _BP_VALUE_RE.match(left)
    if not match and left:
        match = _BP_VALUE_RE.match(left.split()[0])
    if match:
        return match.group(1), match.group(2)

    return _first_number(left) or left, None


def normalize_vital_sign_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with BP values split and non-BP second values cleared."""
    out = dict(record or {})
    vital_type = str(out.get("type") or out.get("name") or "").strip()
    v1 = str(out.get("refValue1") or out.get("value") or "").strip()
    v2 = str(out.get("refValue2") or out.get("value2") or "").strip()

    if is_blood_pressure(vital_type):
        systolic, diastolic = split_bp_values(v1, v2)
        out["refValue1"] = systolic
        out["refValue2"] = diastolic
        if "value" in out:
            out["value"] = systolic
        if "value2" in out:
            out["value2"] = diastolic
    elif v2:
        # Keep explicit second values only for BP; other vitals are single-value.
        out["refValue2"] = None
        if "value2" in out:
            out["value2"] = None

    return out
