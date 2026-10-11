"""PostgreSQL persistence for count-based daily medication tracking."""

from datetime import date
from typing import Dict, Optional

from ..awsutils.postgresql_utils import pg_transaction
from .medication_schema import ensure_medication_daily_count_schema


class MedicationDailyCountRepository:
    """Store daily target snapshots and atomic taken-count changes."""

    def set_target(
        self, patient_id: str, medication_id: int, target_count: int
    ) -> Optional[Dict]:
        """Set the medication's daily target after enforcing patient ownership."""
        ensure_medication_daily_count_schema()
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                """
                UPDATE medications
                SET daily_target_count = %s, updated_at = NOW()
                WHERE id = %s AND patient_id = %s
                RETURNING *
                """,
                (target_count, medication_id, patient_id),
            )
            return cur.fetchone()

    def get_target(
        self, patient_id: str, medication_id: int
    ) -> Optional[Dict]:
        """Return an owned medication's configured daily target."""
        ensure_medication_daily_count_schema()
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                """
                SELECT id, patient_id, name, status, daily_target_count
                FROM medications
                WHERE id = %s AND patient_id = %s
                """,
                (medication_id, patient_id),
            )
            return cur.fetchone()

    def get_daily_count(
        self, medication_id: int, tracking_date: date
    ) -> Optional[Dict]:
        """Return a stored daily count snapshot, if any."""
        ensure_medication_daily_count_schema()
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                """
                SELECT *
                FROM medication_daily_counts
                WHERE medication_id = %s AND tracking_date = %s
                """,
                (medication_id, tracking_date),
            )
            return cur.fetchone()

    def increment(
        self,
        medication_id: int,
        tracking_date: date,
        timezone_name: str,
        target_count: int,
        count: int,
    ) -> Optional[Dict]:
        """Atomically add taken uses without allowing the daily target to be exceeded."""
        ensure_medication_daily_count_schema()
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                """
                INSERT INTO medication_daily_counts (
                    medication_id, tracking_date, timezone, target_count, taken_count
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (medication_id, tracking_date)
                DO UPDATE SET
                    target_count = EXCLUDED.target_count,
                    taken_count = medication_daily_counts.taken_count
                        + EXCLUDED.taken_count,
                    updated_at = NOW()
                WHERE medication_daily_counts.taken_count + EXCLUDED.taken_count
                    <= EXCLUDED.target_count
                RETURNING *
                """,
                (
                    medication_id,
                    tracking_date,
                    timezone_name,
                    target_count,
                    count,
                ),
            )
            return cur.fetchone()

    def decrement(
        self, medication_id: int, tracking_date: date, count: int
    ) -> Optional[Dict]:
        """Atomically undo taken uses without allowing a negative count."""
        ensure_medication_daily_count_schema()
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                """
                UPDATE medication_daily_counts
                SET taken_count = taken_count - %s, updated_at = NOW()
                WHERE medication_id = %s
                  AND tracking_date = %s
                  AND taken_count >= %s
                RETURNING *
                """,
                (count, medication_id, tracking_date, count),
            )
            return cur.fetchone()
