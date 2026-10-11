from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from ..awsutils.postgresql_utils import pg_transaction


def _day_bounds_ms(day: date, tz: Optional[ZoneInfo] = None):
    tzinfo = tz or timezone.utc
    start = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=tzinfo)
    end = datetime(day.year, day.month, day.day, 23, 59, 59, 999999, tzinfo=tzinfo)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def insert_history_entry(entry):

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            INSERT INTO medication_history (
                medication_id,
                reminder_id,
                scheduled_time,
                taken_time,
                status,
                delay_minutes,
                synced
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                entry["medicationId"],
                entry.get("reminderId"),
                entry["scheduledTime"],
                entry.get("takenTime"),
                entry["status"],
                entry.get("delayMinutes", 0),
                entry.get("synced", False),
            ),
        )

        return cur.fetchone()


def get_dose_history(patient_medications, from_time=None, to_time=None):

    with pg_transaction(dict_cursor=True) as (_, cur):

        query = """
        SELECT *
        FROM medication_history
        WHERE medication_id = ANY(%s)
        """

        params = [patient_medications]

        if from_time:
            query += " AND scheduled_time >= %s"
            params.append(from_time)

        if to_time:
            query += " AND scheduled_time <= %s"
            params.append(to_time)

        query += " ORDER BY scheduled_time DESC"

        cur.execute(query, params)

        return cur.fetchall()


def get_dose_history_for_day(medication_ids, day: date, tz: Optional[ZoneInfo] = None):

    if not medication_ids:
        return []

    start_ms, end_ms = _day_bounds_ms(day, tz)

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            SELECT *
            FROM medication_history
            WHERE medication_id = ANY(%s)
              AND scheduled_time >= %s
              AND scheduled_time <= %s
            ORDER BY scheduled_time ASC
            """,
            (medication_ids, start_ms, end_ms),
        )

        return cur.fetchall()


def upsert_history_entry(entry):

    with pg_transaction(dict_cursor=True) as (_, cur):

        cur.execute(
            """
            UPDATE medication_history
            SET
                taken_time = %s,
                status = %s,
                delay_minutes = %s,
                synced = %s
            WHERE medication_id = %s
              AND scheduled_time = %s
              AND COALESCE(reminder_id, -1) = COALESCE(%s, -1)
            RETURNING *
            """,
            (
                entry.get("takenTime"),
                entry["status"],
                entry.get("delayMinutes", 0),
                entry.get("synced", True),
                entry["medicationId"],
                entry["scheduledTime"],
                entry.get("reminderId"),
            ),
        )

        row = cur.fetchone()
        if row:
            return row

        cur.execute(
            """
            INSERT INTO medication_history (
                medication_id,
                reminder_id,
                scheduled_time,
                taken_time,
                status,
                delay_minutes,
                synced
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                entry["medicationId"],
                entry.get("reminderId"),
                entry["scheduledTime"],
                entry.get("takenTime"),
                entry["status"],
                entry.get("delayMinutes", 0),
                entry.get("synced", True),
            ),
        )

        return cur.fetchone()
