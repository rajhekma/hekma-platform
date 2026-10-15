#!/usr/bin/env python3
"""
End-to-end diagnostic for trial_gpt_ehr ingest after Fasten EHR export.

Checks each stage independently:
  1. MySQL patient identity
  2. Fasten PG tables (fastenhealth_*)
  3. trial_gpt_ehr row (summary_status, diseases)
  4. Optional: POST internal ingest (same as lambda after export)
  5. Optional: poll until ready

Read APIs (/diseases) do NOT start ingest — only internal POST or ?wait=true does.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from repositories import fastenhealth_repo, trial_gpt_ehr_repo  # noqa: E402
from repositories.mysql_repo import get_patient_identity  # noqa: E402
from services.trial_gpt_ehr_ingest_service import (  # noqa: E402
    STALE_INGESTING_ROW_SECONDS,
    is_stale_ingesting_row,
)
from services.trial_gpt_ehr_read_service import get_patient_ehr_status  # noqa: E402


def _age_seconds(updated_at) -> float | None:
    if not isinstance(updated_at, datetime):
        return None
    return (datetime.utcnow() - updated_at).total_seconds()


def check_stages(patient_id: str) -> dict:
    """Return a dict describing each pipeline stage for patient_id."""
    out: dict = {"patient_id": patient_id, "stages": {}}

    identity = get_patient_identity(patient_id)
    out["stages"]["mysql"] = {
        "ok": bool(identity),
        "detail": identity,
    }
    if not identity:
        return out

    mysql_id = int(identity["mysql_patient_id"])
    fasten_ok = fastenhealth_repo.has_clinical_data(str(mysql_id))
    export_data = fastenhealth_repo.export_fasten_patient_data(str(mysql_id), skip_large_tables=True)
    row_count = sum(len(rows) for rows in (export_data or {}).values())
    latest_ts = fastenhealth_repo.get_fasten_clinical_latest_ts(str(mysql_id))

    out["stages"]["fasten_pg"] = {
        "ok": bool(fasten_ok and row_count > 0),
        "has_clinical_data": fasten_ok,
        "clinical_latest_ts": str(latest_ts) if latest_ts else None,
        "clinical_rows": row_count,
        "tables": len(export_data or {}),
    }

    row = trial_gpt_ehr_repo.fetch_ehr_status_row(mysql_patient_id=mysql_id, llm=True)
    status = (row or {}).get("summary_status")
    updated = (row or {}).get("updated_at")
    age = _age_seconds(updated)
    stale = is_stale_ingesting_row(mysql_id, llm=True)

    diseases = trial_gpt_ehr_repo.fetch_disease_list(mysql_patient_id=mysql_id, llm=True) or []

    out["stages"]["trial_gpt_ehr"] = {
        "ok": status == "ready" and bool(diseases),
        "summary_status": status,
        "updated_at": str(updated) if updated else None,
        "age_seconds": round(age, 1) if age is not None else None,
        "stale_ingesting": stale,
        "stale_threshold_sec": STALE_INGESTING_ROW_SECONDS,
        "disease_count": len(diseases),
        "diseases_preview": diseases[:5],
    }

    ehr_status = get_patient_ehr_status(patient_id)
    out["stages"]["read_api"] = {
        "ehr_status": ehr_status.get("ehr_status"),
        "note": "GET /diseases is read-only; returns preparing until trial_gpt_ehr ready",
    }

    return out


def trigger_internal_ingest(patient_id: str, *, force: bool = True) -> dict:
    """POST internal ingest (same contract as lambda trial_gpt_ehr_client)."""
    import requests

    base = os.getenv("TRIALGPT_API_BASE_URL", "http://127.0.0.1:8000").strip().rstrip("/")
    key = os.getenv("TRIALGPT_EHR_INGEST_API_KEY", "").strip()
    if not key:
        return {"error": "TRIALGPT_EHR_INGEST_API_KEY not set in .env"}

    url = f"{base}/api/internal/trial-gpt-ehr/ingest"
    resp = requests.post(
        url,
        json={
            "patient_id": str(patient_id),
            "trigger": "diagnose_ehr_ingest",
            "force": force,
        },
        headers={"X-Hekma-Internal-Key": key},
        timeout=15,
    )
    return {"url": url, "status_code": resp.status_code, "body": resp.text[:500]}


def print_report(report: dict) -> None:
    print(f"\n=== E2E ingest diagnostic | patient_id={report['patient_id']} ===\n")
    for name, stage in report["stages"].items():
        ok = stage.get("ok")
        flag = "OK" if ok is True else ("FAIL" if ok is False else "—")
        print(f"[{flag}] {name}")
        for k, v in stage.items():
            if k == "ok":
                continue
            print(f"      {k}: {v}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patient_id", help="MySQL patientId e.g. 203578")
    parser.add_argument(
        "--trigger",
        action="store_true",
        help="POST internal ingest (lambda-equivalent) then poll",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=True,
        help="force=true on internal ingest (default: true)",
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=0,
        help="Poll ehr-status every 5s for N seconds after --trigger",
    )
    args = parser.parse_args()
    patient_id = str(args.patient_id).strip()

    report = check_stages(patient_id)
    print_report(report)

    fasten_ok = report["stages"].get("fasten_pg", {}).get("ok")
    ehr_ok = report["stages"].get("trial_gpt_ehr", {}).get("ok")

    if fasten_ok and not ehr_ok:
        print(
            "GAP DETECTED: Fasten PG has data but trial_gpt_ehr is not ready.\n"
            "  → EHR pull succeeded; LLM ingest step did not finish.\n"
            "  → Check lambda logs for 'trial_gpt_ehr notify' and gpt-api for 'background worker'.\n"
            "  → Run with --trigger to replay lambda POST.\n"
        )

    if args.trigger:
        print("Triggering internal ingest...")
        result = trigger_internal_ingest(patient_id, force=args.force)
        print(result)
        if args.wait_seconds <= 0:
            args.wait_seconds = 180

    if args.wait_seconds > 0:
        deadline = time.time() + args.wait_seconds
        while time.time() < deadline:
            status = get_patient_ehr_status(patient_id)
            diseases = trial_gpt_ehr_repo.fetch_disease_list(
                mysql_patient_id=int(get_patient_identity(patient_id)["mysql_patient_id"]),
                llm=True,
            )
            print(
                f"poll | ehr_status={status.get('ehr_status')} | "
                f"summary_status={status.get('summary_status')} | diseases={len(diseases or [])}"
            )
            if status.get("ehr_status") == "ready" and diseases:
                print("SUCCESS: trial_gpt_ehr ready")
                return
            time.sleep(5)
        print("TIMEOUT: trial_gpt_ehr did not become ready — check gpt-api logs for trial_gpt_ehr")


if __name__ == "__main__":
    main()
