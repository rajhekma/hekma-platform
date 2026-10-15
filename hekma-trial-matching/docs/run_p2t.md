# P2T (Patient-to-Trials) — Complete Run Guide

This document covers every step needed to set up and run the P2T flow end-to-end,
from a fresh environment to getting results in Postman.

---

## Architecture Overview

```
dataset/annot_20_patient.json          (source of truth: 20 patients × 58 trials)
         │
         ├──► Postgres compose_summary_block    (patient summaries + disease lists)
         ├──► Postgres trialgpt_corpus          (trial text + criteria)
         ├──► MySQL   Patient                   (external patientId → UUID mapping)
         └──► Qdrant  patient + trial vectors   (RAG vector search)
                                │
                    POST /api/patient-to-trials/start
                                │
              ┌─────────────────▼──────────────────┐
              │  1. compose   – LLM keyword gen    │
              │  2. retrieve  – Qdrant RAG top-58  │
              │  3. evaluate  – LLM per-criterion  │
              │  4. rank      – score + persist    │
              └─────────────────┬──────────────────┘
                                │
              GET /results  ·  GET /nct-inference
```

---

## Prerequisites

| Requirement | Details |
|---|---|
| Python | 3.10+ |
| PostgreSQL | Remote: `87.106.50.234:5432` db=`hekmaai` |
| MySQL | Remote: `dev-hekmadb.cyjz2t0etrbb.us-east-1.rds.amazonaws.com` db=`operations` |
| Qdrant | Running locally on `localhost:6333` |
| OpenAI API key | Set in `.env` |
| Dataset file | `dataset/annot_20_patient.json` (20 patients, 58 trials) |

---

## Step 0 — Environment Setup

### 0.1 Clone and enter the project

```powershell
cd C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt
```

### 0.2 Create and activate virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 0.3 Install dependencies

```powershell
pip install -r requirements.txt
pip install qdrant-client fastembed psycopg2-binary
```

### 0.4 Configure `.env`

Create a `.env` file in the project root with these values:

```env
# LLM Keys
OPENAI_API_KEY=<your-openai-api-key>

# PostgreSQL (patient summaries + trial corpus + job results)
PG_HOST=localhost
PG_PORT=5433
PG_DB=hekma_platform
PG_USER=hekma
PG_PASSWORD=<set-in-env>

# JWT (API authentication)
JWT_SECRET=<generate-a-strong-secret>
JWT_ALGORITHM=HS512
JWT_HEADER_PREFIX=Token
```

> MySQL credentials are hardcoded in `utils/mysql_util.py` (host: `dev-hekmadb...`, db: `operations`).
> Qdrant runs locally — start it before running the API.

---

## Step 1 — Load Patients into Postgres (`compose_summary_block`)

This loads the 20 patient summaries and block JSON from the annot dataset into Postgres.
It also calls the LLM once per patient to generate `disease_list`.

```powershell
cd C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt
.\.venv\Scripts\Activate.ps1

python scripts\load_compose_summary_block.py `
  --json-path "C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt\dataset\annot_20_patient.json"
```

**Expected output:**
```
Loaded 20 records into compose_summary_block.
```

**What this does:**
- Creates `compose_summary_block` table if it doesn't exist
- Upserts 20 rows: `patient_id`, `summary_text`, `structured_json`, `disease_list`
- `disease_list` is generated via OpenAI LLM (~20 small API calls, one per patient)

> Note: `--skip-disease-llm` exists but do **not** use it. The P2T workflow does not
> read `disease_list` today, but the field should be populated for future compatibility.

> **To reload cleanly** (wipe old data first):
> Connect to Postgres and run: `TRUNCATE TABLE compose_summary_block;`
> Then re-run the load script above.

---

## Step 2 — Load Trials into Postgres (`trialgpt_corpus`)

The 58 annot trials must be in `trialgpt_corpus` so the API can hydrate RAG results.

Use the trial ingestion API or run the ingestion script. The annot file already contains
full trial text. You can insert via the API endpoint:

**POST** `http://127.0.0.1:8000/api/ingest/trial`

Or load trials directly from the annot JSON using a script. If `trialgpt_corpus` already
contains the 58 annot NCTs (check with a quick SELECT), skip this step.

