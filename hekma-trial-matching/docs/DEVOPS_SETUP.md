# DevOps Setup Guide — TrialGPT API (RAG mode)

Short guide to deploy and run the app on the `develop` branch.

---

## What you need

| Service | Purpose |
|---------|---------|
| **PostgreSQL** | Trials, patient profiles, job results |
| **MySQL** | Maps external `patient_id` → internal `subjectId` (P2T) |
| **Qdrant** | Vector search for RAG retrieval |
| **OpenAI API** | Embeddings (`text-embedding-3-large`) |
| **Anthropic API** | Claude matching & ranking (default LLM) |

Default retrieval mode is **`rag`** — Qdrant is required for full operation.

**Qdrant role:** search index only. PostgreSQL remains the source of truth for trial and patient data.

---

## 1. Install the app

```bash
cd trailgpt
python -m venv .venv
```

**Linux / Mac:**

```bash
source .venv/bin/activate
pip install -r requirements.txt
pip install qdrant-client fastembed
```

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install qdrant-client fastembed
```

---

## 2. Configure `.env`

Copy the template and fill in real values locally. **Never commit `.env`.**

```bash
cp .env.example .env
```

Edit `.env` with your environment credentials. See `.env.example` for all supported variables (Postgres, MySQL, LLM keys, JWT, Qdrant).

---

## 3. Install and start Qdrant

### Docker (recommended)

```bash
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -v qdrant_storage:/qdrant/storage \
  qdrant/qdrant
```

**Windows (PowerShell):**

```powershell
docker run -d --name qdrant -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
```

Verify: open `http://<QDRANT_HOST>:6333/dashboard` (default `http://localhost:6333/dashboard`).

### Qdrant collections (created by ingest scripts)

| Collection | Used by |
|------------|---------|
| `patient_profiles_hybrid_v1` | T2P RAG, P2T patient lookup |
| `clinical_trials_hybrid_v1` | P2T RAG trial search |

> **Important:** Ingest scripts in `TrialGPT_RAG/` use `TrialGPT_RAG/config.py`, which defaults to `localhost:6333`. Run ingest on the same host as Qdrant, or update that file to match `QDRANT_HOST` before ingesting. The **API** reads `QDRANT_HOST` / `QDRANT_PORT` from `.env`.

---

## 4. Load data (run once, in order)

Run all commands from the **project root** with the venv active.

### Step 1 — PostgreSQL: patient profiles

```bash
python scripts/load_compose_summary_block.py
```

Default input: `dataset/single_patient_load.json`

Custom file:

```bash
python scripts/load_compose_summary_block.py --json-path dataset/single_patient_load.json
```

### Step 2 — PostgreSQL: trial corpus

```bash
python scripts/load_trials_jsonl_to_corpus.py
```

Default input: `dataset/trials.jsonl`

### Step 3 — MySQL: patient ID mapping

Dry run (optional):

```bash
python scripts/sync_block_patients_to_mysql.py --dry-run
```

Apply:

```bash
python scripts/sync_block_patients_to_mysql.py --source json
```

### Step 4 — Export patient profiles for Qdrant

```bash
python scripts/export_compose_profiles_for_qdrant.py
```

Output: `TrialGPT_RAG/patient_block_summaries.from_compose.json`

### Step 5 — Qdrant: ingest patients

```bash
cd TrialGPT_RAG
python ingest_patients_block.py ^
  --json-path patient_block_summaries.from_compose.json ^
  --batch-size 50 ^
  --recreate
```

Linux / Mac — use `\` instead of `^` for line continuation, or run as one line:

```bash
python ingest_patients_block.py --json-path patient_block_summaries.from_compose.json --batch-size 50 --recreate
```

### Step 6 — Qdrant: ingest trials

From `TrialGPT_RAG/`:

```bash
python main.py --corpus ../dataset/trials.jsonl --recreate
```

This embeds trials into `clinical_trials_hybrid_v1`. Expect OpenAI API calls during ingest.

**Re-run steps 4–6** whenever patient or trial data changes.

---

## 5. Start the API

From project root:

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Dev with reload:

```bash
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

