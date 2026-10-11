"""Resolve CTMS patientId values for Internal* EHR SQL filters."""

from __future__ import annotations

from typing import List, Optional, Set

from ..awsutils.mysql_db_connection import mysql_connection

# Clients send the literal strings "undefined"/"null" when an id is missing.
BLANK_IDENTIFIERS = {"", "undefined", "null", "none", "nan"}

ARCHIVED_EMAIL_DOMAIN = "deleted.hekma.local"
ARCHIVED_ROW_PREDICATE = "archived_at IS NULL"
_DELETED_STATUSES = ("DELETED", "ARCHIVED")


def normalize_identifier(value) -> Optional[str]:
    """Return None for blank / JS placeholder identifier strings."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in BLANK_IDENTIFIERS else text


def is_archived_email(email: Optional[str]) -> bool:
    """True when the address is the deletion tombstone."""
    text = (email or "").strip().lower()
    return text.startswith("archived+") and text.endswith(f"@{ARCHIVED_EMAIL_DOMAIN}")


def locked_email_for_patient(patient_id: str) -> str:
    return f"archived+{str(patient_id).strip()}@{ARCHIVED_EMAIL_DOMAIN}"


def resolve_living_patient_by_email(email: str) -> Optional[str]:
    """Living MySQL Patient id for email, or None if deleted/missing."""
    email = normalize_identifier(email)
    if not email or is_archived_email(email):
        return None
    sql = (
        "SELECT patientId FROM Patient "
        "WHERE LOWER(TRIM(email)) = LOWER(TRIM(%s)) "
        "AND UPPER(COALESCE(status, '')) NOT IN ('DELETED', 'ARCHIVED') "
        "AND (email IS NULL OR LOWER(email) NOT LIKE 'archived+%@deleted.hekma.local') "
        "LIMIT 1"
    )
    try:
        with mysql_connection() as mysql:
            cursor = mysql.cursor()
            cursor.execute(sql, (email,))
            row = cursor.fetchone()
    except Exception:
        return None
    if not row or row[0] is None:
        return None
    return str(row[0]).strip()


def resolve_chart_patient_id(
    patient_id=None,
    hekma_mail=None,
    jwt_user_id=None,
) -> Optional[str]:
    """
    Current chart identity for 360/EHR reads.

    JWT userId wins. Query patientId is next. Email is only used when no id
    is present, and only for a living (non-deleted) MySQL patient.
    """
    jwt_user_id = normalize_identifier(jwt_user_id)
    if jwt_user_id:
        return jwt_user_id
    patient_id = normalize_identifier(patient_id)
    if patient_id:
        return patient_id
    return resolve_living_patient_by_email(hekma_mail)


def resolve_ctms_patient_ids(
    patient_id=None, hekma_mail=None
) -> List[int]:
    """
    Resolve numeric CTMS patientId values for Internal* EHR queries.

    Email does not widen the chart. Deleted/archived MySQL patients are skipped.
    A numeric caller id is kept only when no Patient row exists (new scans).
    """
    ids: Set[int] = set()
    patient_id = normalize_identifier(patient_id)
    _ = normalize_identifier(hekma_mail)  # ignored for widening

    if not patient_id:
        return []

    clauses = ["subjectId=%s", "CAST(patientId AS CHAR)=%s"]
    params = [patient_id, str(patient_id)]
    sql = (
        "SELECT patientId, status, email FROM Patient WHERE "
        + " OR ".join(clauses)
    )
    caller_deleted = False
    try:
        with mysql_connection() as mysql:
            cursor = mysql.cursor()
            cursor.execute(sql, tuple(params))
            for row in cursor.fetchall():
                if not row or row[0] is None:
                    continue
                status = str(row[1] or "").upper()
                email = str(row[2] or "")
                if status in _DELETED_STATUSES or is_archived_email(email):
                    if str(row[0]).strip() == str(patient_id).strip():
                        caller_deleted = True
                    continue
                try:
                    ids.add(int(row[0]))
                except (TypeError, ValueError):
                    pass
    except Exception:
        caller_deleted = False

    if str(patient_id).strip().isdigit() and not caller_deleted:
        ids.add(int(str(patient_id).strip()))

    return sorted(ids)


def build_ctms_sql(sql_template: str, patient_ids) -> str:
    """Substitute validated patient ids into an integrate.json CTMS SQL template."""
    ids = ",".join(str(int(pid)) for pid in patient_ids)
    return str(sql_template).replace("{patient_ids}", ids)


def append_id_only_scope(
    where: list,
    params: dict,
    *,
    pid_column: str,
    patient_id: Optional[str],
    param_key: str = "patient_id",
) -> bool:
    """
    Restrict a 360/EHR query to one patient id and non-archived rows.

    Returns False when there is no patient id (caller should return empty).
    """
    patient_id = normalize_identifier(patient_id)
    if not patient_id:
        return False
    where.append(f"{pid_column} = %({param_key})s")
    params[param_key] = patient_id
    where.append(ARCHIVED_ROW_PREDICATE)
    return True
