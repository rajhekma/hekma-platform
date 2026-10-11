from ..awsutils.postgresql_utils import pg_transaction


def create_reminder(medication_id, reminder):

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            INSERT INTO medication_reminders (
                medication_id,
                hour,
                minute,
                label
            )
            VALUES (%s,%s,%s,%s)
            RETURNING *
            """,
            (
                medication_id,
                reminder["hour"],
                reminder["minute"],
                reminder.get("label"),
            ),
        )

        return cur.fetchone()


def get_reminders_by_medication(medication_id):

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            SELECT *
            FROM medication_reminders
            WHERE medication_id=%s
            ORDER BY hour, minute
            """,
            (medication_id,),
        )

        return cur.fetchall()


def delete_reminders_by_medication(medication_id):

    with pg_transaction() as (_, cur):

        cur.execute(
            """
            DELETE FROM medication_reminders
            WHERE medication_id=%s
            """,
            (medication_id,),
        )
