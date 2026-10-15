"""
Priority 2 (+ optional Qdrant + API smoke test) from local against dev DBs.

Usage:
  python scripts/sync_all_patients_for_dev.py --dry-run
  python scripts/sync_all_patients_for_dev.py --apply
  python scripts/sync_all_patients_for_dev.py --apply --trigger-qdrant --test-api
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()


def count_pg_compose() -> int:
    from utils.pg_util import pg_transaction

    with pg_transaction() as (_, cur):
        cur.execute(
            """
            SELECT COUNT(*) AS n
            FROM trialgpt_eligible_patients
            WHERE structured_json IS NOT NULL
              AND summary_text IS NOT NULL
              AND BTRIM(summary_text) <> ''
            """
        )
        return int(cur.fetchone()["n"])


def count_mysql_patients() -> int:
    from utils.mysql_util import get_mysql_connection

    conn = get_mysql_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM Patient
            WHERE subjectId IS NOT NULL AND TRIM(subjectId) != ''
            """
        )
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def run_mysql_sync(dry_run: bool) -> None:
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "sync_block_patients_to_mysql.py"),
        "--source",
        "pg",
    ]
    if dry_run:
        cmd.append("--dry-run")
    print("\n=== MySQL sync (compose_summary_block -> Patient) ===")
    subprocess.check_call(cmd, cwd=str(PROJECT_ROOT))


def trigger_qdrant_ingest(base_url: str, secret: str, force: bool) -> dict:
    url = f"{base_url.rstrip('/')}/api/admin/qdrant/ingest"
    if force:
        url += "?force=true"
    headers = {"X-Qdrant-Ingest-Secret": secret}
    print(f"\n=== Qdrant ingest ===\nPOST {url}")
    r = httpx.post(url, headers=headers, timeout=120)
    r.raise_for_status()
    return r.json()


def qdrant_status(base_url: str, secret: str) -> dict:
    r = httpx.get(
        f"{base_url.rstrip('/')}/api/admin/qdrant/status",
        headers={"X-Qdrant-Ingest-Secret": secret},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def make_jwt() -> tuple[str, str]:
    raw = os.getenv("JWT_SECRET", "").strip()
    if not raw:
        raise RuntimeError("JWT_SECRET missing in .env")
    try:
        secret = base64.b64decode(raw)
    except Exception:
        secret = raw.encode("utf-8")
    prefix = os.getenv("JWT_HEADER_PREFIX", "Token")
    token = jwt.encode(
        {
            "sub": "sync-script",
            "userId": "sync-script",
            "role": "Site",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        secret,
        algorithm="HS512",
    )
    return prefix, token


def test_patient_api(base_url: str, patient_id: str) -> None:
    prefix, token = make_jwt()
    headers = {
        "Authorization": f"{prefix} {token}",
        "logged-in-user-type": "Site",
        "Content-Type": "application/json",
    }
    print(f"\n=== API smoke test patient_id={patient_id} ===")

    for path in (f"/api/patient/{patient_id}/summary", f"/api/patient/{patient_id}/diseases"):
        r = httpx.get(f"{base_url.rstrip('/')}{path}", headers=headers, timeout=30)
        print(f"GET {path} -> {r.status_code}")
        if r.status_code != 200:
            print(r.text[:300])
            return

    body = {
        "patient_id": patient_id,
        "selected_disease": ["Trauma"],
        "selected_region": ["US"],
        "retrieval_mode": "rag",
        "llm_service": "claude",
        "model": "claude-sonnet-4-6",
        "force_rerun": True,
        "debug": True,
    }
    r = httpx.post(
        f"{base_url.rstrip('/')}/api/patient-to-trials/start",
        headers=headers,
        json=body,
        timeout=60,
    )
    print(f"POST /api/patient-to-trials/start -> {r.status_code}")
    if r.status_code == 200:
        print(json.dumps(r.json(), indent=2)[:500])
    else:
        print(r.text[:300])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync all compose patients to MySQL for dev API"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview MySQL inserts only (default if no --apply)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually insert missing MySQL Patient rows",
    )
    parser.add_argument(
        "--trigger-qdrant",
        action="store_true",
        help="POST dev Qdrant ingest after sync",
    )
    parser.add_argument(
        "--qdrant-force",
        action="store_true",
        help="Use force=true on Qdrant ingest",
    )
    parser.add_argument(
        "--test-api",
        action="store_true",
        help="Smoke-test P2T on dev API",
    )
    parser.add_argument("--api-base", default="https://gpt-api.hekma.ai")
    parser.add_argument(
        "--test-patient-id",
        default="203450",
        help="Known working patient for API test",
    )
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        args.dry_run = True

    print("=== Counts (dev DBs via .env) ===")
    try:
        pg_n = count_pg_compose()
        mysql_n = count_mysql_patients()
        print(f"Postgres trialgpt_eligible_patients (ready summaries): {pg_n}")
        print(f"MySQL Patient (with subjectId):                     {mysql_n}")
        print(f"Gap (approx):                                       {max(0, pg_n - mysql_n)} need sync")
    except Exception as exc:
        print(f"Count failed: {exc}")
        return 1

    run_mysql_sync(dry_run=not args.apply)

    if args.apply and args.trigger_qdrant:
        secret = (os.getenv("QDRANT_INGEST_ADMIN_SECRET") or "").strip()
        if not secret:
            print("WARN: QDRANT_INGEST_ADMIN_SECRET not set; skip Qdrant ingest")
        else:
            try:
                print(json.dumps(trigger_qdrant_ingest(args.api_base, secret, args.qdrant_force), indent=2))
                print(json.dumps(qdrant_status(args.api_base, secret), indent=2))
            except Exception as exc:
                print(f"Qdrant ingest failed: {exc}")

    if args.test_api:
        try:
            test_patient_api(args.api_base, args.test_patient_id)
        except Exception as exc:
            print(f"API test failed: {exc}")
            return 1

    print("\nDone.")
    if args.dry_run and not args.apply:
        print("Re-run with --apply to write MySQL rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
