"""
SQLite snapshot storage for ClinicalTrials.gov registry monitoring metrics.
Stores daily totals, new trial arrivals, and update frequencies for drift tracking.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "trial_monitoring.db"


def get_db_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS registry_daily_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT UNIQUE NOT NULL,
                total_recruiting INTEGER NOT NULL,
                new_24h INTEGER NOT NULL,
                updated_24h INTEGER NOT NULL,
                new_7d INTEGER NOT NULL,
                updated_7d INTEGER NOT NULL,
                recorded_at TEXT NOT NULL
            );
        """)
        conn.commit()


def save_snapshot(
    total_recruiting: int,
    new_24h: int,
    updated_24h: int,
    new_7d: int,
    updated_7d: int,
) -> dict:
    init_db()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO registry_daily_snapshots (
                snapshot_date, total_recruiting, new_24h, updated_24h, new_7d, updated_7d, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                total_recruiting = excluded.total_recruiting,
                new_24h = excluded.new_24h,
                updated_24h = excluded.updated_24h,
                new_7d = excluded.new_7d,
                updated_7d = excluded.updated_7d,
                recorded_at = excluded.recorded_at;
        """, (today_str, total_recruiting, new_24h, updated_24h, new_7d, updated_7d, now_iso))
        conn.commit()

    return {
        "snapshot_date": today_str,
        "total_recruiting": total_recruiting,
        "new_24h": new_24h,
        "updated_24h": updated_24h,
        "new_7d": new_7d,
        "updated_7d": updated_7d,
        "recorded_at": now_iso,
    }


def get_latest_snapshot() -> Optional[dict]:
    init_db()
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT * FROM registry_daily_snapshots
            ORDER BY snapshot_date DESC LIMIT 1;
        """)
        row = cursor.fetchone()
        return dict(row) if row else None


def get_history(limit_days: int = 30) -> list[dict]:
    init_db()
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT * FROM registry_daily_snapshots
            ORDER BY snapshot_date DESC LIMIT ?;
        """, (limit_days,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
