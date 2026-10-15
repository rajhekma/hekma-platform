"""
Create MySQL `Patient` rows so `patientId` -> `subjectId` matches block-summary UUIDs.

The API maps request `patient_id` via:
  SELECT subjectId FROM Patient WHERE patientId = %s

So each row needs:
  - subjectId = UUID from PostgreSQL `trialgpt_eligible_patients.subject_id` OR JSON `Patient_ID`
  - patientId = unique external id (dummy), default 30001, 30002, ... (see --patient-id-start)

Sources (--source):
  - json: read Patient_ID from block summary JSON (default path below)
  - pg:   read subject_id from PostgreSQL trialgpt_eligible_patients

MySQL connection:
  Prefer env: MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE, MYSQL_PORT (optional)
  If unset, falls back to utils.mysql_util.get_mysql_connection() (same as the API).

PostgreSQL env (only if --source pg), same as app:
  PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD

Usage:
  cd trailgpt
  .\\.venv\\Scripts\\Activate.ps1
  python .\\scripts\\sync_block_patients_to_mysql.py --dry-run
  python .\\scripts\\sync_block_patients_to_mysql.py --source json
  python .\\scripts\\sync_block_patients_to_mysql.py --source pg --limit 57
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_JSON = (
    PROJECT_ROOT
    / "dataset"
    / "block_summary"
    / "P2Tv1_P57_v3 1.json"
)


def _mysql_connect():
    load_dotenv()
    host = os.getenv("MYSQL_HOST")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    database = os.getenv("MYSQL_DATABASE")
    if all([host, user, password, database]):
        import mysql.connector

        return mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )
    try:
        from utils.mysql_util import get_mysql_connection

        return get_mysql_connection()
    except Exception as exc:
        raise RuntimeError(
            "MySQL connection failed. Either set MYSQL_HOST, MYSQL_USER, "
            "MYSQL_PASSWORD, MYSQL_DATABASE in .env, or ensure "
            "utils.mysql_util.get_mysql_connection() works."
        ) from exc


def _pg_fetch_patient_ids(limit: int | None) -> list[str]:
    load_dotenv()
    import psycopg2

    pg_host = os.getenv("PG_HOST")
    pg_port = int(os.getenv("PG_PORT", "5432"))
    pg_db = os.getenv("PG_DB")
    pg_user = os.getenv("PG_USER")
    pg_password = os.getenv("PG_PASSWORD")
    missing = [k for k, v in {
        "PG_HOST": pg_host,
        "PG_DB": pg_db,
        "PG_USER": pg_user,
        "PG_PASSWORD": pg_password,
    }.items() if not v]
    if missing:
        raise RuntimeError("Missing PostgreSQL env: " + ", ".join(missing))

    conn = psycopg2.connect(
        host=pg_host,
        port=pg_port,
        dbname=pg_db,
        user=pg_user,
        password=pg_password,
    )
    try:
        with conn.cursor() as cur:
            sql = "SELECT subject_id AS patient_id FROM trialgpt_eligible_patients ORDER BY subject_id"
            if limit is not None:
                cur.execute(sql + " LIMIT %s", (limit,))
            else:
                cur.execute(sql)
            rows = cur.fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows if r and r[0]]


def _json_fetch_patient_ids(json_path: Path) -> list[str]:
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("JSON must be a list of objects with Patient_ID")
    ids = []
    for i, item in enumerate(data, start=1):
        pid = item.get("Patient_ID")
        if not pid:
            raise ValueError(f"Missing Patient_ID at index {i}")
        ids.append(str(pid).strip())
    return ids


def _load_subject_ids(source: str, json_path: Path, limit: int | None) -> list[str]:
    if source == "json":
        ids = _json_fetch_patient_ids(json_path)
    elif source == "pg":
        ids = _pg_fetch_patient_ids(limit)
    else:
        raise ValueError(f"Unknown --source {source}")
    if limit is not None:
        ids = ids[:limit]
    # de-dupe preserve order
    seen = set()
    out = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _mysql_table_columns(cursor) -> list[dict]:
    cursor.execute(
        """
        SELECT COLUMN_NAME, COLUMN_KEY, EXTRA, IS_NULLABLE, COLUMN_DEFAULT, DATA_TYPE,
               CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Patient'
        ORDER BY ORDINAL_POSITION
        """
    )
    rows = cursor.fetchall()
    cols = []
    for r in rows:
        cols.append({
            "name": r[0],
            "column_key": r[1],
            "extra": (r[2] or "").lower(),
            "nullable": r[3],
            "default": r[4],
            "data_type": r[5],
            "char_max": r[6],
        })
    return cols


def _mysql_unique_index_columns(cursor) -> set[str]:
    """Column names that participate in any non-PK UNIQUE index (must not copy template verbatim)."""
    cursor.execute(
        """
        SELECT DISTINCT COLUMN_NAME
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Patient'
          AND NON_UNIQUE = 0 AND INDEX_NAME <> 'PRIMARY'
        """
    )
    return {r[0] for r in cursor.fetchall()}


def _patient_value_exists(cursor, col: str, value, col_names: set[str]) -> bool:
    if col not in col_names:
        raise ValueError(f"Unknown column {col!r}")
    cursor.execute(
        f"SELECT 1 FROM Patient WHERE `{col}` = %s LIMIT 1",
        (value,),
    )
    return cursor.fetchone() is not None


def _allocate_patient_id(cursor, seq_index: int, start: int) -> str:
    """Prefer start, start+1, ...; if taken, try other bands without updating existing rows."""
    preferred = str(start + seq_index - 1)
    if not _patient_id_exists(cursor, preferred):
        return preferred
    for base in (40000, 50000, 60000, 70000, 80000):
        cand = str(base + seq_index)
        if not _patient_id_exists(cursor, cand):
            return cand
    n = 90000 + seq_index
    while _patient_id_exists(cursor, str(n)):
        n += 1
    return str(n)


def _allocate_unique_string(
    cursor,
    col: str,
    subject_id: str,
    seq_index: int,
    patient_id: str,
    col_names: set[str],
    max_len: int | None,
) -> str:
    """Stable unique string for a UNIQUE varchar/text column; never reuses DB values."""
    cap = max_len if max_len and max_len > 0 else 64
    for salt in range(0, 5000):
        digest = hashlib.sha256(
            f"{col}|{subject_id}|{seq_index}|{patient_id}|{salt}".encode()
        ).hexdigest()
        raw = f"C{digest}"[:cap]
        if not _patient_value_exists(cursor, col, raw, col_names):
            return raw
    raise RuntimeError(f"Could not allocate unique value for column {col!r}")


def _fetch_template_row(cursor, col_names: list[str]) -> dict | None:
    cursor.execute(f"SELECT {', '.join('`' + c + '`' for c in col_names)} FROM Patient LIMIT 1")
    row = cursor.fetchone()
    if not row:
        return None
    if isinstance(row, dict):
        return {k: row.get(k) for k in col_names}
    return dict(zip(col_names, row))


def _subject_exists(cursor, subject_id: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM Patient WHERE subjectId = %s LIMIT 1",
        (subject_id,),
    )
    return cursor.fetchone() is not None


def _patient_id_exists(cursor, patient_id: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM Patient WHERE patientId = %s LIMIT 1",
        (patient_id,),
    )
    return cursor.fetchone() is not None


def main():
    parser = argparse.ArgumentParser(
        description="Insert MySQL Patient rows linking dummy patientId to block subjectId."
    )
    parser.add_argument(
        "--source",
        choices=("json", "pg"),
        default="json",
        help="Where to read subject UUIDs (default: json).",
    )
    parser.add_argument(
        "--json-path",
        type=Path,
        default=DEFAULT_JSON,
        help="Path to block summary JSON (Patient_ID).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max rows to process (default: all from source).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions only; do not insert.",
    )
    parser.add_argument(
        "--patient-id-start",
        type=int,
        default=30001,
        help="Starting numeric patientId (default: 30001).",
    )
    args = parser.parse_args()

    subject_ids = _load_subject_ids(args.source, args.json_path, args.limit)
    if not subject_ids:
        print("No subject IDs found; exiting.")
        return

    conn = _mysql_connect()
    try:
        cur_meta = conn.cursor()
        cols = _mysql_table_columns(cur_meta)
        unique_cols = _mysql_unique_index_columns(cur_meta)
        cur_meta.close()
        if not cols:
            raise RuntimeError("Patient table not found or has no columns.")

        col_names = [c["name"] for c in cols]
        col_names_set = set(col_names)
        col_meta = {c["name"]: c for c in cols}
        auto_skip = {c["name"] for c in cols if "auto_increment" in c["extra"]}

        cur_tpl = conn.cursor(dictionary=True)
        template = _fetch_template_row(cur_tpl, col_names)
        cur_tpl.close()

        if not template:
            if not {"patientId", "subjectId"}.issubset(set(col_names)):
                raise RuntimeError(
                    "Patient table is empty and schema has no patientId/subjectId; "
                    "cannot infer insert shape."
                )
            template = {n: None for n in col_names}

        cur = conn.cursor()
        inserted = 0
        skipped = 0

        for idx, subject_id in enumerate(subject_ids, start=1):
            if _subject_exists(cur, subject_id):
                print(f"[skip] subjectId already exists: {subject_id}")
                skipped += 1
                continue

            patient_id = _allocate_patient_id(cur, idx, args.patient_id_start)

            row = dict(template)
            for name in col_names:
                if name in auto_skip:
                    continue
                if name == "subjectId":
                    row[name] = subject_id
                elif name == "patientId":
                    row[name] = patient_id
                elif name in unique_cols:
                    # Keep every non-PK UNIQUE index value unique (e.g. alterntId).
                    dtype = (col_meta.get(name, {}).get("data_type") or "").lower()
                    if dtype in {"int", "integer", "smallint", "mediumint", "bigint"}:
                        cand = args.patient_id_start + idx - 1
                        while _patient_value_exists(cur, name, cand, col_names_set):
                            cand += 10000
                        row[name] = cand
                    else:
                        row[name] = _allocate_unique_string(
                            cur,
                            name,
                            subject_id,
                            idx,
                            patient_id,
                            col_names_set,
                            col_meta.get(name, {}).get("char_max"),
                        )

            insert_cols = [n for n in col_names if n not in auto_skip and n in row]
            placeholders = ", ".join(["%s"] * len(insert_cols))
            sql = (
                f"INSERT INTO Patient ({', '.join('`' + c + '`' for c in insert_cols)}) "
                f"VALUES ({placeholders})"
            )
            values = [row[c] for c in insert_cols]

            if args.dry_run:
                print(f"[dry-run] INSERT patientId={patient_id} subjectId={subject_id}")
            else:
                cur.execute(sql, values)
                inserted += 1

        cur.close()
        if not args.dry_run:
            conn.commit()
        print(
            f"Done. subjects={len(subject_ids)}, inserted={inserted}, "
            f"skipped_existing_subject={skipped}, dry_run={args.dry_run}"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