**Quick check:**
```sql
-- Run in your Postgres client
SELECT count(*) FROM trialgpt_corpus
WHERE nct_id IN ('NCT00997100','NCT01187901','NCT02238756','NCT01745731',
                 'NCT02340533','NCT00841789','NCT00180739','NCT00880347',
                 'NCT01139632','NCT00236912');
-- Should return 10 (or 58 for full annot set check)
```

---

## Step 3 — Map Patients in MySQL (`Patient` table)

This creates the `patientId → subjectId` mapping that the API uses to look up patients.

```powershell
cd C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt
.\.venv\Scripts\Activate.ps1

python scripts\sync_block_patients_to_mysql.py --source json `
  --json-path "C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt\dataset\annot_20_patient.json"
```

**Expected output:**
```
Done. subjects=20, inserted=20, skipped_existing_subject=0, dry_run=False
```

If you see `skipped_existing_subject=20` — the mapping already exists, no action needed.

**What this does:**
- Reads `Patient_ID` UUIDs from the annot JSON
- Inserts rows into MySQL `Patient` table: `patientId` (e.g. `203375`) → `subjectId` (UUID)

**Resulting patient ID mapping:**

| `patientId` (use in API) | Key diseases |
|---|---|
| `203375` | Systemic Lupus Erythematosus, Chronic Liver Disease |
| `203390` | Atrial Fibrillation, Congestive Heart Failure |
| `203395` | Asthma, Hypothyroidism |
| `203442` | Osteoarthrosis, Hemochromatosis |
| `203443` | Hypothyroidism, Esophageal Reflux |
| `203446` | Hypertension, Type II Diabetes Mellitus |
| `203447` | Malignant Brain Neoplasm, Normal Pressure Hydrocephalus |
| `203448` | Convulsions, Brain Meninges Neoplasm |
| `203449` | Hypertension, Osteoarthrosis |
| `203450` | Traumatic Shock, Pneumothorax |
| `203452` | Malignant Melanoma, Epilepsy |
| `203453` | Hypertension, Urinary Calculi |
| `203455` | Accidental Poisoning by Heroin |
| `203439–203445` | Various (some have no diseases) |

---

## Step 4 — Ingest Vectors into Qdrant (RAG)

RAG retrieval needs vector representations of both patients and trials in Qdrant.

### 4.1 Export patient block profiles from Postgres

```powershell
cd C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt
python scripts\export_compose_profiles_for_qdrant.py
```

**Expected output:**
```
[done] Exported 20 compose profiles to 'TrialGPT_RAG\patient_block_summaries.from_compose.json'.
```

### 4.2 Ingest patient vectors into Qdrant

```powershell
cd C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt\TrialGPT_RAG

python ingest_patients_block.py `
  --json-path "C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt\TrialGPT_RAG\patient_block_summaries.from_compose.json" `
  --batch-size 20 `
  --recreate
```

**Expected output:**
```
[init] Dropped existing collection 'patient_profiles_hybrid_v1'.
[init] Collection 'patient_profiles_hybrid_v1' created.
Ingesting patients: 100%|██████████| 20/20
[done] Ingested 20 patients into 'patient_profiles_hybrid_v1'.
```

`--recreate` wipes the collection first. Remove it to upsert without wiping.

### 4.3 Prepare and ingest trial vectors into Qdrant

First, export the 58 annot trials to JSONL format (the ingest script needs JSONL):

```python
# Run this Python snippet once to create trials_annot.jsonl
import json
from pathlib import Path

annot = json.load(open(r"C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt\dataset\annot_20_patient.json", encoding="utf-8"))
seen = set()
lines = []
for patient in annot:
    for trial in patient.get("Trials", []):
        nct = trial["Trail_ID"]
        if nct in seen:
            continue
        seen.add(nct)
        tt = trial.get("Trail_text") or {}
        lines.append(json.dumps({
            "_id": nct,
            "title": tt.get("title", ""),
            "text": tt.get("text", ""),
            "metadata": tt.get("metadata") or {},
        }, ensure_ascii=True))

Path(r"C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt\TrialGPT_RAG\trials_annot.jsonl").write_text(
    "\n".join(lines) + "\n", encoding="utf-8"
)
print(f"Exported {len(lines)} trials")
```

Then ingest into Qdrant:

```powershell
cd C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt\TrialGPT_RAG

python main.py `
  --corpus "trials_annot.jsonl" `
  --recreate `
  --no-ingest
