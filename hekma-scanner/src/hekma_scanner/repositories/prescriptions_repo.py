import json

from ..awsutils.postgresql_utils import pg_transaction
from ..utils.prescription_dates import normalize_prescription_date
from .medication_schema import ensure_medication_schema


def create_prescription(patient_id, data):
    """Insert a prescription row; ensures content_hash and related columns exist."""
    ensure_medication_schema()
    extracted_data = data.get("extractedData")
    extracted_json = json.dumps(extracted_data) if extracted_data is not None else None

    content_hash = data.get("contentHash")
    prescription_date = normalize_prescription_date(data.get("prescriptionDate"))

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            INSERT INTO prescriptions (
                patient_id,
                image_path,
                scanned_at,
                prescription_date,
                prescriber_name,
                extracted_data,
                document_type,
                content_hash
            )
            VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
            RETURNING *
            """,
            (
                patient_id,
                data["imageUrl"],
                data["scannedAt"],
                prescription_date,
                data.get("prescriberName") or data.get("doctorName"),
                extracted_json,
                data.get("documentType", "prescription"),
                content_hash,
            ),
        )

        return cur.fetchone()


def get_prescriptions_by_patient(patient_id):

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            SELECT *
            FROM prescriptions
            WHERE patient_id = %s
              AND archived_at IS NULL
            ORDER BY created_at DESC
            """,
            (patient_id,),
        )

        return cur.fetchall()


def find_prescription_by_content_hash(patient_id: str, content_hash: str):
    """Lookup by content hash; ensures schema before querying content_hash."""
    ensure_medication_schema()
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            "SELECT * FROM prescriptions WHERE patient_id = %s AND content_hash = %s LIMIT 1",
            (patient_id, content_hash),
        )
        return cur.fetchone()


def count_medications_for_prescription(prescription_id: int) -> int:
    """Return how many medication rows are linked to this prescription."""
    ensure_medication_schema()
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT COUNT(*) AS count
            FROM medications
            WHERE prescription_id = %s
            """,
            (prescription_id,),
        )
        row = cur.fetchone() or {}
        return int(row.get("count") or 0)


def update_prescription(prescription_id: int, data: dict):
    """Refresh scan metadata/extracted data on an existing prescription row."""
    ensure_medication_schema()
    extracted_data = data.get("extractedData")
    extracted_json = json.dumps(extracted_data) if extracted_data is not None else None
    prescription_date = normalize_prescription_date(data.get("prescriptionDate"))

    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            UPDATE prescriptions
            SET
                image_path = %s,
                scanned_at = %s,
                prescription_date = COALESCE(%s, prescription_date),
                prescriber_name = COALESCE(%s, prescriber_name),
                extracted_data = COALESCE(%s::jsonb, extracted_data),
                document_type = COALESCE(%s, document_type),
                content_hash = COALESCE(%s, content_hash)
            WHERE id = %s
            RETURNING *
            """,
            (
                data["imageUrl"],
                data["scannedAt"],
                prescription_date,
                data.get("prescriberName") or data.get("doctorName"),
                extracted_json,
                data.get("documentType"),
                data.get("contentHash"),
                prescription_id,
            ),
        )
        return cur.fetchone()


def get_prescription(prescription_id):

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            SELECT *
            FROM prescriptions
            WHERE id = %s
            """,
            (prescription_id,),
        )

        return cur.fetchone()
