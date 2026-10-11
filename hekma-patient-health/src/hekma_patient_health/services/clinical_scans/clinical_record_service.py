"""Lab/vital enrichment used by the FHIR projector.

The scanner API is not part of Patient Health. This module keeps the
small helper the projector already calls.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .exceptions import CatalogFieldKeyError

logger = logging.getLogger("clinical_records")


def enrich_standard_measurement(module: str, data: Dict[str, Any], catalog=None) -> Dict[str, Any]:
    """Copy LOINC, panel, and blank name/unit/range from standard_lab_catalog."""
    raw_key = data.get("fieldKey")
    if not isinstance(raw_key, str) or not raw_key.strip():
        return data
    if module not in {"lab_reports", "vital_signs"}:
        return data

    try:
        from ...repositories.lab_catalog_repo import LabCatalogRepository
    except Exception:
        return data

    field_key = raw_key.strip().lower()
    repo = catalog if catalog is not None else LabCatalogRepository()
    try:
        row = repo.get_active_field(field_key, module)
    except Exception:
        logger.debug("lab catalog unavailable; skipping enrichment for %s", field_key)
        return data
    if not row:
        raise CatalogFieldKeyError(f"Unknown or inactive fieldKey for {module}: {field_key}")
    # original helper copies catalog fields when the incoming record left them blank
    for src, dest in (
        ("loinc", "loinc"),
        ("panel", "panel"),
        ("display_name", "name"),
        ("unit", "unit"),
        ("ref_range", "range"),
    ):
        if not data.get(dest) and row.get(src):
            data[dest] = row[src]
    return data
