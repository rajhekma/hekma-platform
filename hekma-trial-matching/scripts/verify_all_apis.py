"""Smoke-test every Swagger-documented endpoint on the running TrialGPT API."""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from dotenv import load_dotenv

load_dotenv()

BASE = os.getenv("VERIFY_API_BASE", "http://127.0.0.1:8000")
PREFIX = os.getenv("JWT_HEADER_PREFIX", "Token")


def _make_token() -> str:
    raw = os.getenv("JWT_SECRET", "").strip()
    if not raw:
        raise RuntimeError("JWT_SECRET not set in .env")
    try:
        secret = base64.b64decode(raw)
    except Exception:
        secret = raw.encode("utf-8")
    payload = {
        "sub": "api-verify",
        "userId": "verify-user-001",
        "role": "Patient",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm="HS512")


def _auth_headers(token: str) -> dict:
    return {
        "Authorization": f"{PREFIX} {token}",
        "logged-in-user-type": "Patient",
    }


def _check(name: str, method: str, path: str, *, headers=None, json_body=None, params=None, ok_statuses=None, timeout=30.0):
    ok_statuses = ok_statuses or {200, 201, 202}
    url = f"{BASE}{path}"
    try:
        r = httpx.request(method, url, headers=headers, json=json_body, params=params, timeout=timeout)
        body = r.text[:300]
        if r.status_code in ok_statuses:
            return {"endpoint": name, "status": "PASS", "code": r.status_code, "detail": body[:120]}
        if r.status_code in (401, 403):
            return {"endpoint": name, "status": "AUTH_FAIL", "code": r.status_code, "detail": body[:120]}
        if r.status_code in (404, 400, 422):
            return {"endpoint": name, "status": "OK_ROUTE", "code": r.status_code, "detail": body[:120]}
        return {"endpoint": name, "status": "FAIL", "code": r.status_code, "detail": body[:200]}
    except Exception as e:
        return {"endpoint": name, "status": "ERROR", "code": None, "detail": str(e)}


