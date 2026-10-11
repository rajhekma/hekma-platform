from datetime import date
from typing import Dict, List, Optional

from ..awsutils.postgresql_utils import pg_transaction
from .medication_schema import ensure_medication_daily_count_schema


def get_active_medications_with_reminders() -> List[Dict]:
    """Load active meds with reminders; ensures daily_target_count column exists."""
    ensure_medication_daily_count_schema()
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT
                m.id AS medication_id,
                m.patient_id,
                m.name,
                m.strength,
                m.dosage,
                m.how_much_to_take,
                m.frequency,
                m.start_date,
                m.end_date,
                m.created_at,
                m.daily_target_count,
                m.is_reminder_enabled,
                r.id AS reminder_id,
                r.hour,
                r.minute,
                r.label
            FROM medications m
            LEFT JOIN medication_reminders r ON r.medication_id = m.id
            WHERE m.status = 'Active'
              AND m.archived_at IS NULL
            ORDER BY m.patient_id, m.id, r.hour, r.minute
            """
        )
        return cur.fetchall()


def get_history_in_range(from_ms: int, to_ms: int) -> List[Dict]:
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT
                h.medication_id,
                h.reminder_id,
                h.scheduled_time,
                h.taken_time,
                h.status
            FROM medication_history h
            INNER JOIN medications m ON m.id = h.medication_id
            WHERE m.status = 'Active'
              AND m.archived_at IS NULL
              AND h.scheduled_time >= %s
              AND h.scheduled_time <= %s
            """,
            (from_ms, to_ms),
        )
        return cur.fetchall()


def get_patients_by_ids(patient_ids: List[str]) -> Dict[str, Dict]:
    if not patient_ids:
        return {}

    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT id, given_name, family_name, hekma_mail
            FROM patient
            WHERE id = ANY(%s)
            """,
            (patient_ids,),
        )
        rows = cur.fetchall()

    return {row["id"]: row for row in rows}


def count_brand_name_medications() -> int:
    """Approximate brand-name count (non-generic heuristic: capitalized multi-word)."""
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM medications
            WHERE status = 'Active'
              AND archived_at IS NULL
              AND name ~ '[A-Z][a-z]+ [A-Z]'
            """
        )
        row = cur.fetchone()
        return int(row["cnt"]) if row else 0


def count_total_medications() -> int:
    """Count all medications."""
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM medications
            """
        )
        row = cur.fetchone()
        return int(row["cnt"]) if row else 0
