# Dev deploy readiness (P2T + T2P)

Deploy branch: **`trialgpt-api-v1`** (CI → dev K8s via `.github/workflows/dev.yml`).

DevOps does **not** run ingest scripts manually. The API handles Qdrant population on startup.

## Required env (dev pod secrets)

Copy from `.env.example`. Minimum:

| Variable | Purpose |
|----------|---------|
| `PG_*` | Postgres (compose summaries + trialgpt_corpus) |
| `OPENAI_API_KEY` | Embeddings for Qdrant ingest + RAG query |
| `ANTHROPIC_API_KEY` | Claude matching/reasoning (P2T + T2P) |
| `JWT_SECRET` | API auth |
| `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_API_KEY` | Vector retrieval |
| `QDRANT_AUTO_INGEST_ON_STARTUP=true` | Auto patient + trial ingest on boot |
| `QDRANT_TRIALS_FROM_POSTGRES=true` | Export trials from `trialgpt_corpus` (not 10-row file) |
| `QDRANT_INGEST_SKIP_QUERY_EXPANSION=true` | Faster/cheaper ingest (keyword fallback) |
| `PG_STATEMENT_TIMEOUT_MS=120000` | Large trial export (2500+ rows) |

Optional: `QDRANT_INGEST_ADMIN_SECRET` for `POST /api/admin/qdrant/ingest?force=true`.

## QA Trial Match seed (tell DevOps)

QA Trial Match locations/matching need the Dev `trialgpt_corpus` rows. This runs **in the QA gpt-api pod on startup**, before Qdrant ingest.

Set these **QA-only** secrets (do **not** set on prod `gpt-api.hekma.ai`):

| Variable | Value |
|----------|--------|
| `TRIALGPT_CORPUS_SEED_FROM_DEV` | `true` |
| `TRIALGPT_CORPUS_SEED_EXPECTED_ROWS` | `2508` |
| `DEV_PG_HOST` / `DEV_PG_DB` / `DEV_PG_USER` / `DEV_PG_PASSWORD` | Dev Postgres (`87.106.50.234` / `hekmaai`) |
| `PG_*` | QA Postgres (already set) |

Behavior (one-shot — not on every request, not on every restart after success):

- Process already ran seed → **skip** (`already_ran`)
- DB marker `trialgpt_corpus_seed_marker` exists → **skip** (`already_seeded`)
- Local `COUNT(*) == 2508` → **skip**, write marker
- Otherwise → truncate + copy once, write marker, then Qdrant ingest
- Missing Dev env → log and continue (unless `TRIALGPT_CORPUS_SEED_REQUIRED=true`)

Do **not** call the migrator from app routes. Startup is the only call site.

Manual fallback (laptop):

```bash
python3 scripts/migrate_trialgpt_corpus_dev_to_qa.py --apply --truncate
```

Look for logs: `trialgpt_corpus seed skipped | reason=expected_count` or `trialgpt_corpus seed done`.

## What happens on first deploy

1. API starts → creates every TrialGPT-owned table if missing (`compose`, `trialgpt_corpus`, `matching_jobs`, result tables, `trial_gpt_ehr`, `trialgpt_eligible_patients`, annotations, validations). Does **not** create Fasten/FHIR/MIMIC warehouse tables.
2. If `TRIALGPT_CORPUS_SEED_FROM_DEV=true` and row count is not 2508 → copy corpus from Dev PG.
3. Background thread runs `run_qdrant_ingest()`.
4. If patient collection empty → export compose profiles from Postgres → ingest patients.
5. If trial collection empty → export `trialgpt_corpus` → ingest trials (with upsert retries).
6. Subsequent restarts **skip** corpus seed at 2508 rows and skip Qdrant ingest when collections already have points.

## Verify after deploy

```bash
# Health
curl https://gpt-api.hekma.ai/health

# Full E2E (from a machine with .env + network to dev)
python scripts/dev_e2e_verify.py --base https://gpt-api.hekma.ai
```

**Smoke IDs (MySQL numeric patient id, not UUID):**

- P2T: `patient_id=203450` (trauma gold pair → `NCT01771861`)
- T2P: `nct_id=NCT01771861`

Postman: `docs/postman/TrialGPT_API.postman_collection.json` + Dev environment.

## Local run

```powershell
.\run_local_api.ps1
python scripts\dev_e2e_verify.py
```

## Known limits

- **OTEL Python inject vs FastAPI:** the operator mounts `/otel-auto-instrumentation-python` with an old `typing_extensions.py`. That used to crash the pod (`cannot import name 'sentinel'`) and nginx returned 503. `docker_entrypoint.py` strips that shadow; `anyio==4.6.2` and `typing_extensions>=4.12.2` are pinned. If a new agent image still crashes, bump the OTEL Python auto-instrumentation image in the Instrumentation CR.
- **First ingest** of 2500+ trials takes ~30–60 min (OpenAI embeddings + Qdrant upserts). API is usable while ingest runs if collections are partially populated.
- **New patients** added to Postgres after initial ingest are **not** auto-added to Qdrant until `force=true` ingest or collection recreate.
- MySQL patient mapping uses `utils/mysql_util.py` when `MYSQL_*` env vars are empty (dev RDS).

## Files added for zero-DevOps ingest

- `scripts/export_trialgpt_corpus_for_qdrant.py` — Postgres → JSONL for trial ingest
- `scripts/dev_e2e_verify.py` — health + Qdrant + P2T + T2P poll test
- `services/qdrant_auto_ingest_service.py` — startup orchestration
