from repositories.trialgpt_schema_bootstrap import ensure_trialgpt_schema
from utils.pg_util import pg_transaction


def get_patient_row(patient_id):
    with pg_transaction() as (_, cur):
        cur.execute("SELECT * FROM patient WHERE id = %s", (patient_id,))
        return cur.fetchone()


def get_table_rows(table_name, patient_id):
    with pg_transaction() as (_, cur):
        cur.execute(
            f"SELECT raw_resource, sort_date FROM {table_name} WHERE patient_id = %s",
            (patient_id,),
        )
        return cur.fetchall()


def get_latest_timestamp(patient_id):
    timestamps = []

    with pg_transaction() as (_, cur):

        # patient table
        cur.execute("SELECT created_at FROM patient WHERE id = %s", (patient_id,))
        row = cur.fetchone()
        if row:
            timestamps.append(row["created_at"])

        for table in ["condition", "allergy", "medication_order", "immunization"]:
            cur.execute(
                f"SELECT MAX(sort_date) AS max_date FROM {table} WHERE patient_id = %s",
                (patient_id,),
            )
            result = cur.fetchone()
            if result and result["max_date"]:
                timestamps.append(result["max_date"])

    return max(timestamps) if timestamps else None


def filter_patient_ids_with_pg_row(patient_ids: list[str]) -> set[str]:
    """Return the subset of IDs that exist in the FHIR patient table."""
    if not patient_ids:
        return set()
    with pg_transaction() as (_, cur):
        cur.execute(
            "SELECT id FROM patient WHERE id = ANY(%s)",
            (list(patient_ids),),
        )
        rows = cur.fetchall() or []
    return {str(row["id"]).strip() for row in rows if row.get("id")}


def fetch_compose_block_timestamps(patient_ids: list[str]) -> dict[str, object]:
    """Return {patient_id: last_data_timestamp} from trialgpt_eligible_patients."""
    ensure_trialgpt_schema()
    if not patient_ids:
        return {}
    with pg_transaction() as (_, cur):
        cur.execute(
            """
            SELECT subject_id AS patient_id, last_data_timestamp
            FROM trialgpt_eligible_patients
            WHERE subject_id = ANY(%s)
            """,
            (list(patient_ids),),
        )
        rows = cur.fetchall() or []
    out = {}
    for row in rows:
        pid = str(row.get("patient_id") or "").strip()
        if pid:
            out[pid] = row.get("last_data_timestamp")
    return out
