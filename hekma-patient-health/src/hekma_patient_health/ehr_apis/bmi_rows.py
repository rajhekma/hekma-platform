"""BMI rows for the Vital Signs tile.

fastenhealth_bmi_data (written by hekma_api) holds one computed BMI per patient.
The generic fastenhealth_* reader applies EHR_SOURCE_PREDICATE, which excludes
source='computed' / org_connection_id='hekma:computed', so BMI is read here
directly and shaped like an Internal vital row (Name / value / category_code).
Rows carry no internal='Y', so the UI treats them as read-only, like EHR data.
"""

from datetime import datetime
from typing import Iterable, List

from ..awsutils.postgresql_utils import pg_transaction

_DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d")


def _iso_date(raw, fallback) -> str:
    """Observation date as YYYY-MM-DD so it sorts with the other vitals."""
    if raw:
        text = str(raw).strip()
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text[:10], fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        if len(text) >= 10 and text[4] == "-":
            return text[:10]
    return fallback.strftime("%Y-%m-%d") if fallback else ""


def _clean_ids(patient_ids: Iterable[str]) -> List[str]:
    ids = []
    for p in patient_ids or []:
        s = str(p).strip() if p is not None else ""
        if s and s not in ids:
            ids.append(s)
    return ids


def count_bmi_rows(patient_ids: Iterable[str]) -> int:
    """Header count for the Observation tile (the UI uses it as the detail page size)."""
    ids = _clean_ids(patient_ids)
    if not ids:
        return 0
    try:
        with pg_transaction(dict_cursor=False) as (_, cur):
            cur.execute(
                "SELECT COUNT(*) FROM fastenhealth_bmi_data "
                "WHERE patient_id = ANY(%(ids)s) AND org_connection_id = 'hekma:computed'",
                {"ids": ids},
            )
            return cur.fetchone()[0]
    except Exception as exc:
        print(f"BMI count unavailable: {exc}")
        return 0


def fetch_bmi_dashboard_rows(patient_ids: Iterable[str]) -> List[dict]:
    ids = _clean_ids(patient_ids)
    if not ids:
        return []

    sql = """
        SELECT patient_id, bmi, bmi_category, raw_resource, updated_at,
               height_cm, weight_kg
        FROM fastenhealth_bmi_data
        WHERE patient_id = ANY(%(ids)s)
          AND org_connection_id = 'hekma:computed'
    """
    try:
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(sql, {"ids": ids})
            records = cur.fetchall()
    except Exception as exc:  # table missing in an env, etc. -> no BMI, never break vitals
        print(f"BMI rows unavailable: {exc}")
        return []

    rows = []
    for rec in records:
        resource = rec.get("raw_resource") or {}
        name = (resource.get("code") or {}).get("text") or "Body Mass Index"
        unit = (resource.get("valueQuantity") or {}).get("unit") or "kg/m2"
        bmi = float(rec["bmi"]) if rec.get("bmi") is not None else None
        date = _iso_date(resource.get("effectiveDateTime"), rec.get("updated_at"))
        rows.append(
            {
                "Name": name,
                "Status": "final",
                "date_of_observation": date,
                "sort_date": date,
                "category_code": "vital-signs",
                "value_quantity": [{"value": bmi, "unit": unit}],
                "refValue1": bmi,
                "metric": unit,
                "notes": rec.get("bmi_category"),
                "bmi_category": rec.get("bmi_category"),
                "height_cm": float(rec["height_cm"]) if rec.get("height_cm") is not None else None,
                "weight_kg": float(rec["weight_kg"]) if rec.get("weight_kg") is not None else None,
                "computed": "Y",
                "createdBy": rec.get("patient_id"),
            }
        )
    return rows