# Remove --no-ingest to run the actual ingest (it will embed all 58 trials)
```

Or use the `ingestion.py` directly:

```python
# Run from TrialGPT_RAG/ folder
from ingestion import ingest_corpus
ingest_corpus("trials_annot.jsonl", batch_size=20, recreate=True)
```

**Expected Qdrant state after Steps 4.2 + 4.3:**
```
patient_profiles_hybrid_v1 : 20 points
clinical_trials_hybrid_v1  : 58 points
```

---

## Step 5 — Check Port and Start the API

### 5.1 Free port 8000 if blocked

```powershell
# Find what is using port 8000
netstat -ano | findstr ":8000"

# Kill it (replace 12345 with the PID shown above)
taskkill /PID 12345 /F
```

### 5.2 Start the API server

```powershell
cd C:\Users\ADMIN\Documents\Hekma_gpt\trailgpt
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

**Expected output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

**Verify it's up:**
```
GET http://127.0.0.1:8000/health
→ {"status": "ok"}
```

---

## Step 6 — Test in Postman

### Common headers (required for every API call)

| Header | Value |
|---|---|
| `Authorization` | `Token <your-jwt>` |
| `logged-in-user-type` | `Patient` |
| `Content-Type` | `application/json` |

> The JWT is signed using `JWT_SECRET` from `.env` with algorithm `HS512`.
> Get a token from your auth system or generate a test one using the `JWT_SECRET`.

---

### API 1 — Start P2T Job

**POST** `http://127.0.0.1:8000/api/patient-to-trials/start`

**Body:**
```json
{
  "patient_id": "203375",
  "selected_disease": ["Systemic Lupus Erythematosus"],
  "selected_region": ["United States"],
  "retrieval_mode": "rag",
  "model": "gpt-4o",
  "debug": true
}
```

**Fields:**

| Field | Required | Notes |
|---|---|---|
| `patient_id` | Yes | External ID from MySQL `Patient` table (e.g. `203375`) |
| `selected_disease` | Yes | Any value — not used for filtering in RAG mode |
| `selected_region` | Yes | Any value — not used for filtering in RAG mode |
| `retrieval_mode` | Yes | `"rag"` (vector search) or `"legacy"` (DB keyword filter) |
| `model` | No | Default `gpt-3.5-turbo-0125`. Use `"gpt-4o"` for best results |
| `llm_service` | No | Default `"openai"`. Options: `"openai"`, `"gemini"`, `"claude"` |
| `debug` | No | `true` = verbose logs. Change between runs to force fresh job |

**Response:**
```json
{
  "job_id": "abc123...",
  "flow_type": "P2T",
  "status": "STARTED"
}
```

> **Idempotency:** Calling `/start` twice with identical body returns the existing `job_id`
> without re-running. Toggle `debug` or `model` to force a new run.

---

### API 2 — Poll Job Status

**GET** `http://127.0.0.1:8000/api/jobs/{job_id}/status`

Poll this every 10–15 seconds until `status` is `COMPLETED`.

**Response when done:**
```json
{
  "status": "COMPLETED",
  "compose_status": "COMPLETED",
  "retrieve_status": "COMPLETED",
  "evaluate_status": "COMPLETED",
  "rank_status": "COMPLETED",
  "completed_at": "2026-05-17T..."
}
```

**Stage durations (approximate with gpt-4o, 58 trial candidates):**

| Stage | What happens | Time |
|---|---|---|
| compose | LLM generates keywords from patient summary | ~5s |
| retrieve | Qdrant RRF vector search returns top-58 trial NCTs | ~5s |
| evaluate | LLM checks each inclusion/exclusion criterion per trial | ~60–120s |
| rank | Scores combined, results written to DB | ~5s |

---

### API 3 — Get Ranked Results

**GET** `http://127.0.0.1:8000/api/jobs/{job_id}/results`

**Response (key fields per evaluation):**

```json
{
  "job_id": "...",
  "patient_id": "<uuid>",
  "evaluations": [
    {
      "rank": 1,
      "trial_id": "NCT00997100",
      "trial_title": "Exploratory Study of Changes in Disease Activity...",
      "eligible": false,
      "eligibility_score": 96.15,
      "inclusion_met": "0/1",
      "exclusion_violated": "0/25",
      "phase": ["Phase 2"],
      "enrollment": {"count": 13.0}
    }
  ]
}
```

**How to read the results:**

