from ..awsutils.postgresql_utils import pg_transaction


def register_device_token(patient_id, device_token, platform):

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            INSERT INTO patient_device_tokens (
                patient_id,
                device_token,
                platform,
                is_active
            )
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT (patient_id, device_token)
            DO UPDATE SET
                platform = EXCLUDED.platform,
                is_active = TRUE,
                updated_at = NOW()
            RETURNING *
            """,
            (patient_id, device_token, platform),
        )

        return cur.fetchone()


def get_active_device_tokens(patient_id):

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            SELECT *
            FROM patient_device_tokens
            WHERE patient_id = %s AND is_active = TRUE
            ORDER BY updated_at DESC
            """,
            (patient_id,),
        )

        return cur.fetchall()
