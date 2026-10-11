from typing import Optional

import psycopg2

from ..awsutils.postgresql_utils import pg_transaction

_COLUMN_MISSING = False


def get_patient_timezone_name(patient_id: str) -> Optional[str]:
    global _COLUMN_MISSING
    if _COLUMN_MISSING:
        return None

    try:
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                """
                SELECT timezone
                FROM patient
                WHERE id = %s
                """,
                (patient_id,),
            )
            row = cur.fetchone()
    except psycopg2.errors.UndefinedColumn:
        _COLUMN_MISSING = True
        return None

    if not row:
        return None
    value = row.get("timezone")
    if not value:
        return None
    return str(value).strip() or None


def set_patient_timezone(patient_id: str, timezone_name: str) -> bool:
    global _COLUMN_MISSING
    if _COLUMN_MISSING:
        return False

    try:
        with pg_transaction() as (_, cur):
            cur.execute(
                """
                UPDATE patient
                SET timezone = %s
                WHERE id = %s
                """,
                (timezone_name.strip(), patient_id),
            )
            return cur.rowcount > 0
    except psycopg2.errors.UndefinedColumn:
        _COLUMN_MISSING = True
        return False
