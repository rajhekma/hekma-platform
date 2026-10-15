import json

from repositories.trialgpt_schema_bootstrap import ensure_trialgpt_schema
from utils.pg_util import pg_transaction


# def insert_patient(patient_id, data):
#     with pg_transaction() as (conn, cur):
#         cur.execute("""
#             INSERT INTO patient_annotations (patient_id, data, comments)
#             VALUES (%s, %s, %s)
#             ON CONFLICT (patient_id) DO NOTHING
#         """, (patient_id, json.dumps(data), json.dumps({"Trials": []})))



def insert_patient(patient_id, data):
    ensure_trialgpt_schema()
    with pg_transaction() as (conn, cur):
        cur.execute("""
            INSERT INTO patient_annotations (patient_id, data, comments)
            VALUES (%s, %s, %s)
            ON CONFLICT (patient_id)
            DO UPDATE SET
                data = EXCLUDED.data,
                updated_at = NOW()
        """, (patient_id, json.dumps(data), json.dumps({"Trials": []})))



def get_all_patients():
    ensure_trialgpt_schema()
    with pg_transaction() as (conn, cur):
        cur.execute("""
            SELECT
                patient_id,
                LEFT(COALESCE(data->>'Patient_Summary', ''), 120) AS summary,
                has_review_requests,
                COALESCE(jsonb_array_length(comments->'Trials'), 0) > 0 AS is_commented
            FROM patient_annotations
            ORDER BY updated_at DESC, patient_id
        """)
        return cur.fetchall()


def get_patient(patient_id):
    ensure_trialgpt_schema()
    with pg_transaction() as (conn, cur):
        cur.execute("""
            SELECT *
            FROM patient_annotations
            WHERE patient_id = %s
        """, (patient_id,))
        return cur.fetchone()


def update_comments(patient_id, comments, has_review):
    ensure_trialgpt_schema()
    with pg_transaction() as (conn, cur):
        cur.execute("""
            UPDATE patient_annotations
            SET comments = %s,
                has_review_requests = %s,
                updated_at = NOW()
            WHERE patient_id = %s
        """, (json.dumps(comments), has_review, patient_id))