**Health check:**

```http
GET http://localhost:8000/health
```

**Swagger UI:** `http://localhost:8000/docs`

---

## 6. Smoke test (optional)

With the API running:

```bash
python scripts/verify_all_apis.py
```

Requires `JWT_SECRET` in `.env`. Tests route availability only — does not wait for long-running jobs.

### Manual P2T test

```http
POST /api/patient-to-trials/start
Authorization: Token <jwt>
Content-Type: application/json
```

```json
{
  "patient_id": "203375",
  "selected_disease": ["Systemic lupus erythematosus"],
  "selected_region": ["United States"],
  "debug": true,
  "force_rerun": true
}
```

Poll job:

```http
GET /api/jobs/{job_id}/status
GET /api/jobs/{job_id}/results
```

`retrieval_mode` defaults to `"rag"` — no need to pass it.

### Manual T2P test

```http
POST /api/trial-to-patients/start
Authorization: Token <jwt>
Content-Type: application/json
```

```json
{
  "nct_id": "NCT00997100",
  "site_id": "prod-site-1",
  "prospective_patient_count": 10,
  "debug": true
}
```

---

## Script reference

| Script | When to run |
|--------|-------------|
| `scripts/load_compose_summary_block.py` | Once — load patients into Postgres |
| `scripts/load_trials_jsonl_to_corpus.py` | Once — load trials into Postgres |
| `scripts/sync_block_patients_to_mysql.py` | Once — MySQL `patientId` → `subjectId` mapping |
| `scripts/export_compose_profiles_for_qdrant.py` | Before Qdrant patient ingest; after Postgres patient load |
| `TrialGPT_RAG/ingest_patients_block.py` | Once — build `patient_profiles_hybrid_v1` in Qdrant |
| `TrialGPT_RAG/main.py --corpus ... --recreate` | Once — build `clinical_trials_hybrid_v1` in Qdrant |
| `scripts/verify_all_apis.py` | After API start (optional smoke test) |

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|--------------|-----|
| Qdrant connection error on retrieve | Qdrant not running or wrong host | Start Docker container; set `QDRANT_HOST` / `QDRANT_PORT` |
| P2T returns 0 trials | Empty trial collection | Run step 6 (trial ingest) |
| T2P returns 0 patients | Empty patient collection | Run steps 4–5 (patient export + ingest) |
| `Subject ID not found` | Missing MySQL row | Run step 3 |
| `No summary found in compose_summary_block` | Missing Postgres patient | Run step 1 |
| OpenAI / embedding errors | Bad or missing key | Check `OPENAI_API_KEY` |
| Matching / aggregation errors | Bad or missing key | Check `ANTHROPIC_API_KEY` |
| Ingest works but API cannot reach Qdrant | Ingest used `localhost`, API uses remote host | Re-run ingest against the same Qdrant instance the API uses |

---

## Legacy mode (skip Qdrant)

Pass `"retrieval_mode": "legacy"` in API requests to use Postgres keyword/BM25 retrieval instead of vector search. This is **not** the default on `develop`.

---

## Dev-only: fixed trial cohort

`"corpus": "annot_10"` pins 10 trials for evaluation. **Do not use in production.** Omit `corpus` for full RAG trial search.

---

## Deployment checklist

- [ ] Python venv created; `requirements.txt` + `qdrant-client` + `fastembed` installed
- [ ] `.env` configured (Postgres, MySQL, OpenAI, Anthropic, JWT, Qdrant)
- [ ] Qdrant running on port 6333
- [ ] Step 1 — Postgres patient profiles loaded
- [ ] Step 2 — Postgres trial corpus loaded
- [ ] Step 3 — MySQL patient mapping synced
- [ ] Step 4 — Patient profiles exported for Qdrant
- [ ] Step 5 — Qdrant patient collection ingested
- [ ] Step 6 — Qdrant trial collection ingested
- [ ] API started (`uvicorn main:app`)
- [ ] `/health` OK; one P2T and one T2P job complete successfully
