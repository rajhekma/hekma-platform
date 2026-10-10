#!/usr/bin/env python3
"""Local-only Hekma-styled AI cost dashboard.

Not for deployment. Read-only view of the cost ledger.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

HERE = Path(__file__).resolve().parent
COST_BASE = os.getenv("AI_COST_BASE_URL", "http://127.0.0.1:8090").rstrip("/")

app = FastAPI(title="Local AI cost UI", docs_url=None, redoc_url=None)


def _cost(patient_id: str) -> dict:
    response = requests.get(
        f"{COST_BASE}/v1/patients/{patient_id}/ai-cost",
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


@app.get("/")
def index():
    return FileResponse(HERE / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/cost")
def cost(patient_id: str):
    patient_id = patient_id.strip()
    if not patient_id:
        raise HTTPException(400, "patient_id is required")
    try:
        return _cost(patient_id)
    except requests.RequestException as exc:
        raise HTTPException(502, f"Cost API is not reachable at {COST_BASE}: {exc}") from exc


@app.get("/api/events")
def events(patient_id: str, limit: int = 200):
    patient_id = patient_id.strip()
    if not patient_id:
        raise HTTPException(400, "patient_id is required")
    limit = max(1, min(int(limit or 200), 500))
    try:
        response = requests.get(
            f"{COST_BASE}/v1/patients/{patient_id}/ai-cost/events",
            params={"limit": limit},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise HTTPException(502, f"Cost API is not reachable at {COST_BASE}: {exc}") from exc


@app.get("/api/prices")
def prices():
    try:
        response = requests.get(f"{COST_BASE}/v1/ai-cost/prices", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise HTTPException(502, f"Cost API is not reachable at {COST_BASE}: {exc}") from exc


if __name__ == "__main__":
    port = int(os.getenv("COST_UI_PORT", "8091"))
    uvicorn.run(app, host="127.0.0.1", port=port)
