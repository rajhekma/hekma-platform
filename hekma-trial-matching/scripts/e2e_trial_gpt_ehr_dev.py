#!/usr/bin/env python3
"""E2E verify trial_gpt_ehr ingest on dev gpt-api (gpt.test.hekma.ai)."""

from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

DEFAULT_DEV_BASE = "https://gpt.test.hekma.ai"
_SSL_CTX = ssl.create_default_context()
try:
    import certifi

    _SSL_CTX.load_verify_locations(certifi.where())
except Exception:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE


def _jwt_headers() -> dict[str, str]:
    raw = os.getenv("JWT_SECRET", "").strip()
    if not raw:
        raise RuntimeError("JWT_SECRET not set in .env")
    try:
        secret = base64.b64decode(raw)
    except Exception:
        secret = raw.encode("utf-8")
    prefix = os.getenv("JWT_HEADER_PREFIX", "Token")
    token = jwt.encode(
        {
            "sub": "e2e-trial-gpt-ehr",
            "userId": "e2e",
            "role": "Site",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        secret,
        algorithm="HS512",
    )
    return {
        "Authorization": f"{prefix} {token}",
        "logged-in-user-type": "Site",
        "Content-Type": "application/json",
    }


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    timeout: int = 30,
) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def _db_snapshot(patient_id: str) -> dict:
    from repositories import fastenhealth_repo, trial_gpt_ehr_repo
    from repositories.mysql_repo import get_patient_identity

    identity = get_patient_identity(patient_id)
    if not identity:
        return {"ok": False, "error": "patient not in MySQL"}
    mid = int(identity["mysql_patient_id"])
    row = trial_gpt_ehr_repo.fetch_ehr_status_row(mysql_patient_id=mid, llm=True)
    diseases = trial_gpt_ehr_repo.fetch_disease_list(mysql_patient_id=mid, llm=True) or []
    export = fastenhealth_repo.export_fasten_patient_data(str(mid), skip_large_tables=True)
    fasten_rows = sum(len(v) for v in (export or {}).values())
    err = None
    if row:
        structured = row.get("structured_json") or {}
        if isinstance(structured, dict):
            err = structured.get("error")
    return {
        "mysql_patient_id": mid,
        "fasten_rows": fasten_rows,
        "summary_status": (row or {}).get("summary_status"),
        "disease_count": len(diseases),
        "error": err,
    }


def _local_ingest(patient_id: str, *, force: bool) -> dict:
    from services.trial_gpt_ehr_ingest_service import ensure_trial_gpt_ehr_ready

    result = ensure_trial_gpt_ehr_ready(
        patient_id,
        trigger="e2e_local_fix",
        force=force,
        skip_inflight_guard=True,
    )
    return {"status": result.status, "modes": result.modes_written}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patient_id", default="203578", nargs="?")
    parser.add_argument("--base", default=os.getenv("TRIALGPT_API_BASE_URL", DEFAULT_DEV_BASE))
    parser.add_argument("--trigger-remote", action="store_true", help="POST internal ingest on dev gpt-api")
    parser.add_argument("--local-fix", action="store_true", help="Run ingest locally with fixed bridge code")
    parser.add_argument("--wait-seconds", type=int, default=180)
    args = parser.parse_args()

    base = args.base.rstrip("/")
    patient = str(args.patient_id).strip()
    print(f"\n=== trial_gpt_ehr E2E | patient={patient} | api={base} ===\n")

    code, health = _http_json("GET", f"{base}/health")
    print(f"[{'OK' if code == 200 else 'FAIL'}] health {code} {health}")

    db_before = _db_snapshot(patient)
    print(f"[INFO] db before: {json.dumps(db_before, default=str)}")

    if args.trigger_remote:
        key = os.getenv("TRIALGPT_EHR_INGEST_API_KEY", "").strip()
        if not key:
            print("[FAIL] TRIALGPT_EHR_INGEST_API_KEY missing")
            return 1
        code, body = _http_json(
            "POST",
            f"{base}/api/internal/trial-gpt-ehr/ingest",
            headers={"X-Hekma-Internal-Key": key, "Content-Type": "application/json"},
            body={"patient_id": patient, "trigger": "e2e_dev", "force": True},
        )
        print(f"[{'OK' if code in (200, 202) else 'FAIL'}] remote ingest {code} {body}")

    if args.local_fix:
        print("[INFO] running local ingest with bundled bridge...")
        try:
            result = _local_ingest(patient, force=True)
            print(f"[OK] local ingest {result}")
        except Exception as exc:
            print(f"[FAIL] local ingest {type(exc).__name__}: {exc}")
            return 1

    headers = _jwt_headers()
    deadline = time.time() + args.wait_seconds
    last_api = None
    while time.time() < deadline:
        code, body = _http_json(
            "GET",
            f"{base}/api/patient/{patient}/diseases",
            headers=headers,
        )
        if isinstance(body, dict):
            last_api = body
            print(
                f"poll diseases | http={code} | ehr_status={body.get('ehr_status')} | "
                f"stage={body.get('stage')} | pct={body.get('progress_percent')} | "
                f"msg={str(body.get('message', ''))[:100]}"
            )
            if body.get("ehr_status") == "ready" and body.get("diseases"):
                print(f"\n[SUCCESS] diseases={len(body['diseases'])}")
                return 0
        else:
            print(f"poll diseases | http={code} | {str(body)[:120]}")
        time.sleep(5)

    db_after = _db_snapshot(patient)
    print(f"\n[INFO] db after: {json.dumps(db_after, default=str)}")
    print(f"[INFO] last API: {json.dumps(last_api, default=str)[:800]}")
    print("\n[FAIL] TIMEOUT — dev gpt-api likely missing deploy cb5be38 (bundled bridge fix)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
