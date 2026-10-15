"""
Populate Postgres trialgpt_eligible_patients with MySQL subjects that have
usable Postgres FHIR clinical timestamps (~30k cohort).

Does NOT copy clinical FHIR payloads — only IDs + metadata for other uses.
TrialGPT matching still requires compose_summary_block (+ Qdrant for RAG).

Usage:
  python scripts/populate_trialgpt_eligible_patients.py
  python scripts/populate_trialgpt_eligible_patients.py --dry-run --limit 5000
  python scripts/populate_trialgpt_eligible_patients.py --page-size 2000
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from psycopg2.extras import execute_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from repositories.mysql_repo import count_source_ids, get_source_id_rows_page
from utils.pg_util import pg_transaction

DDL_PATH = PROJECT_ROOT / "migration" / "010_trialgpt_eligible_patients.sql"
DEFAULT_PAGE_SIZE = 2000


def ensure_table() -> None:
    ddl = DDL_PATH.read_text(encoding="utf-8")
    with pg_transaction() as (conn, cur):
        cur.execute(ddl)
        conn.commit()


def batch_clinical_meta(subject_ids: list[str]) -> dict[str, dict]:
    """
    For a page of subject_ids, return:
      {subject_id: {has_pg_patient, clinical_latest_ts, in_compose}}
    Only includes IDs that have a usable clinical timestamp
    (same definition as get_latest_timestamp: patient.created_at or
     max sort_date on condition/allergy/medication_order/immunization).
    """
    if not subject_ids:
        return {}

    with pg_transaction() as (_, cur):
        cur.execute(
            """
            WITH ids AS (
                SELECT unnest(%s::text[]) AS subject_id
            ),
            base AS (
                SELECT i.subject_id, p.created_at AS patient_ts,
                       (p.id IS NOT NULL) AS has_pg_patient
                FROM ids i
                LEFT JOIN patient p ON p.id = i.subject_id
            ),
            cond AS (
                SELECT patient_id, MAX(sort_date) AS ts
                FROM condition
                WHERE patient_id = ANY(%s)
                GROUP BY patient_id
            ),
            allergy AS (
                SELECT patient_id, MAX(sort_date) AS ts
                FROM allergy
                WHERE patient_id = ANY(%s)
                GROUP BY patient_id
            ),
            med AS (
                SELECT patient_id, MAX(sort_date) AS ts
                FROM medication_order
                WHERE patient_id = ANY(%s)
                GROUP BY patient_id
            ),
            imm AS (
                SELECT patient_id, MAX(sort_date) AS ts
                FROM immunization
                WHERE patient_id = ANY(%s)
                GROUP BY patient_id
            ),
            compose AS (
                SELECT patient_id
                FROM compose_summary_block
                WHERE patient_id = ANY(%s)
            )
            SELECT
                b.subject_id,
                COALESCE(b.has_pg_patient, FALSE) AS has_pg_patient,
                GREATEST(
                    b.patient_ts,
                    c.ts,
                    a.ts,
                    m.ts,
                    i.ts
                ) AS clinical_latest_ts,
                (comp.patient_id IS NOT NULL) AS in_compose
            FROM base b
            LEFT JOIN cond c ON c.patient_id = b.subject_id
            LEFT JOIN allergy a ON a.patient_id = b.subject_id
            LEFT JOIN med m ON m.patient_id = b.subject_id
            LEFT JOIN imm i ON i.patient_id = b.subject_id
            LEFT JOIN compose comp ON comp.patient_id = b.subject_id
            WHERE GREATEST(
                b.patient_ts,
                c.ts,
                a.ts,
                m.ts,
                i.ts
            ) IS NOT NULL
            """,
            (subject_ids, subject_ids, subject_ids, subject_ids, subject_ids, subject_ids),
        )
        rows = cur.fetchall() or []

    out: dict[str, dict] = {}
    for row in rows:
        sid = str(row["subject_id"]).strip()
        out[sid] = {
            "has_pg_patient": bool(row.get("has_pg_patient")),
            "clinical_latest_ts": row.get("clinical_latest_ts"),
            "in_compose": bool(row.get("in_compose")),
        }
    return out


def upsert_rows(rows: list[tuple], *, dry_run: bool) -> int:
    if not rows:
        return 0
    if dry_run:
        return len(rows)

    sql = """
        INSERT INTO trialgpt_eligible_patients (
            subject_id,
            mysql_patient_id,
            has_pg_patient,
            clinical_latest_ts,
            in_compose_summary_block,
            identified_at,
            updated_at
        )
        VALUES %s
        ON CONFLICT (subject_id) DO UPDATE SET
            mysql_patient_id = EXCLUDED.mysql_patient_id,
            has_pg_patient = EXCLUDED.has_pg_patient,
            clinical_latest_ts = EXCLUDED.clinical_latest_ts,
            in_compose_summary_block = EXCLUDED.in_compose_summary_block,
            updated_at = NOW()
    """
    with pg_transaction() as (conn, cur):
        execute_values(cur, sql, rows, page_size=500)
        conn.commit()
    return len(rows)


def populate(*, page_size: int, limit: int | None, dry_run: bool) -> dict:
    ensure_table()
    mysql_total = count_source_ids()
    offset = 0
    scanned = 0
    eligible = 0
    upserted = 0
    now = datetime.now(timezone.utc)

    while True:
        if limit is not None and scanned >= limit:
            break
        take = page_size
        if limit is not None:
            take = min(page_size, limit - scanned)

        page = get_source_id_rows_page(take, offset)
        if not page:
            break

        scanned += len(page)
        subject_ids = [r["subject_id"] for r in page]
        meta = batch_clinical_meta(subject_ids)

        batch_by_sid: dict[str, tuple] = {}
        for row in page:
            sid = row["subject_id"]
            info = meta.get(sid)
            if not info:
                continue
            # MySQL can have duplicate subjectId rows; last wins within the page.
            if sid not in batch_by_sid:
                eligible += 1
            batch_by_sid[sid] = (
                sid,
                row.get("mysql_patient_id"),
                info["has_pg_patient"],
                info["clinical_latest_ts"],
                info["in_compose"],
                now,
                now,
            )

        batch = list(batch_by_sid.values())
        upserted += upsert_rows(batch, dry_run=dry_run)
        offset += len(page)
        print(
            f"[progress] scanned={scanned} eligible={eligible} upserted={upserted}",
            file=sys.stderr,
        )
        if len(page) < take:
            break

    table_count = None
    if not dry_run:
        with pg_transaction() as (_, cur):
            cur.execute("SELECT COUNT(*) AS n FROM trialgpt_eligible_patients")
            table_count = int(cur.fetchone()["n"])

    return {
        "mysql_with_subject": mysql_total,
        "scanned": scanned,
        "eligible_identified": eligible,
        "upserted": upserted,
        "dry_run": dry_run,
        "table_row_count": table_count,
        "table": "trialgpt_eligible_patients",
        "db": "postgres (PG_DB)",
        "note": (
            "IDs + metadata only. Raw FHIR stays in patient/condition/...; "
            "TrialGPT still needs compose_summary_block for matching."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate trialgpt_eligible_patients (~30k clinical-eligible cohort)."
    )
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max MySQL subjects to scan (0 = all).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Postgres.")
    parser.add_argument(
        "--output",
        default="results/trialgpt_eligible_patients_populate.json",
        help="Write stats JSON here.",
    )
    args = parser.parse_args()

    stats = populate(
        page_size=args.page_size,
        limit=args.limit if args.limit > 0 else None,
        dry_run=args.dry_run,
    )
    text = json.dumps(stats, indent=2, default=str)
    print(text)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"[done] wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
