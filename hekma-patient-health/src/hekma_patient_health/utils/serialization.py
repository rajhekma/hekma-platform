from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union


def _snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def to_camel_case(data: Any) -> Any:
    if isinstance(data, dict):
        return {_snake_to_camel(k): to_camel_case(v) for k, v in data.items()}
    if isinstance(data, list):
        return [to_camel_case(item) for item in data]
    if isinstance(data, datetime):
        return data.isoformat()
    if isinstance(data, date):
        return data.isoformat()
    return data


def _with_display_date(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Report the prescription date the way prescriptions print it: 08-Sep-2026.

    `prescription_date` is a DATE column, so it reads back as 2026-09-08; the
    printed spelling is rebuilt here so every response uses one format. Writes
    accept it back unchanged — normalize_prescription_date parses this form.
    """
    from .prescription_dates import format_prescription_date

    payload = to_camel_case(dict(record))
    if "prescriptionDate" in payload:
        payload["prescriptionDate"] = format_prescription_date(
            record.get("prescription_date")
        )
    return payload


def medication_response(record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if record is None:
        return None
    return _with_display_date(record)


def prescription_response(record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Format a prescription row for API responses."""
    if record is None:
        return None
    return _with_display_date(record)


def prescriptions_response(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_with_display_date(r) for r in records]


def medications_response(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_with_display_date(r) for r in records]
