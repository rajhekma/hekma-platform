# Hekma Pipeline — Trial → Patients (T2P): Technical backend reference

This document is the **detailed** T2P companion to the short overview in [HEKMA_PIPELINE_API_GUIDE.md](./HEKMA_PIPELINE_API_GUIDE.md). It covers **Trial → Patients only**: HTTP routes, SQL, tables, the background workflow, and how that maps to **Direction B** on the pipeline diagram.

**P2T technical counterpart:** [HEKMA_PIPELINE_P2T_TECHNICAL.md](./HEKMA_PIPELINE_P2T_TECHNICAL.md)

**Visuals:** [HekmaPipeline.pdf](./HekmaPipeline.pdf) · [Pipeline diagram (JPEG)](./WhatsApp%20Image%202026-05-04%20at%207.30.26%20PM.jpeg)

---

## Table of contents

| Section | Anchor |
|--------|--------|
| Systems | [Systems involved](#section-systems) |
| Application startup | [When the app starts](#section-startup) |
| UI call order | [Typical T2P API sequence](#section-ui-order) |
| Start endpoint | [`POST /api/trial-to-patients/start`](#section-post-start) |
| Background workflow | [`run_trial_to_patients_workflow`](#section-workflow) |
| Status / results / inference | [Read APIs](#section-read-apis) |
| Diagram mapping | [Diagram vs code](#section-diagram) |
| File index | [Source files](#section-files) |

---

<a id="section-systems"></a>

## Systems involved

| System | Role in T2P |
|--------|-------------|
| **FastAPI** (`main.py`) | HTTP entrypoint, JWT, schedules **`run_trial_to_patients_workflow_db`** in a background task. |
| **PostgreSQL** (`utils/pg_util.py`) | **`trialgpt_corpus`** (trial row by `nct_id`), **`compose_summary_block`** (all patient summaries for legacy BM25 or for **hydrating** RAG hits), **`matching_jobs`**, **`retrieval_results`**, **`matching_results`**, **`aggregation_results`**, **`final_ranking`**. |
| **MySQL** | **Not used on `start`.** Used on **`GET .../patient-inference`** when `patient_id` is an external id (see [Read APIs](#section-read-apis)). |
| **Qdrant** | When `retrieval_mode: "rag"`: **`retrieve_patient_ids_for_trial`** queries **`patient_profiles_hybrid_v1`** (hybrid dense + sparse, **RRF**). Trial vectors live in **`clinical_trials_hybrid_v1`** for other flows; T2P retrieval embeds the **trial text** and searches the **patient** collection. |
| **LLMs** | Matching + aggregation: `model` / `llm_service` from job parameters. RAG **embeddings**: OpenAI `text-embedding-3-large` in `services/rag_retrieval_service.py`. |

---

<a id="section-startup"></a>

## When the application starts

Same as P2T: import `main.py` loads env, logging, routers, NLTK `punkt`; **no** automatic Qdrant rebuild. See [HEKMA_PIPELINE_P2T_TECHNICAL.md § When the app starts](./HEKMA_PIPELINE_P2T_TECHNICAL.md#section-startup).

Smoke check: `GET /health` → `{"status":"ok"}`.

---

<a id="section-ui-order"></a>

## Typical T2P API sequence

1. `GET /health` (optional)
2. `POST /api/trial-to-patients/start`
3. Poll `GET /api/jobs/{job_id}/status` until `status` is `COMPLETED` or `FAILED`
4. `GET /api/jobs/{job_id}/results` (same route as P2T; response shape follows stored `flow_type = 'T2P'`)
5. `GET /api/jobs/{job_id}/patient-inference?patient_id=...` (optional)

**Unlike P2T**, `start` does **not** call `find_completed_job_by_parameters` — each start creates a **new** `matching_jobs` row.

---

<a id="section-post-start"></a>

## `POST /api/trial-to-patients/start`

**Handler:** `main.py` → `start_trial_to_patients`

### Auth and headers

- **`Depends(jwt_filter)`** — JWT; `user["userId"]` → `matching_jobs.requested_user_id`.
- **`logged-in-user-type`** (required): `Patient`, `Sponsor`, `Site`, or **`Administrator`** → mapped to `PATIENT` / `SPONSOR` / `SITE` / **`ADMIN`**.

### Request body (`TrialToPatientsRequest`)

| Field | Role |
|--------|------|
| `nct_id` | Clinical trial id; becomes **`matching_jobs.query_id`** and drives the whole workflow. |
| `site_id` | Stored in `parameters` (auditing / product); not used for retrieval SQL in the current workflow. |
| `prospective_patient_count` | Cap on how many patients to keep after ranking (RAG: `top_k` to `retrieve_patient_ids_for_trial`; legacy: top BM25 slice). |
| `corpus` | Optional; default `sigir` (passed to aggregation). |
| `model` | Optional; default `gpt-3.5-turbo-0125`. |
| `llm_service` | Default `openai`. |
| `retrieval_mode` | `"legacy"` or `"rag"`. |
| `debug` | Extra logs (hydration counts, field lengths, etc.). |

**Note:** The workflow also reads `parameters.get("rag_threshold", 0.1)` from the stored job JSON. The Pydantic model **does not** expose `rag_threshold` today, so the default **0.1** is used unless you extend the request model.

### Step A — Create job (PostgreSQL)

**Function:** `create_job` — `repositories/matching_jobs_repo.py`

```sql
INSERT INTO matching_jobs (
  job_id,
  flow_type,
  requested_user_id,
  user_type,
  query_id,
  parameters,
  status,
  compose_status,
  retrieve_status,
  evaluate_status,
  rank_status
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
```

Typical values: `flow_type = 'T2P'`, `query_id = req.nct_id`, `parameters = json.dumps(req.dict())`, `status = 'STARTED'`, stage columns `PENDING` as in code.

### Step B — Background task

```text
background_tasks.add_task(run_trial_to_patients_workflow_db, job_id)
```

**`run_trial_to_patients_workflow_db`** (`workflows/trial_to_patients.py`) loads the job row, parses `parameters`, and calls **`run_trial_to_patients_workflow`** with `nct_id`, `corpus`, `model`, `llm_service`, `retrieval_mode`, `debug`.

**Immediate HTTP response:**

```json
{
  "job_id": "<new>",
  "flow_type": "T2P",
  "status": "STARTED",
  "message": "Patient retrieval initiated"
}
```

---

<a id="section-workflow"></a>

## Background workflow: `run_trial_to_patients_workflow`

**File:** `workflows/trial_to_patients.py`  
**Artifacts:** `jobs/<job_id>/input/`, `jobs/<job_id>/results/` — e.g. `matching_input.json`, `matching_results.json`, `aggregation_results.json`.

**Stages:** same columns as P2T — `compose`, `retrieve`, `evaluate`, `rank` on **`matching_jobs`**, via `JobManager` → `matching_jobs_repo.update_stage`.

### Stage: `compose` (load trial from DB)

1. **`job_manager.update_stage(job_id, "compose", "RUNNING")`**

2. **`fetch_trial_by_id(nct_id)`** — `repositories/trialgpt_corpus_repo.py`:

```sql
SELECT nct_id, title, text, diseases, drugs
FROM trialgpt_corpus
WHERE nct_id = %s
LIMIT 1
```

If no row → **`compose` FAILED**, exception raised (`Trial {nct_id} not found in DB`).

3. Build **`adapted_trial`** dict (title, summary text, inclusion/exclusion strings, diseases, drugs) for matching.

4. **`compose` → `COMPLETED`**.

There is **no** separate LLM “keyword generation” stage for T2P (unlike P2T).

### Stage: `retrieve` (pick patient ids)

**`retrieve` → `RUNNING`.**

Read from **`job_manager.get_job(job_id)`** → `parameters`: `prospective_patient_count`, `rag_threshold` (default **0.1**), `debug`.

#### Mode `rag`

1. Build **`rag_trial`** dict from `trial_obj` (title, text, criteria, diseases, drugs).

2. **`retrieve_patient_ids_for_trial`** — `services/rag_retrieval_service.py`: embed trial text, sparse vectors, **Qdrant** `query_points` on **`patient_profiles_hybrid_v1`** (RRF over prefetches).

3. **`fetch_compose_summaries_map()`** — `repositories/compose_repo.py` (via `fetch_all_compose_summaries`):

```sql
SELECT patient_id, summary_text
FROM compose_summary_block
WHERE summary_text IS NOT NULL
```

Build `patient_map` keyed by **normalized** UUID strings where possible (`_normalize_patient_id`). Keep only RAG-returned ids that still have a non-empty summary → **`top_patients`** list `{patient_id, text}`.

4. **`insert_retrieval_results`** — `repositories/retrieval_results_repo.py`:

```sql
INSERT INTO retrieval_results (
  job_id, flow_type, query_id, candidate_id, rank_position
) VALUES (%s, %s, %s, %s, %s)
```

For T2P the workflow passes **`qid2patients = { nct_id: [patient_id, ...] }`**. So **`query_id` = NCT id**, **`candidate_id` = patient subject id**, `flow_type = 'T2P'`.

#### Mode `legacy`

1. **`fetch_all_compose_summaries()`** — same SQL as above (all rows).

2. If empty → **`retrieve` COMPLETED** and function **returns early** (no matching file / downstream — be aware for QA).

3. **BM25Okapi** over tokenized `summary_text`, trial text tokenized, **`np.argsort`** top **`prospective_patient_count`**.

4. Same **`insert_retrieval_results`** shape: `{ nct_id: [patient_ids...] }`.

**`retrieve` → `COMPLETED`**.

### Build matching input

For each row in **`top_patients`**, append:

```json
{ "patient_id": "<uuid>", "patient": "<summary text>", "candidates": [<adapted_trial>] }
```

Write **`matching_input.json`** under `jobs/<job_id>/results/`.

### Stage: `evaluate`

- **`run_matching_process`** — `trialgpt_matching/run_matching.py`  
- Persist: **`insert_matching_result`** with `flow_type='T2P'`, **`query_id = nct_id`**, **`candidate_id = patient_id`**, inclusion/exclusion JSON.

### Stage: `rank`

1. **`run_aggregation_process`** — `trialgpt_ranking/run_aggregation.py`.  
2. **`insert_aggregation_result`** — `flow_type='T2P'`, `query_id=nct_id`, `candidate_id=patient_id`.  
3. Score each patient for this trial (`get_matching_score` + `get_agg_score`), sort descending.  
4. **`insert_final_ranking`** — `flow_type='T2P'`, **`query_id=nct_id`**, **`candidate_id=patient_id`**, `rank_position`, `final_score`.  
5. **`rank` → `COMPLETED`** (job status completed via same `update_stage` rules as P2T).

---

<a id="section-read-apis"></a>

## Read APIs (after the job runs)

### `GET /api/jobs/{job_id}/status`

Same handler as P2T: **`get_job_status_public`** — reads **`matching_jobs`** by `job_id`.

### `GET /api/jobs/{job_id}/results`

Same handler as P2T: **`get_results`** → `build_job_results_response(job_id, flow_type=job['flow_type'])`.  
For T2P jobs, `flow_type` is **`T2P`**; SQL still comes from **`fetch_job_results`** in `repositories/results_repo.py` (join on `job_id`; ranking rows use **`query_id` = trial**, **`candidate_id` = patient** for T2P).

Core join (same file as P2T):

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

For T2P: **`fr.query_id`** is the **NCT id**; **`fr.candidate_id`** is the **patient subject UUID**.

### `GET /api/jobs/{job_id}/patient-inference?patient_id=...`

**Handler:** `get_patient_inference` — `main.py` — **`Depends(jwt_filter)`**.

**Resolve `patient_id`:**

- If the string parses as a **UUID**, treat it as **subject id** (T2P results path).  
- Else **`get_subject_id_by_patient_id(patient_id)`** — MySQL:

```sql
SELECT subjectId
FROM Patient
WHERE patientId = %s
LIMIT 1
```

If still no subject → **HTTP 404** `"Subject ID not found"`.

**DB:** **`fetch_patient_inference_data(job_id, subject_id)`** — `repositories/inference_repo.py`:

1. Ranking + aggregation + matching for this job, filtered by **`fr.candidate_id = %s`** (patient):

```sql
SELECT fr.query_id,
       fr.final_score,
       ar.relevance_score_R AS relevance_score_r,
       ar.eligibility_score_E AS eligibility_score_e,
       ar.relevance_explanation,
       ar.eligibility_explanation,
       mr.inclusion_results,
       mr.exclusion_results
FROM final_ranking fr
LEFT JOIN aggregation_results ar
  ON fr.job_id = ar.job_id
 AND fr.flow_type = ar.flow_type
 AND fr.query_id = ar.query_id
 AND fr.candidate_id = ar.candidate_id
LEFT JOIN matching_results mr
  ON fr.job_id = mr.job_id
 AND fr.flow_type = mr.flow_type
 AND fr.query_id = mr.query_id
 AND fr.candidate_id = mr.candidate_id
WHERE fr.job_id = %s
  AND fr.candidate_id = %s
```

2. Trial row from **`trialgpt_corpus`** where `nct_id = result.query_id`.

3. Patient summary from **`compose_summary_block`**:

```sql
SELECT summary_text
FROM compose_summary_block
WHERE patient_id = %s
```

Response: **`build_patient_inference_response`** in `core/inference_builders.py`.

---

<a id="section-diagram"></a>

## Diagram vs this codebase (T2P / Direction B)

| Diagram item | In this product |
|--------------|-----------------|
| `trial_2_patient_blocks.py` | **Not a repo filename.** Implementation: **`workflows/trial_to_patients.py`** + **`services/rag_retrieval_service.py`** (RAG) or BM25 in-workflow (legacy). |
| Qdrant trial + patient collections | RAG T2P searches **`patient_profiles_hybrid_v1`** using an embedding of the **trial**; patient points must align with **`compose_summary_block.patient_id`**. |
| `t2p_retrieved.json` | Development analogue: ordered ids go to **`retrieval_results`** (`query_id` = NCT, `candidate_id` = patient). |
| `t2p_reasoning.json` | **`matching_results`** + **`aggregation_results`** + **`final_ranking`** for `flow_type = 'T2P'`. |

---

<a id="section-files"></a>

## Source file index (T2P)

| Area | Files |
|------|--------|
| HTTP | `main.py` (`start_trial_to_patients`, `get_patient_inference`) |
| Workflow | `workflows/trial_to_patients.py` (`run_trial_to_patients_workflow`, `run_trial_to_patients_workflow_db`) |
| RAG patient retrieval | `services/rag_retrieval_service.py` (`retrieve_patient_ids_for_trial`) |
| Trial row | `repositories/trialgpt_corpus_repo.py` (`fetch_trial_by_id`) |
| Patient summaries | `repositories/compose_repo.py` (`fetch_all_compose_summaries`, `fetch_compose_summaries_map`) |
| Jobs + stages | `repositories/matching_jobs_repo.py`, `core/job_manager.py` |
| Retrieval rows | `repositories/retrieval_results_repo.py` |
| Matching / aggregation | `trialgpt_matching/run_matching.py`, `trialgpt_ranking/run_aggregation.py` |
| Results + inference | `repositories/results_repo.py`, `repositories/inference_repo.py`, `core/response_builders.py`, `core/inference_builders.py` |
| External patient id → UUID | `repositories/mysql_repo.py` (inference path) |

**Ops / RAG:** [P2T_T2P_END_TO_END_RUNBOOK.md](./P2T_T2P_END_TO_END_RUNBOOK.md) · **RAG QA:** [RAG_P2T_QA_CHECKLIST.md](./RAG_P2T_QA_CHECKLIST.md) (T2P log markers)  
**Short overview:** [HEKMA_PIPELINE_API_GUIDE.md](./HEKMA_PIPELINE_API_GUIDE.md)
