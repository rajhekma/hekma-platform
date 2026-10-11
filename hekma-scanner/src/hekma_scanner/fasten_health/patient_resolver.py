import json
from ..awsutils.postgresql_utils import pg_transaction


def resolve_patient_id(org_connection_id: str):
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT patient_id
            FROM fasten_controller
            WHERE org_connection_id = %s
            ORDER BY data_time DESC
            LIMIT 1
            """,
            (org_connection_id,),
        )
        row = cur.fetchone()
        if row:
            return row["patient_id"]

        cur.execute(
            """
            SELECT patient_id
            FROM fasten_controller
            WHERE fasten_health_ref -> 'data' @> %s
            ORDER BY data_time DESC
            LIMIT 1
            """,
            (json.dumps([{"org_connection_id": org_connection_id}]),),
        )
        row = cur.fetchone()
        return row["patient_id"] if row else None


def resolve_hekma_details(patient_id: str):
    from ..awsutils.mysql_db_connection import mysql_connection

    with mysql_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT email, subjectId
                FROM Patient
                WHERE patientId = %s
                LIMIT 1
                """,
                (patient_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "email": row.get("email"),
                    "subjectId": row.get("subjectId")
                }
            return None
        finally:
            cursor.close()