| Field | Meaning |
|---|---|
| `rank` | 1 = best match |
| `eligible` | `true` only if ALL inclusion met AND zero exclusion violated |
| `eligibility_score` | % of criteria passed (inclusion met + exclusion not violated) / total |
| `inclusion_met` | e.g. `"3/7"` = 3 of 7 inclusion criteria met |
| `exclusion_violated` | e.g. `"1/6"` = 1 of 6 exclusion criteria violated (bad) |

---

### API 4 — Per-Criterion Inference (Deep View)

**GET** `http://127.0.0.1:8000/api/jobs/{job_id}/nct-inference?nct_id=NCT00997100`

Replace `NCT00997100` with any `trial_id` from `/results`.

Returns per-criterion LLM reasoning showing **why** the patient matched or didn't match each inclusion/exclusion criterion of that specific trial.

**Response includes:**
- `inclusion_criteria[]` — per-criterion: `eligible`, `reasoning`, `evidence`
- `exclusion_criteria[]` — per-criterion: `eligible`, `reasoning`, `evidence`
- `why_user_matched` / `why_user_not_matched` — human-readable breakdown
- `eligibility_score`, `relevance_score`, `inclusion_met`, `exclusion_violated`

---

## Step 7 — Recommended Test Patients

| `patient_id` | Primary diseases | Good for testing |
|---|---|---|
| `203375` | Systemic Lupus Erythematosus, Chronic Liver Disease | SLE trial matching |
| `203390` | Atrial Fibrillation, Congestive Heart Failure | Cardiac trials |
| `203447` | Brain Neoplasm, Normal Pressure Hydrocephalus | Neuro/Oncology |
| `203452` | Malignant Melanoma, Epilepsy | Oncology |
| `203446` | Hypertension, Type II Diabetes | Metabolic |
| `203395` | Asthma, Hypothyroidism | Respiratory/Endocrine |

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `404 Subject ID not found` | `patient_id` not in MySQL | Run Step 3 (MySQL sync) |
| `No summary found in compose_summary_block` | UUID not in Postgres | Run Step 1 (Postgres load) |
| `RAG retrieval returned 0 candidates` | Qdrant not running or collection empty | Start Qdrant; run Step 4 |
| `evaluations: []` in results | No trials hydrated from DB | Check `trialgpt_corpus` has the NCTs |
| `WinError 10013` on uvicorn start | Port 8000 already in use | Run `netstat -ano | findstr :8000` then `taskkill /PID <pid> /F` |
| Same old result returned instantly | Idempotency hit — same request params | Toggle `debug` or change `model` in request body |
| `eligible: true` with `inclusion_met: 0/0` | LLM found no inclusion criteria to parse | Check `/nct-inference` — trial may have unusual criteria format |

---

## Quick Re-run Checklist (if switching datasets)

If you replace `dataset/annot_20_patient.json` with a new file:

```
1. TRUNCATE TABLE compose_summary_block;          (Postgres)
2. python scripts/load_compose_summary_block.py --json-path <new_file>
3. python scripts/sync_block_patients_to_mysql.py --source json --json-path <new_file>
4. python scripts/export_compose_profiles_for_qdrant.py
5. python TrialGPT_RAG/ingest_patients_block.py --json-path ... --recreate
6. [Re-export trials JSONL from new file and ingest into Qdrant --recreate]
7. Restart uvicorn
```

---

## File Reference

| File | Purpose |
|---|---|
| `dataset/annot_20_patient.json` | Canonical dataset: 20 patients × 58 trials |
| `dataset/block_summary/paths.py` | Canonical path constant `ANNOT_20_PATIENT_P2T_JSON` |
| `scripts/load_compose_summary_block.py` | Load patients → Postgres |
| `scripts/sync_block_patients_to_mysql.py` | Map UUIDs → external patientId in MySQL |
| `scripts/export_compose_profiles_for_qdrant.py` | Export patient block JSON for Qdrant ingest |
| `TrialGPT_RAG/ingest_patients_block.py` | Ingest patient vectors into Qdrant |
| `TrialGPT_RAG/ingestion.py` | Ingest trial vectors into Qdrant |
| `workflows/patient_to_trials.py` | Main P2T workflow orchestrator |
| `services/rag_retrieval_service.py` | RAG vector retrieval from Qdrant (top_k=58) |
| `main.py` | FastAPI app + all route handlers |
| `core/inference_builders.py` | Builds `/nct-inference` response from stored labels |
| `core/response_builders.py` | Builds `/results` response from DB |
