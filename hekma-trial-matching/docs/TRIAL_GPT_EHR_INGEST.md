# trial_gpt_ehr — Fasten EHR summaries for P2T + RAG

## Purpose

P2T (`POST /api/patient-to-trials/start`) **always** uses `trial_gpt_ehr` (Fasten-derived).
There is **no** fallback to `trialgpt_eligible_patients`.

Patient Qdrant embeddings for RAG are built from `trial_gpt_ehr.structured_json`.

## Config

[`config/trial_gpt_ehr_config.json`](../config/trial_gpt_ehr_config.json)

| Field | Meaning |
|-------|---------|
| `summaryModes` | `["llm"]`, `["rule_based"]`, or both |
| `p2tPreferredLlm` | Which `llm` row P2T / RAG reads (`true` = LLM summary) |
| `skipLargeTables` | Skip `fastenhealth_binary` / `media` |
| `fastenPatientCreatedAtCutoff` / `mysqlPatientCreatedDateCutoff` | Retained for ops reference; **not** used to skip to eligible_patients |

Override path: `TRIAL_GPT_EHR_CONFIG_PATH`.

## Flow

### Primary (recommended): lambda triggers ingest after Fasten export

1. **lambda_api** (`hekma_data_pipleline`) completes `ingest_fasten_export()` → `fastenhealth_*` tables updated
2. Lambda calls **`POST /api/internal/trial-gpt-ehr/ingest`** on gpt-api (fire-and-forget)
3. gpt-api queues background Fasten → LLM → `trial_gpt_ehr` ingest
4. When user opens Trial Match, **`GET /diseases`** returns cached data immediately (`cached: true`)

**Lambda env (caller):**

| Variable | Example |
|----------|---------|
| `TRIALGPT_API_BASE_URL` | `https://gpt-api.hekma.ai` |
| `TRIALGPT_EHR_INGEST_API_KEY` | shared secret (same on gpt-api) |

**gpt-api env (receiver):**

| Variable | Purpose |
|----------|---------|
| `TRIALGPT_EHR_INGEST_API_KEY` | Validates `X-Hekma-Internal-Key` header |

**Request:**

```http
POST /api/internal/trial-gpt-ehr/ingest
X-Hekma-Internal-Key: <shared-secret>
Content-Type: application/json

{
  "patient_id": "203578",
  "trigger": "fasten_ehi_export_success",
  "force": true
}
```

**Responses:**

| Status | Meaning |
|--------|---------|
| `200` | `already_present` — trial_gpt_ehr already ready (when `force=false`) |
| `202` | `accepted` — background ingest started |
| `404` | No fastenhealth_* clinical rows for patient (EHR, manual, or scan) |

Hook location in lambda: `fasten_health/fasten_handler.py` → `process_export_success()` after all export files ingested.

### Read APIs (`/diseases`, `/summary`) — read-only

These endpoints **do not start ingest**. Ingest is triggered only by:

- `POST /api/internal/trial-gpt-ehr/ingest` (lambda after Fasten export)
- `GET .../diseases?wait=true` (Postman / ops — blocking sync ingest)

When data is not ready yet, read APIs return **200** with `ehr_status: "preparing"` so the UI can poll. They never queue a second ingest job.

1. Resolve MySQL `patientId` → `subjectId`
2. **Read APIs**: diseases come from `fastenhealth_condition` (all sources). If `trial_gpt_ehr` is missing, LLM ingest may still run in the background for P2T summaries, but the Condition step does not wait on it when Fasten conditions exist.
3. **P2T start**: if configured rows already `ready` → skip ingest; else sync ingest → start workflow. Returns **409** if ingest still running.
4. Workflow loads `summary_text` + RAG `structured_json` **only** from `trial_gpt_ehr`
5. Missing Fasten / empty EHR summary → API error (404/503), not legacy table

### UI polling (Trial Match Condition step)

When `/diseases` returns `ehr_status: "preparing"`, poll **`/ehr-ingest-progress`** (or `/ehr-status`) every 15s:

```json
{
  "patient_id": "203578",
  "ehr_status": "preparing",
  "stage": "building_profile",
  "progress_percent": 65,
  "message": "Building your health profile from EHR data. This usually takes 1–2 minutes.",
  "elapsed_seconds": 45,
  "estimated_seconds_remaining": 75,
  "fasten_ready": true,
  "fasten_clinical_rows": 416,
  "retry_scheduled": false,
  "retry_after_seconds": 15
}
```

**Endpoints:**