def main() -> int:
    # Wait for server
    for _ in range(20):
        try:
            if httpx.get(f"{BASE}/health", timeout=2.0).status_code == 200:
                break
        except Exception:
            time.sleep(0.5)
    else:
        print("ERROR: Server not reachable at", BASE)
        return 1

    token = _make_token()
    auth = _auth_headers(token)
    dummy_job = os.getenv("VERIFY_JOB_ID", "693a398e-50a5-4b96-bed4-3ddc2c7d012d")
    dummy_t2p_job = os.getenv("VERIFY_T2P_JOB_ID", "8006fbf2-d7b9-48e7-ad23-dfc4d46061ef")
    dummy_patient = os.getenv("VERIFY_PATIENT_ID", "203375")
    dummy_subject = os.getenv("VERIFY_SUBJECT_ID", "004fec23-6023-572a-922e-6d73b325e771")
    dummy_annotation_pid = os.getenv("VERIFY_ANNOTATION_PID", "00bf0672-1125-5fee-b375-838a4e4628a1")
    dummy_validation_patient = os.getenv("VERIFY_VALIDATION_PATIENT", "00000027-c5e0-554f-8e85-b097c3b177d4")
    dummy_nct = os.getenv("VERIFY_NCT_ID", "NCT00997100")

    tests = [
        ("GET /health", "GET", "/health"),
        ("POST /batch/refresh-patient-summaries", "POST", "/batch/refresh-patient-summaries", {"headers": auth, "ok_statuses": {200, 201, 202, 504}}),
        ("POST /api/trials/ingest", "POST", "/api/trials/ingest", {"json_body": {}}),
        ("POST /mimic/summaries", "POST", "/mimic/summaries", {"params": {"patient_id": dummy_patient}}),
        ("POST /api/patient-to-trials/start", "POST", "/api/patient-to-trials/start", {
            "headers": auth,
            "json_body": {
                "patient_id": dummy_patient,
                "selected_disease": "lupus",
                "selected_region": "United States",
            },
        }),
        ("POST /api/trial-to-patients/start", "POST", "/api/trial-to-patients/start", {
            "headers": {**auth, "logged-in-user-type": "Site"},
            "json_body": {
                "nct_id": dummy_nct,
                "site_id": "site-1",
                "prospective_patient_count": 5,
            },
        }),
        ("GET /api/jobs/{job_id}/status", "GET", f"/api/jobs/{dummy_job}/status", {"headers": auth}),
        ("GET /api/jobs/{job_id}/results", "GET", f"/api/jobs/{dummy_job}/results", {"headers": auth}),
        ("GET /api/jobs/{job_id}/nct-inference", "GET", f"/api/jobs/{dummy_job}/nct-inference", {"params": {"nct_id": dummy_nct}}),
        ("GET /api/jobs/{job_id}/patient-inference", "GET", f"/api/jobs/{dummy_t2p_job}/patient-inference", {
            "headers": auth,
            "params": {"patient_id": dummy_subject},
        }),
        ("GET /api/trials/regions", "GET", "/api/trials/regions", {"headers": auth, "params": {"disease": "lupus"}}),
        ("GET /api/patient/{patient_id}/diseases", "GET", f"/api/patient/{dummy_patient}/diseases", {"headers": auth}),
        ("GET /api/jobs", "GET", "/api/jobs", {"headers": auth, "params": {"patient_id": dummy_patient}}),
        ("GET /api/patient/{patient_id}/summary", "GET", f"/api/patient/{dummy_patient}/summary", {"headers": auth}),
        ("GET /api/patient/{patient_id}/jobs-with-results", "GET", f"/api/patient/{dummy_patient}/jobs-with-results", {"headers": auth}),
        # Patient Annotations
        ("GET /api/annotations/patients", "GET", "/api/annotations/patients"),
        ("POST /api/annotations/patients/upload", "POST", "/api/annotations/patients/upload", {"json_body": {"data": {}}}),
        ("GET /api/annotations/patients/{pid}", "GET", f"/api/annotations/patients/{dummy_annotation_pid}"),
        ("POST /api/annotations/patients/{pid}/comments", "POST", f"/api/annotations/patients/{dummy_annotation_pid}/comments", {
            "json_body": {"trial_index": 0, "type": "trial_fields", "fields": {}},
        }),
        ("GET /api/annotations/patients/{pid}/final-json", "GET", f"/api/annotations/patients/{dummy_annotation_pid}/final-json"),
        ("GET /api/annotations/patients/final-json/all", "GET", "/api/annotations/patients/final-json/all", {"ok_statuses": {200, 504}}),
        # Trial Match Validation
        ("GET /api/trial-match-validation/patients", "GET", "/api/trial-match-validation/patients", {"headers": auth}),
        ("GET /api/trial-match-validation/patients/{patient_id}", "GET", f"/api/trial-match-validation/patients/{dummy_validation_patient}", {"headers": auth}),
        ("POST /api/trial-match-validation/patients/{patient_id}/validate", "POST", f"/api/trial-match-validation/patients/{dummy_validation_patient}/validate", {
            "headers": auth,
            "json_body": {"refresh_patient_360": False, "use_llm": False, "persist": False},
        }),
    ]

    results = []
    for item in tests:
        name, method, path = item[0], item[1], item[2]
        kwargs = item[3] if len(item) > 3 else {}
        if "timeout" not in kwargs and ("batch/refresh" in path or "final-json/all" in path):
            kwargs["timeout"] = 120.0
        results.append(_check(name, method, path, **kwargs))

    # Also verify OpenAPI lists all routes
    openapi = httpx.get(f"{BASE}/openapi.json", timeout=10.0).json()
    registered = sorted(openapi.get("paths", {}).keys())

    print("\n=== API Verification Report ===\n")
    fails = []
    for r in results:
        icon = {"PASS": "OK", "OK_ROUTE": "OK", "AUTH_FAIL": "!!", "FAIL": "XX", "ERROR": "XX"}.get(r["status"], "?")
        print(f"[{icon}] {r['endpoint']:55} HTTP {r['code']}  {r['status']}")
        if r["status"] in ("FAIL", "ERROR", "AUTH_FAIL"):
            print(f"     -> {r['detail']}")
            fails.append(r)

    print(f"\nRegistered routes ({len(registered)}):")
    for p in registered:
        print(f"  {p}")

    print(f"\nSummary: {len(results) - len(fails)}/{len(results)} endpoints reachable")
    if fails:
        print(f"Issues: {len(fails)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
