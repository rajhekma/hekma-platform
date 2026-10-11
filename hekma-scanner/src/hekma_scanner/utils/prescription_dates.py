"""Parse OCR / free-text dates into Postgres-safe YYYY-MM-DD strings."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

# How prescriptions print dates, and how they are shown back to the user.
DISPLAY_DATE_FORMAT = "%d-%b-%Y"


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%Y/%m/%d",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d %Y",
    "%B %d %Y",
    "%d %b %y",
    "%d %B %y",
    # Hyphenated month names are common on printed prescriptions (08-Sep-2026).
    "%d-%b-%Y",
    "%d-%B-%Y",
    "%d-%b-%y",
    "%d-%B-%y",
    "%b-%d-%Y",
    "%B-%d-%Y",
)

# Strip day ordinals only when attached to digits (22nd → 22), not letters in month names.
_ORDINAL_RE = re.compile(r"\b(\d+)(st|nd|rd|th)\b", re.IGNORECASE)


def normalize_prescription_date(value: Optional[str]) -> Optional[str]:
    """
    Convert common handwritten/OCR date strings to YYYY-MM-DD.

    Returns None when blank, uncertain, or unparseable so DB DATE columns
    are not fed invalid values like 22/05/2026.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"uncertain", "unknown", "n/a", "na", "none"}:
        return None

    cleaned = _ORDINAL_RE.sub(r"\1", text.replace(",", " "))
    # OCR often spaces around separators: "16 / 09 / 2026".
    cleaned = re.sub(r"\s*/\s*", "/", cleaned)
    cleaned = re.sub(r"\s*-\s*", "-", cleaned)
    cleaned = re.sub(r"\s*\.\s*", ".", cleaned)
    cleaned = " ".join(cleaned.split())

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue

    # Last resort: ISO-like prefix YYYY-MM-DD...
    if len(cleaned) >= 10 and cleaned[4] == "-" and cleaned[7] == "-":
        try:
            return datetime.strptime(cleaned[:10], "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    return None


def apply_display_date(extracted: Any) -> Any:
    """
    Rewrite an extraction's document date into the printed form, 08-Sep-2026.

    The model echoes the page, so the format varies between scans. Unreadable
    dates blank out rather than being guessed at.
    """
    if not isinstance(extracted, dict) or "date" not in extracted:
        return extracted
    extracted["date"] = format_prescription_date(extracted.get("date")) or ""
    return extracted


def format_prescription_date(value: Any) -> Optional[str]:
    """
    Render a date the way prescriptions print it — 08-Sep-2026.

    DATE columns can only hold ISO, so the printed spelling is rebuilt on the
    way out rather than stored. Returns None when there is no usable date.
    """
    if isinstance(value, datetime):
        return value.date().strftime(DISPLAY_DATE_FORMAT)
    if isinstance(value, date):
        return value.strftime(DISPLAY_DATE_FORMAT)

    iso = normalize_prescription_date(value)
    if not iso:
        return None
    return datetime.strptime(iso, "%Y-%m-%d").strftime(DISPLAY_DATE_FORMAT)
