# P2T and T2P End-to-End Runbook

This document gives a clean, practical sequence to run and validate both flows:

- P2T (Patient -> Trials)
- T2P (Trial -> Patients)

It includes both `legacy` and `rag` modes.

## 1) Prerequisites

- Python venv is available and dependencies installed.
- API server can run from project root.
- PostgreSQL is reachable with valid `.env` values.
- Qdrant is running on `localhost:6333` (for RAG mode).
- Trial corpus and compose summary data are already loaded.

## 2) Start API

From project root:

```powershell
cd "C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt"
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```http
GET http://127.0.0.1:8000/health
```

---

## 3) Prepare RAG Patient Index (T2P/P2T RAG)

Run this whenever RAG hydration mismatch appears, or on fresh environments.

### 3.1 Export compose profiles for ingestion

```powershell
cd "C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt"
.\.venv\Scripts\Activate.ps1
python .\scripts\export_compose_profiles_for_qdrant.py
```

Expected output file:

- `TrialGPT_RAG/patient_block_summaries.from_compose.json`

### 3.2 Re-ingest patient vectors in Qdrant

```powershell
cd "C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt\TrialGPT_RAG"
python .\ingest_patients_block.py `
  --json-path "C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt\TrialGPT_RAG\patient_block_summaries.from_compose.json" `
  --batch-size 50 `
  --recreate
```

---

## 4) P2T Run and Validation

### 4.1 Start P2T

```http
POST /api/patient-to-trials/start
```

Payload example:

```json
{
  "patient_id": "203375",
  "selected_disease": ["diabetes"],
  "selected_region": ["Hefei, Anhui, China"],
  "retrieval_mode": "rag",
  "debug": true
}
```

### 4.2 Check status

```http
GET /api/jobs/{job_id}/status
```

Expect all stages `COMPLETED`.

### 4.3 Check results

```http
GET /api/jobs/{job_id}/results
```

### 4.4 Check trial inference

Use a `trial_id` from results:

```http
GET /api/jobs/{job_id}/nct-inference?nct_id=<trial_id_from_results>
```

---

## 5) T2P Run and Validation

### 5.1 Start T2P

```http
POST /api/trial-to-patients/start
```

Payload example:

```json
{
  "nct_id": "NCT00002288",
  "site_id": "SITE-1",
  "prospective_patient_count": 20,
  "retrieval_mode": "rag",
  "debug": true
}
```

### 5.2 Check status

```http
GET /api/jobs/{job_id}/status
```

### 5.3 Check results

```http
GET /api/jobs/{job_id}/results
```

### 5.4 Check patient inference

Use a `patient_id` from results:

```http
GET /api/jobs/{job_id}/patient-inference?patient_id=<patient_id_from_results>
```

Note:
- This endpoint accepts both external patient id and subject UUID.

---

## 6) Legacy vs RAG Comparison

For fair comparison, use the same input and run twice:

1. `retrieval_mode: "legacy"`
2. `retrieval_mode: "rag"`

Compare:

- top candidates
- eligibility scores
- inference reasoning
- count of returned evaluations

---

## 7) Troubleshooting

- `evaluations: []` in T2P RAG:
  - Check logs for `RAG hydrated summaries kept=0 requested=X`.
  - Re-run compose export + patient re-ingestion.

- `Subject ID not found` on patient inference:
  - Ensure API is restarted on latest code.
  - Confirm `patient_id` is from that job's result list.

- `fastembed unavailable; using hashed sparse fallback`:
  - Pipeline still works.
  - Install/fix `onnxruntime`/`fastembed` if full sparse model is required.

---

## 8) Quick Acceptance Checklist

- P2T `status` completed and `results` non-empty
- P2T `nct-inference` returns `failed=false`
- T2P `status` completed and `results` non-empty
- T2P `patient-inference` returns `failed=false`
- RAG debug logs show retrieval and hydration counts
