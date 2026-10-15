# Hekma Pipeline — Patient → Trials (P2T): Technical backend reference

This document is the **detailed** companion to the short overview in [HEKMA_PIPELINE_API_GUIDE.md](./HEKMA_PIPELINE_API_GUIDE.md). It is **P2T only**: HTTP routes, SQL, tables, background workflow, and how they map to the pipeline diagram.

**T2P technical counterpart:** [HEKMA_PIPELINE_T2P_TECHNICAL.md](./HEKMA_PIPELINE_T2P_TECHNICAL.md)

**Visuals:** [HekmaPipeline.pdf](./HekmaPipeline.pdf) · [Pipeline diagram (JPEG)](./WhatsApp%20Image%202026-05-04%20at%207.30.26%20PM.jpeg)

---

## Table of contents

| Section | Anchor |
|--------|--------|
| Systems | [Systems involved](#section-systems) |
| Application startup | [When the app starts](#section-startup) |
| UI call order | [Typical P2T API sequence](#section-ui-order) |
| Start endpoint | [`POST /api/patient-to-trials/start`](#section-post-start) |
| Background workflow | [`run_patient_workflow`](#section-workflow) |
| Status / results / inference | [Read APIs](#section-read-apis) |
| Diagram mapping | [Diagram vs code](#section-diagram) |
| File index | [Source files](#section-files) |

---

<a id="section-systems"></a>

## Systems involved

| System | Role in P2T |
|--------|-------------|
| **FastAPI** (`main.py`) | HTTP entrypoint, JWT, schedules `run_patient_workflow` in a background task. |
| **MySQL** (`operations` DB, see `utils/mysql_util.py`) | Maps UI **`patient_id`** → **`subjectId`** (UUID). All Postgres `compose_summary_block` reads use that UUID. |
| **PostgreSQL** (`utils/pg_util.py`) | `compose_summary_block`, `trialgpt_corpus`, `matching_jobs`, `retrieval_results`, `matching_results`, `aggregation_results`, `final_ranking`. |
| **Qdrant** | Used when `retrieval_mode: "rag"`. Collections: `patient_profiles_hybrid_v1`, `clinical_trials_hybrid_v1` (config: `TrialGPT_RAG/config.py`; overrides via `QDRANT_*` env in `services/rag_retrieval_service.py`). |
| **LLMs** | Keyword generation, matching, aggregation: request `model` / `llm_service`. RAG **embeddings** only: OpenAI `text-embedding-3-large` in `rag_retrieval_service.py`. |

---

<a id="section-startup"></a>

## When the application starts

On import of `main.py`:

1. `load_dotenv()` — loads `.env`.
2. Logging configured (INFO).
3. Routers: batch summary, trial ingestion, patient annotation.
4. NLTK `punkt` tokenizer ensured (download if missing) — used later in inference text splitting.
5. **No** FastAPI `lifespan` job: Qdrant / vector indexes are **not** rebuilt on boot.

Smoke check: `GET /health` → `{"status":"ok"}` (no DB).

---

<a id="section-ui-order"></a>

## Typical P2T API sequence

1. `GET /health` (optional)
2. `POST /api/patient-to-trials/start`
3. Poll `GET /api/jobs/{job_id}/status` until `status` is `COMPLETED` or `FAILED`
4. `GET /api/jobs/{job_id}/results`
5. `GET /api/jobs/{job_id}/nct-inference?nct_id=...` (optional)

---

<a id="section-post-start"></a>

## `POST /api/patient-to-trials/start`

**Handler:** `main.py` → `start_patient_to_trials`

### Auth and headers

- **`Depends(jwt_filter)`** — JWT must resolve; `user["userId"]` stored on the job as `requested_user_id`.
- **`logged-in-user-type`** (required): `Patient`, `Sponsor`, or `Site` (mapped to `PATIENT` / `SPONSOR` / `SITE`).

### Request body (`PatientToTrialsRequest`)

| Field | Role |
|--------|------|
| `patient_id` | External id → MySQL `Patient.patientId`. |
| `selected_disease`, `selected_region` | Used in **legacy** retrieval filtering. |
| `corpus` | Optional; default `sigir` (aggregation context). |
| `model` | Optional; default `gpt-3.5-turbo-0125`. |
| `llm_service` | Default `openai`. |
| `retrieval_mode` | `"legacy"` or `"rag"`. |
| `debug` | Extra logs in workflow + RAG service. |

### Step A — Resolve patient (MySQL)

**Function:** `get_subject_id_by_patient_id` — `repositories/mysql_repo.py`

```sql
SELECT subjectId
FROM Patient
WHERE patientId = %s
LIMIT 1
```

If no row → **HTTP 404** `"Subject ID not found for given patient"`.

The returned **`subjectId`** is stored as `matching_jobs.query_id` and passed to the workflow as `patient_data["patient_id"]` (all **Postgres** compose reads use this UUID).

### Step B — Idempotent completed job (PostgreSQL)

**Function:** `find_completed_job_by_parameters` — `repositories/matching_jobs_repo.py`

```sql
SELECT job_id
FROM matching_jobs
WHERE query_id = %s
  AND flow_type = %s
  AND parameters = %s::jsonb
  AND status = 'COMPLETED'
ORDER BY created_at DESC
LIMIT 1
```

If a row is found, the API returns immediately:

```json
{ "job_id": "<existing>", "flow_type": "P2T", "status": "COMPLETED" }
```

No new background run.

### Step C — Create job row (PostgreSQL)

**Function:** `create_job` — `repositories/matching_jobs_repo.py`

Inserts into **`matching_jobs`**: `job_id`, `flow_type='P2T'`, `requested_user_id`, `user_type`, `query_id` (= subject UUID), `parameters` (full JSON body), `status='STARTED'`, stage columns `PENDING` / initial compose state as implemented.

### Step D — Background task

```text
background_tasks.add_task(run_patient_workflow, job_id, patient_data, corpus, model, llm_service)
```

**Immediate response:**

```json
{ "job_id": "<new>", "flow_type": "P2T", "status": "STARTED" }
```

---

<a id="section-workflow"></a>

## Background workflow: `run_patient_workflow`

**File:** `workflows/patient_to_trials.py`  
**Artifacts:** `jobs/<job_id>/input/`, `jobs/<job_id>/results/` (e.g. `retrieved_trials_formatted.json`, `matching_results.json`, `aggregation_results.json`).

**Job stages** (columns on `matching_jobs`): `compose_status`, `retrieve_status`, `evaluate_status`, `rank_status` — updated via `JobManager` → `matching_jobs_repo.update_stage`.

### Stage: `compose` (keyword generation)

1. **Read patient summary** — `fetch_compose_summary(patient_id)` in `repositories/compose_repo.py`, table **`compose_summary_block`**:

```sql
SELECT summary_text FROM compose_summary_block WHERE patient_id = %s
```

If empty → workflow raises `ValueError` (no summary).

2. **`job_manager.update_stage(job_id, "compose", "RUNNING")`**

3. **`generate_keywords_for_text`** (`trialgpt_retrieval/keyword_generation.py`) using `model` / `llm_service`.

4. **`compose` → `COMPLETED`** or **`FAILED`**.

### Stage: `retrieve`

**`retrieve` → `RUNNING`.**

#### Mode `rag`

1. **`fetch_compose_structured_profile(patient_id)`** — same table:

```sql
SELECT structured_json FROM compose_summary_block WHERE patient_id = %s
```

2. **`retrieve_trial_ids_for_patient`** — `services/rag_retrieval_service.py`: Qdrant hybrid query (dense + sparse prefetches, **RRF** fusion), default collections `patient_profiles_hybrid_v1` / `clinical_trials_hybrid_v1`.

3. **`insert_retrieval_results`** — `repositories/retrieval_results_repo.py`, table **`retrieval_results`**:

```sql
INSERT INTO retrieval_results (
  job_id, flow_type, query_id, candidate_id, rank_position
) VALUES (%s, %s, %s, %s, %s)
```

(`flow_type='P2T'`, `query_id` = subject UUID, `candidate_id` = NCT id, rank 1..n.)

#### Mode `legacy`

**`run_retrieval`** (`trialgpt_retrieval/hybrid_fusion_retrieval.py`) with `queries`, `id2queries`, `region`, `disease`. Same **`insert_retrieval_results`** afterward.

**`retrieve` → `COMPLETED`** or **`FAILED`**.

### Hydrate trials for matching

- **`rag`:** `fetch_trials_by_ids` — `repositories/trialgpt_corpus_repo.py`:

```sql
SELECT * FROM trialgpt_corpus WHERE nct_id = ANY(%s)
```

- **`legacy`:** `fetch_trials_by_location_and_diseases` / `fetch_trials_by_location` / `fetch_all_trials` depending on request.

Rows are adapted to matcher JSON; written to **`retrieved_trials_formatted.json`**.

### Stage: `evaluate`

- **`run_matching_process`** — `trialgpt_matching/run_matching.py` → **`matching_results.json`**, then loop **`insert_matching_result`** (`flow_type='P2T'`, `query_id` = patient, `candidate_id` = trial).

### Stage: `rank`

1. **`run_aggregation_process`** — `trialgpt_ranking/run_aggregation.py` → **`aggregation_results.json`** (or empty if no pairs).
2. **`insert_aggregation_result`** for each pair.
3. Final scores: `get_matching_score` + `get_agg_score` per trial; **`insert_final_ranking`** (`flow_type='P2T'`).
4. **`rank` → `COMPLETED`** (job `status` → `COMPLETED` when rank completes, via `update_stage` logic in `matching_jobs_repo.py`).

---

<a id="section-read-apis"></a>

## Read APIs (after the job runs)

### `GET /api/jobs/{job_id}/status`

**Handler:** `get_job_status_public` — `main.py`  
**DB:** `get_job_status` selects from **`matching_jobs`** by `job_id`.

### `GET /api/jobs/{job_id}/results`

**Handler:** `get_results` — `main.py`  
**DB:** `build_job_results_response` → `fetch_job_results` in `repositories/results_repo.py` — joins **`final_ranking`**, **`aggregation_results`**, **`matching_results`**, **`matching_jobs`** (core pattern):

```sql
SELECT fr.query_id,
       fr.candidate_id,
       fr.rank_position,
       ar.relevance_score_R,
       ar.eligibility_score_E,
       mr.inclusion_results,
       mr.exclusion_results,
       mj.parameters
FROM final_ranking fr
LEFT JOIN aggregation_results ar
  ON fr.job_id = ar.job_id
 AND fr.query_id = ar.query_id
 AND fr.candidate_id = ar.candidate_id
LEFT JOIN matching_results mr
  ON fr.job_id = mr.job_id
 AND fr.query_id = mr.query_id
 AND fr.candidate_id = mr.candidate_id
LEFT JOIN matching_jobs mj
  ON fr.job_id = mj.job_id
WHERE fr.job_id = %s
ORDER BY fr.rank_position ASC
```

This matches `repositories/results_repo.py` as of the current codebase.

### `GET /api/jobs/{job_id}/nct-inference`

**Handler:** `get_nct_inference` — `main.py` (currently no JWT on this handler — tighten for production if needed).

**DB:** `fetch_nct_inference_data` — `repositories/inference_repo.py`:

1. Join ranking + aggregation + matching for `job_id` and `nct_id`.
2. Trial row:

```sql
SELECT title, inclusion_criteria, exclusion_criteria
FROM trialgpt_corpus
WHERE nct_id = %s
```

3. Patient summary:

```sql
SELECT summary_text FROM compose_summary_block WHERE patient_id = %s
```

Response built in **`core/inference_builders.build_nct_inference_response`** (includes NLTK `sent_tokenize` on the summary).

---

<a id="section-diagram"></a>

## Diagram vs this codebase (P2T)

| Phase / diagram item | In production API |
|----------------------|-------------------|
| Phase 1: structure patient | Upstream data in **`compose_summary_block`**. API reads `summary_text` + `structured_json` (RAG). Diagram may show `mimic_patient_summary` + Claude — that is ETL, not this HTTP path. |
| Phase 2: vectors | Offline: `TrialGPT_RAG/ingest_patients_block.py`, `ingest_trials.py`, or compose export + ingest. **Not** triggered by `uvicorn` startup. |
| Phase 3: RRF retrieval | **Legacy:** `run_retrieval`. **RAG:** `retrieve_trial_ids_for_patient`. Persisted: **`retrieval_results`**. |
| Phase 4: LLM matching | **`run_matching_process`**, **`run_aggregation_process`**, ranking inserts. Diagram `matching_blocks.py` / `reasoning_results.json` ≈ this stack + **`matching_results`** / **`aggregation_results`** / **`final_ranking`**. |

---

<a id="section-files"></a>

## Source file index (P2T)

| Area | Files |
|------|--------|
| HTTP | `main.py` |
| Workflow | `workflows/patient_to_trials.py` |
| RAG retrieval | `services/rag_retrieval_service.py` |
| Compose | `repositories/compose_repo.py` |
| MySQL | `repositories/mysql_repo.py` |
| Trials | `repositories/trialgpt_corpus_repo.py` |
| Jobs | `repositories/matching_jobs_repo.py`, `core/job_manager.py` |
| Retrieval rows | `repositories/retrieval_results_repo.py` |
| Results | `repositories/results_repo.py`, `core/response_builders.py` |
| Inference | `repositories/inference_repo.py`, `core/inference_builders.py` |
| Keywords / legacy retrieval | `trialgpt_retrieval/keyword_generation.py`, `trialgpt_retrieval/hybrid_fusion_retrieval.py` |
| Matching / rank | `trialgpt_matching/run_matching.py`, `trialgpt_ranking/run_aggregation.py` |

**Ops / RAG setup:** [P2T_T2P_END_TO_END_RUNBOOK.md](./P2T_T2P_END_TO_END_RUNBOOK.md) · **RAG QA:** [RAG_P2T_QA_CHECKLIST.md](./RAG_P2T_QA_CHECKLIST.md)

**Simple P2T + T2P overview:** [HEKMA_PIPELINE_API_GUIDE.md](./HEKMA_PIPELINE_API_GUIDE.md)
