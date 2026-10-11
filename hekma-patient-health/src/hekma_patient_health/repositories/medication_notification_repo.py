import json

from ..awsutils.postgresql_utils import pg_transaction


def log_notification(patient_id, medication_id, reminder_id, scheduled_time, status, payload):

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            INSERT INTO medication_notification_log (
                patient_id,
                medication_id,
                reminder_id,
                scheduled_time,
                status,
                payload
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING *
            """,
            (
                patient_id,
                medication_id,
                reminder_id,
                scheduled_time,
                status,
                json.dumps(payload),
            ),
        )

        return cur.fetchone()
