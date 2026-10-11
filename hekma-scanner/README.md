# Hekma Scanner

**S4 — Clinical AI.** One service for document scan (MS-11) and EHR summary (MS-13).

The Python monolith (`hekma_data_pipeline`) is unchanged. Domain code was copied here.

**Design:** [docs/SCANNER.md](docs/SCANNER.md) — components, APIs, and diagrams.

| Included | Source modules |
|----------|----------------|
| Clinical Scanner | `apis/clinical_scans_api.py`, `services/clinical_scans/` |
| EHR Summary | `apis/ehr_summary_api.py`, `fasten_health/ehr_summary_*` |

Not in this service: patient profile, Fasten connect, medication APIs, chat, CTMS, HealthKit.

## Run

```bash
cd hekma-scanner
cp .env.example .env
# set JWT_SECRET to the same value hekma_api uses
python -m pytest
uvicorn hekma_scanner.main:app --app-dir src --port 8011 --reload
```

Or via platform compose: `./scripts/local-dev.sh up` then `http://localhost:8011/health`.

## Security

- Every request except `/health` and `/ready` is authenticated.
- Patient-scoped routes require `JWT.userId == path/body patient_id`. Mismatch is **404**, not 403.
- Staff roles (`SITE`, `SPONSOR`, `ADMIN`, …) may access a patient they are treating.
- Email-only EHR summary and cache-stats are staff-only.
- No cloud credentials are stored in this repo. `OPENAI_API_KEY` comes from the environment.

## Scale

- Stateless FastAPI workers — add replicas behind the gateway.
- LLM calls are the bottleneck. Isolate this service so a model outage does not take down Patient Health.
- Usage is emitted to `hekma-ai-usage` after a successful model call (never blocks the request).
