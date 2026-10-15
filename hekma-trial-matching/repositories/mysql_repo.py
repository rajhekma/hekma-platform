from utils.mysql_util import get_mysql_connection
import uuid

# MySQL sometimes stores JS placeholder strings instead of a real subject UUID.
_INVALID_SUBJECT_IDS = frozenset({"undefined", "null", "none", "nan", "nil"})


def resolve_subject_id(raw_subject_id, mysql_patient_id) -> str:
    """
    Return a usable subject_id for TrialGPT jobs / trial_gpt_ehr.

    Prefer MySQL Patient.subjectId when it is a real value; otherwise derive a
    stable UUID5 from the numeric patient id so Fasten patients still work.
    """
    text = str(raw_subject_id or "").strip()
    if text and text.lower() not in _INVALID_SUBJECT_IDS:
        return text
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"hekma:patient:{int(mysql_patient_id)}"))


def get_all_source_ids():
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT subjectId
        FROM Patient
        WHERE subjectId IS NOT NULL
          AND TRIM(subjectId) != ''
    """)

    for row in cursor:
        subject_id = row["subjectId"]
        if subject_id and subject_id.strip():
            yield subject_id.strip()

    cursor.close()
    conn.close()


def count_source_ids() -> int:
    conn = get_mysql_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM Patient
            WHERE subjectId IS NOT NULL
              AND TRIM(subjectId) != ''
            """
        )
        return int(cursor.fetchone()[0])
    finally:
        cursor.close()
        conn.close()


def get_source_ids_page(limit: int, offset: int) -> list[str]:
    """Page MySQL subjectIds for batch jobs."""
    rows = get_source_id_rows_page(limit, offset)
    return [r["subject_id"] for r in rows]


def get_source_id_rows_page(limit: int, offset: int) -> list[dict]:
    """
    Page MySQL Patient rows with subjectId.
    Returns list of {subject_id, mysql_patient_id}.
    """
    conn = get_mysql_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT patientId, subjectId
            FROM Patient
            WHERE subjectId IS NOT NULL
              AND TRIM(subjectId) != ''
            ORDER BY subjectId
            LIMIT %s OFFSET %s
            """,
            (int(limit), int(offset)),
        )
        out = []
        for row in cursor:
            subject_id = row.get("subjectId")
            if not subject_id or not str(subject_id).strip():
                continue
            mysql_pid = row.get("patientId")
            try:
                mysql_patient_id = int(mysql_pid) if mysql_pid is not None else None
            except (TypeError, ValueError):
                mysql_patient_id = None
            out.append(
                {
                    "subject_id": str(subject_id).strip(),
                    "mysql_patient_id": mysql_patient_id,
                }
            )
        return out
    finally:
        cursor.close()
        conn.close()


def get_subject_id_by_patient_id(patient_id: str):
    """Resolve subject_id for a MySQL patientId; never return placeholder 'undefined'."""
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT patientId, subjectId
        FROM Patient
        WHERE patientId = %s
        LIMIT 1
        """,
        (patient_id,),
    )

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row:
        return None

    try:
        mysql_patient_id = int(row["patientId"])
    except (TypeError, ValueError):
        return None

    return resolve_subject_id(row.get("subjectId"), mysql_patient_id)


_PATIENT_CREATED_COLUMN_CANDIDATES = (
    "createdAt",
    "created_at",
    "registrationDate",
    "registeredAt",
    "insertDate",
)


def _resolve_patient_created_column(cursor) -> str | None:
    """Detect which Patient created-timestamp column exists (cached per connection)."""
    cursor.execute("SHOW COLUMNS FROM Patient")
    columns = {str(row["Field"]) for row in (cursor.fetchall() or [])}
    for candidate in _PATIENT_CREATED_COLUMN_CANDIDATES:
        if candidate in columns:
            return candidate
    return None


def get_patient_identity(patient_id: str) -> dict | None:
    """
    Load MySQL Patient identity for trial_gpt_ehr gating.

    Returns {mysql_patient_id, subject_id, created_at} or None if missing.
    created_at may be None when the Patient table has no known created column.
    """
    conn = get_mysql_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        created_col = _resolve_patient_created_column(cursor)
        select_cols = ["patientId", "subjectId"]
        if created_col:
            select_cols.append(f"`{created_col}` AS patient_created_at")

        cursor.execute(
            f"""
            SELECT {', '.join(select_cols)}
            FROM Patient
            WHERE patientId = %s
            LIMIT 1
            """,
            (patient_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        mysql_pid = row.get("patientId")
        try:
            mysql_patient_id = int(mysql_pid)
        except (TypeError, ValueError):
            return None

        subject_id = resolve_subject_id(row.get("subjectId"), mysql_patient_id)

        return {
            "mysql_patient_id": mysql_patient_id,
            "subject_id": subject_id,
            "created_at": row.get("patient_created_at") if created_col else None,
            "created_column": created_col,
        }
    finally:
        cursor.close()
        conn.close()
