"""
Dev deploy verification: Qdrant + P2T + T2P end-to-end.

Usage (API must be running):
  python scripts/dev_e2e_verify.py
  python scripts/dev_e2e_verify.py --base http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

DEFAULT_PATIENT = os.getenv("VERIFY_PATIENT_ID", "203450")
DEFAULT_NCT = os.getenv("VERIFY_NCT_ID", "NCT00997100")
POLL_INTERVAL = 5
POLL_TIMEOUT = 600


def _make_token() -> str:
    raw = os.getenv("JWT_SECRET", "").strip()
    if not raw:
        raise RuntimeError("JWT_SECRET not set")
    try:
        secret = base64.b64decode(raw)
    except Exception:
        secret = raw.encode("utf-8")
    payload = {
        "sub": "dev-e2e",
        "userId": "dev-e2e-user",
        "role": "Site",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    prefix = os.getenv("JWT_HEADER_PREFIX", "Token")
    return prefix, jwt.encode(payload, secret, algorithm="HS512")


def _headers(token: str, prefix: str, user_type: str = "Site") -> dict:
    return {
        "Authorization": f"{prefix} {token}",
        "logged-in-user-type": user_type,
        "Content-Type": "application/json",
    }


def _wait_job(client: httpx.Client, base: str, job_id: str, headers: dict) -> dict:
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        try:
            r = client.get(f"{base}/api/jobs/{job_id}/status", headers=headers, timeout=60)
            r.raise_for_status()
        except (httpx.ReadError, httpx.ConnectError, httpx.TimeoutException) as exc:
            print(f"  job {job_id}: poll error ({exc}), retrying…")
            time.sleep(POLL_INTERVAL)
            continue
        data = r.json()
        status = data.get("status")
        print(f"  job {job_id}: {status}")
        if status == "COMPLETED":
            return data
        if status == "FAILED":
            raise RuntimeError(f"Job {job_id} failed: {data.get('error')}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Job {job_id} did not complete within {POLL_TIMEOUT}s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Dev E2E verify P2T + T2P")
    parser.add_argument("--base", default=os.getenv("VERIFY_API_BASE", "http://127.0.0.1:8000"))
    parser.add_argument("--patient-id", default=DEFAULT_PATIENT)
    parser.add_argument("--nct-id", default=DEFAULT_NCT)
    parser.add_argument("--ingest-secret", default=os.getenv("QDRANT_INGEST_ADMIN_SECRET", ""))
    args = parser.parse_args()
    base = args.base.rstrip("/")

    prefix, token = _make_token()
    headers = _headers(token, prefix)
    results: list[dict] = []

    with httpx.Client(timeout=60.0) as client:
        # Health
        r = client.get(f"{base}/health")
        results.append({"check": "health", "ok": r.status_code == 200, "detail": r.text[:80]})

        # Qdrant status (admin API if secret set, else direct client check)
        if args.ingest_secret:
            q_headers = {"X-Qdrant-Ingest-Secret": args.ingest_secret}
            r = client.get(f"{base}/api/admin/qdrant/status", headers=q_headers)
            q = r.json() if r.status_code == 200 else {}
        else:
            from utils.qdrant_util import get_qdrant_client
            qc = get_qdrant_client()
            pc = os.getenv("QDRANT_PATIENT_COLLECTION", "patient_profiles_hybrid_v1")
            tc = os.getenv("QDRANT_TRIAL_COLLECTION", "clinical_trials_hybrid_v1")
            q = {
                "patient_points": qc.get_collection(pc).points_count,
                "trial_points": qc.get_collection(tc).points_count,
                "status": "direct_check",
            }
        pp, tp = q.get("patient_points", 0), q.get("trial_points", 0)
        results.append({
            "check": "qdrant",
            "ok": pp > 0 and tp > 0,
            "detail": f"patients={pp} trials={tp} status={q.get('status')}",
        })

        if pp == 0 or tp == 0:
            print("WARN: Qdrant empty — trigger POST /api/admin/qdrant/ingest or restart API with auto-ingest")

        # P2T
        print("\n=== P2T ===")
        p2t_body = {
            "patient_id": args.patient_id,
            "selected_disease": ["Traumatic shock, initial encounter"],
            "selected_region": ["US"],
            "retrieval_mode": "rag",
            "llm_service": "claude",
            "model": "claude-sonnet-4-6",
            "force_rerun": True,
            "debug": True,
        }
        r = client.post(f"{base}/api/patient-to-trials/start", headers=headers, json=p2t_body)
        if r.status_code != 200:
            results.append({"check": "p2t_start", "ok": False, "detail": r.text[:200]})
        else:
            job_id = r.json()["job_id"]
            _wait_job(client, base, job_id, headers)
            r2 = client.get(f"{base}/api/jobs/{job_id}/results", headers=headers)
            body = r2.json()
            evals = body.get("evaluations") or []
            results.append({
                "check": "p2t_results",
                "ok": r2.status_code == 200 and len(evals) > 0,
                "detail": f"job={job_id} trials={len(evals)}",
            })

        # T2P
        print("\n=== T2P ===")
        t2p_body = {
            "nct_id": args.nct_id,
            "site_id": "site-dev-001",
            "prospective_patient_count": 10,
            "retrieval_mode": "rag",
            "llm_service": "claude",
            "model": "claude-sonnet-4-6",
            "debug": True,
        }
        r = client.post(f"{base}/api/trial-to-patients/start", headers=headers, json=t2p_body)
        if r.status_code != 200:
            results.append({"check": "t2p_start", "ok": False, "detail": r.text[:200]})
        else:
            job_id = r.json()["job_id"]
            _wait_job(client, base, job_id, headers)
            r2 = client.get(f"{base}/api/jobs/{job_id}/results", headers=headers)
            body = r2.json()
            patients = body.get("evaluations") or body.get("patients") or []
            if isinstance(body, dict) and not patients:
                patients = body.get("ranked_patients") or []
            results.append({
                "check": "t2p_results",
                "ok": r2.status_code == 200,
                "detail": f"job={job_id} patients={len(patients) if isinstance(patients, list) else 'see body'}",
            })

    print("\n=== SUMMARY ===")
    failed = 0
    for row in results:
        mark = "PASS" if row["ok"] else "FAIL"
        if not row["ok"]:
            failed += 1
        print(f"  [{mark}] {row['check']}: {row['detail']}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
