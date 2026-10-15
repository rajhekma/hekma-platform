from utils.pg_util import pg_transaction
import json


def upsert_mimic_summary(pid, summary, json_data, diseases, ts):

    with pg_transaction() as (conn, cursor):

        cursor.execute("""
            INSERT INTO mimic_patient_summary
            (patient_id, summary_text, structured_json, disease_list, latest_timestamp)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (patient_id)
            DO UPDATE SET
                summary_text = EXCLUDED.summary_text,
                structured_json = EXCLUDED.structured_json,
                disease_list = EXCLUDED.disease_list,
                latest_timestamp = EXCLUDED.latest_timestamp,
                updated_at = NOW()
        """, (
            pid,
            summary,
            json.dumps(json_data),  
            json.dumps(diseases),
            ts
        ))