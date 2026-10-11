# Hekma Patient Health

**S3 — Patient Health.** One service for the patient-facing clinical record.

The Python monolith (`hekma_data_pipeline`) is unchanged. Domain code was copied here.

**Design:** [docs/PATIENT_HEALTH.md](docs/PATIENT_HEALTH.md) — components, APIs, and diagrams.

| Included | Source modules |
|----------|----------------|
| Patient profile | `apis/patient_api.py`, `ehr_apis/` |
| EHR integration | `apis/fasten_api.py`, `fasten_health/` |
| Clinical FHIR store | `apis/clinical_fhir_api.py`, `services/clinical_fhir/` |
| Medication (full) | `apis/medications_api.py`, `services/medications/` |
| Account & compliance | `apis/account_deletion_api.py`, `services/account_deletion/` |

Not in this service: clinical scanner, EHR summary (Clinical AI), chat, CTMS.

## Run

```bash
cd hekma-patient-health
cp .env.example .env
# set JWT_SECRET to the same value hekma_api uses
python -m pytest
uvicorn hekma_patient_health.main:app --app-dir src --port 8010 --reload
```

Or via platform compose: `./scripts/local-dev.sh up` then `http://localhost:8010/health`.

## Security

- Every request except `/health`, `/ready`, Fasten webhooks, and public deletion-policy is authenticated.
- Patient-scoped routes require `JWT.userId == path patient_id`. Mismatch is **404**, not 403.
- Staff roles (`SITE`, `SPONSOR`, `ADMIN`, …) may access a patient they are treating.
- Internal FHIR projection (`/api/internal/clinical-fhir/project`) needs `CACHE_REPROCESS_API_KEY`. There is no hardcoded default key.
- PHI purge needs `ACCOUNT_DELETION_PURGE_API_KEY`.

## Scale

- Stateless FastAPI workers — add replicas behind the gateway.
- Postgres for clinical/medication data; MySQL only for leftover CTMS patient lookup during the strangler period.
- Long-running EHR ingest stays Fasten-webhook driven; do not put it on the request thread beyond ack.
