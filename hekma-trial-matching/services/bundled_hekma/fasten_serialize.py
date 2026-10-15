"""JSON-safe serialization for Fasten export rows (subset of hekma patient_data_exporter)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict

_ROW_COLUMNS = (
    "id",
    "patient_id",
    "hekma_mail_id",
    "org_connection_id",
    "resource_id",
    "raw_resource",
    "created_at",
)


def serialize_json_value(value: Any) -> Any:
    """Convert DB/Python values into JSON-safe primitives."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): serialize_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_json_value(item) for item in value]
    return str(value)


def serialize_fasten_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one Fasten table row for summary generation."""
    return {key: serialize_json_value(row.get(key)) for key in _ROW_COLUMNS if key in row}
