import json

from repositories.trialgpt_schema_bootstrap import ensure_trialgpt_schema
from utils.pg_util import pg_transaction


def get_mimic_summary_record(patient_id: str):
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT
                patient_id,
                summary_text,
                structured_json,
                disease_list,
                updated_at
            FROM mimic_patient_summary
            WHERE patient_id = %s
            """,
            (patient_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        structured = row.get("structured_json")
        if isinstance(structured, str):
            structured = json.loads(structured)

        diseases = row.get("disease_list")
        if isinstance(diseases, str):
            diseases = json.loads(diseases)

        return {
            "patient_id": row["patient_id"],
            "summary_text": row.get("summary_text") or "",
            "structured_json": structured or {},
            "disease_list": diseases or [],
            "updated_at": row.get("updated_at"),
        }


def list_mimic_summary_patients(limit: int = 50, offset: int = 0):
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT
                patient_id,
                LEFT(summary_text, 160) AS summary_preview,
                disease_list,
                updated_at
            FROM mimic_patient_summary
            WHERE summary_text IS NOT NULL
              AND TRIM(summary_text) <> ''
            ORDER BY patient_id
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        rows = cur.fetchall()

        cur.execute(
            """
            SELECT COUNT(*) AS total
            FROM mimic_patient_summary
            WHERE summary_text IS NOT NULL
              AND TRIM(summary_text) <> ''
            """
        )
        total = cur.fetchone()["total"]

    patients = []
    for row in rows:
        diseases = row.get("disease_list")
        if isinstance(diseases, str):
            diseases = json.loads(diseases)

        patients.append(
            {
                "patient_id": row["patient_id"],
                "summary_preview": row.get("summary_preview") or "",
                "disease_list": diseases or [],
                "summary_updated_at": row.get("updated_at"),
            }
        )

    return {"patients": patients, "total": total, "limit": limit, "offset": offset}


def get_cached_validation(patient_id: str):
    ensure_trialgpt_schema()
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT
                patient_id,
                validation_result,
                overall_status,
                reliability_score,
                validated_at
            FROM patient_summary_validations
            WHERE patient_id = %s
            """,
            (patient_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        result = row.get("validation_result")
        if isinstance(result, str):
            result = json.loads(result)

        return {
            "patient_id": row["patient_id"],
            "validation": result,
            "overall_status": row["overall_status"],
            "reliability_score": row["reliability_score"],
            "validated_at": row["validated_at"],
        }


def upsert_validation(
    patient_id: str,
    validation_result: dict,
    overall_status: str,
    reliability_score: int,
):
    ensure_trialgpt_schema()
    with pg_transaction() as (_, cur):
        cur.execute(
            """
            INSERT INTO patient_summary_validations (
                patient_id,
                validation_result,
                overall_status,
                reliability_score,
                validated_at
            )
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (patient_id)
            DO UPDATE SET
                validation_result = EXCLUDED.validation_result,
                overall_status = EXCLUDED.overall_status,
                reliability_score = EXCLUDED.reliability_score,
                validated_at = NOW()
            """,
            (
                patient_id,
                json.dumps(validation_result),
                overall_status,
                reliability_score,
            ),
        )