| Route | Use |
|-------|-----|
| `GET /api/patient/{id}/ehr-ingest-progress` | Detailed progress bar + ETA (recommended) |
| `GET /api/patient/{id}/ehr-status` | Same payload (alias) |
| `GET /api/patient/{id}/diseases` | Returns diseases when ready; includes `stage` + `progress_percent` while preparing |

Failed ingest is **auto-retried** on poll (no more 503 `trial_gpt_ehr ingest failed` during the 1–2 min window).

## Log tracing

All stages use the prefix `trial_gpt_ehr` so you can grep pod logs end-to-end:

```bash
# lambda (after Fasten export)
kubectl logs -f deploy/lambda-api | rg 'trial_gpt_ehr'

# gpt-api (ingest worker + LLM)
kubectl logs -f deploy/gpt-api | rg 'trial_gpt_ehr'
```

| Log line | Stage |
|----------|--------|
| `notify queued after fasten export` | Lambda — Fasten PG ingest done, calling gpt-api |
| `notify dispatch` | Lambda — HTTP POST thread started |
| `notify \| patient_id=... \| status=202` | Lambda — gpt-api accepted |
| `internal ingest request` | gpt-api — endpoint hit |
| `internal trigger accepted` | gpt-api — background thread queued |
| `background worker start` | gpt-api — worker thread running |
| `ingest start` | Export + LLM pipeline started |
| `ingest fasten_export \| tables=... \| rows=...` | Read from fastenhealth_* |
| `ingest status=ingesting` | Row marked in trial_gpt_ehr |
| `ingest llm_start` | LLM summary generation started (~1–2 min) |
| `ingest llm_done \| diseases=N \| llm_elapsed_sec=...` | Summary written |
| `ingest complete \| elapsed_sec=...` | Ready for /diseases |
| `background worker done \| result=ingested` | Full pipeline success |
| `background worker failed` | Check stack trace in gpt-api logs |

## Migration

Runs automatically on **gpt-api startup** and on first read/ingest. Manual apply (optional):

```bash
# from trailgpt with venv + .env set
python -c 'from pathlib import Path; from dotenv import load_dotenv; import os, psycopg2; load_dotenv(".env", override=True); sql=Path("migration/012_trial_gpt_ehr.sql").read_text(); conn=psycopg2.connect(host=os.environ["PG_HOST"], port=int(os.environ.get("PG_PORT",5432)), dbname=os.environ["PG_DB"], user=os.environ["PG_USER"], password=os.environ["PG_PASSWORD"]); conn.autocommit=True; cur=conn.cursor(); cur.execute(sql); cur.execute("SELECT to_regclass(%s)", ("public.trial_gpt_ehr",)); print(cur.fetchone()[0]); conn.close()'
```

Table is also auto-ensured on gpt-api startup and first `/diseases` call.

## QA / test environment checklist

| Step | Service | Check |
|------|---------|-------|
| 1 | Fasten webhook | Fasten dashboard webhook URL points to **QA lambda** (e.g. `https://dev-lambda.hekma.ai/fastenhealth/callback`) |
| 2 | Lambda PG | After EHR pull: `SELECT * FROM fastenhealth_patient WHERE patient_id = '<id>'` |
| 3 | Lambda env | `TRIALGPT_API_BASE_URL=https://gpt.test.hekma.ai` (not prod `gpt-api.hekma.ai`) |
| 4 | Lambda env | `TRIALGPT_EHR_INGEST_API_KEY` matches gpt-api QA secret |
| 5 | gpt-api QA | `TRIALGPT_EHR_INGEST_API_KEY` set; table `trial_gpt_ehr` exists after pod start |
| 6 | Lambda logs | `trial_gpt_ehr notify queued after fasten export` → `notify \| status=202` |
| 7 | gpt-api logs | `internal trigger accepted` → `background worker done` |
| 8 | UI | `GET /api/patient/<id>/diseases` → `ehr_status: preparing` then `ready` |

**Common QA failures:**

- **`/diseases` 500** — `trial_gpt_ehr` table missing (fixed: auto-create on startup)
- **Empty diseases, no error** — Fasten PG empty (step 1–2 failed; lambda webhook/export issue)
- **Stuck `preparing` forever** — lambda notify skipped (missing env) or gpt-api worker failed (check logs)
- **Notify hits wrong env** — lambda `TRIALGPT_API_BASE_URL` points to prod while UI uses `gpt.test.hekma.ai`

## Qdrant export

```bash
python scripts/export_compose_profiles_for_qdrant.py
# exports ready trial_gpt_ehr profiles (script name kept for ops compatibility)
```

## Tests

```bash
cd trailgpt
python3 scripts/test_trial_gpt_ehr.py
```
