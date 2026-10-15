# Hekma matching pipeline — simple backend & API guide (P2T + T2P)

This guide explains **what happens in the server** when the UI calls the matching APIs. It is written for **any reader** (product, QA, new engineers). Technical names are included where they help you search the code.

**Technical deep dives:** [HEKMA_PIPELINE_P2T_TECHNICAL.md](./HEKMA_PIPELINE_P2T_TECHNICAL.md) (P2T) · [HEKMA_PIPELINE_T2P_TECHNICAL.md](./HEKMA_PIPELINE_T2P_TECHNICAL.md) (T2P)

**Patient → Trials (P2T):** “For this patient, which trials fit best?”  
**Trial → Patients (T2P):** “For this trial, which patients look like the best prospects?”

**Pictures in this folder:**

- [HekmaPipeline.pdf](./HekmaPipeline.pdf) — full pipeline slide deck  
- [Pipeline flow diagram (JPEG)](./WhatsApp%20Image%202026-05-04%20at%207.30.26%20PM.jpeg) — same diagram; filename has spaces, so this link uses URL encoding (works in GitHub and most browsers).

If a preview tool still will not open the JPEG, open it from the file explorer: `trailgpt/docs/` → `WhatsApp Image 2026-05-04 at 7.30.26 PM.jpeg`.

---

## Table of contents

Jump links use fixed anchors so they work in Cursor, VS Code, GitHub, and GitLab.

| # | Section |
|---|--------|
| 1 | [Big picture](#section-1-big-picture) |
| 2 | [What must be running / filled in advance](#section-2-prerequisites) |
| 3 | [When the app starts](#section-3-app-start) |
| 4 | [Patient → Trials (P2T)](#section-4-p2t) |
| 5 | [Trial → Patients (T2P)](#section-5-t2p) |
| 6 | [Endpoints both flows use](#section-6-shared-endpoints) |
| 7 | [How the diagram maps to this app](#section-7-diagram-map) |
| 8 | [Where to look in the code](#section-8-code-index) |

---

<a id="section-1-big-picture"></a>

## 1. Big picture

1. **Data lives in databases** — patient text in Postgres (`compose_summary_block`), trials in Postgres (`trialgpt_corpus`), optional **vector search** in **Qdrant** when you use `"rag"` mode.  
2. **The UI only talks to the API** — it does **not** run Python scripts. Heavy work runs **in the background** after `start`.  
3. **Same four ideas as the diagram** — (1) prepare patient text, (2) optional vectors in Qdrant, (3) retrieve candidates, (4) use an LLM to score criteria and rank.

---

<a id="section-2-prerequisites"></a>

## 2. What must be running / filled in advance

| Piece | Why it matters |
|--------|----------------|
| **PostgreSQL** | Stores patients (`compose_summary_block`), trials (`trialgpt_corpus`), jobs, scores. |
| **MySQL** (P2T only) | Maps the UI’s **patient id** to an internal **subject UUID** used in Postgres. |
| **Qdrant** (only if `retrieval_mode` is `"rag"`) | Stores patient and trial vectors for fast similarity search. |
| **`.env`** | DB hosts, passwords, API keys for LLMs and (for RAG) embeddings. |

If Qdrant is empty but you call `"rag"`, retrieval will return few or no good hits — see [P2T_T2P_END_TO_END_RUNBOOK.md](./P2T_T2P_END_TO_END_RUNBOOK.md).

---

<a id="section-3-app-start"></a>

## 3. When the app starts

Starting `uvicorn` loads `main.py`. That:

- loads environment variables  
- turns on logging  
- attaches extra API modules (batch trials, annotations, etc.)  
- makes sure a small NLP helper (**NLTK punkt**) is available  

**Nothing** on startup rebuilds Qdrant or re-imports all patients. That is a **separate ops step** (scripts in `TrialGPT_RAG/` or `scripts/`).

**First check many teams use:**

```http
GET http://127.0.0.1:8000/health
```

Example response: `{"status":"ok"}` — means the process is up, not that your databases are full.

---

<a id="section-4-p2t"></a>

## 4. Patient → Trials (P2T)

For **line-by-line backend detail** (every DB query, stage flags, file paths), use **[HEKMA_PIPELINE_P2T_TECHNICAL.md](./HEKMA_PIPELINE_P2T_TECHNICAL.md)**. The rest of this section stays short on purpose.

### 4.1 What the user story is

The sponsor or site picks **one patient** (plus filters in legacy mode). The system finds **trial candidates**, runs **detailed LLM matching**, then returns a **ranked list of trials**.

### 4.2 UI call order (simple)

1. `GET /health` *(optional)*  
2. `POST /api/patient-to-trials/start` → you get a `job_id`  
3. Poll `GET /api/jobs/{job_id}/status` until `status` is `COMPLETED` or `FAILED`  
4. `GET /api/jobs/{job_id}/results` → ranked trials for the UI  
5. `GET /api/jobs/{job_id}/nct-inference?nct_id=NCT...` *(optional)* → one trial explained in plain language  

### 4.3 Example — start a P2T job (RAG)

**URL:** `POST http://127.0.0.1:8000/api/patient-to-trials/start`  

**Headers (required today):**

- Normal **JWT** auth the app already uses  
- `logged-in-user-type` — e.g. `Sponsor`, `Site`, or `Patient`  

**Body example:**

```json
{
  "patient_id": "203375",
  "selected_disease": ["diabetes"],
  "selected_region": ["Hefei, Anhui, China"],
  "retrieval_mode": "rag",
  "debug": true
}
```

**Example success:**

```json
{
  "job_id": "a1b2c3d4-....",
  "flow_type": "P2T",
  "status": "STARTED"
}
```

Sometimes the API returns an **old completed job** immediately (same patient + same request body saved earlier) — then `status` is already `COMPLETED` and no new run starts.

### 4.4 What the server does step by step (`start` → background job)

| Step | Plain English | Technical detail |
|------|----------------|-------------------|
| 1 | “Who is this patient internally?” | **MySQL** `Patient` table: `patientId` → `subjectId` (UUID). If not found → **404**. |
| 2 | “Did we already finish this exact request?” | **Postgres** `matching_jobs`: look for same `query_id` + same saved JSON parameters + `COMPLETED`. If yes → return that `job_id`. |
| 3 | “Book the work.” | Insert a row in **`matching_jobs`** with `flow_type = 'P2T'`, stages `PENDING`, then return `STARTED`. |
| 4 | “Run the pipeline in the background.” | Function **`run_patient_workflow`** in `workflows/patient_to_trials.py`. |

### 4.5 Inside the background pipeline (stages you see in `status`)

**A) `compose` stage — keywords**

- Read patient story from **`compose_summary_block`** (`summary_text`) using the **subject UUID**.  
- Call **`generate_keywords_for_text`** (LLM) so legacy retrieval has search terms.  
- Stage flips to **COMPLETED** or **FAILED** in **`matching_jobs`**.

**B) `retrieve` stage — pick trial IDs**

- **Legacy mode** (`retrieval_mode: "legacy"`): hybrid search using those keywords + region/disease filters; trial list comes from Postgres views used in `run_retrieval`.  
- **RAG mode** (`retrieval_mode: "rag"`): read **`structured_json`** from `compose_summary_block`, call **`retrieve_trial_ids_for_patient`** → **Qdrant** hybrid search (dense + sparse, fused with **RRF**).  
- Save ordered trial IDs into **`retrieval_results`** (`flow_type = 'P2T'`, `query_id` = patient subject id, `candidate_id` = NCT id).

**C) Hydrate trials**

- Load full trial rows from **`trialgpt_corpus`** with `WHERE nct_id = ANY(...)` (RAG: only returned IDs; legacy: filter path as coded).  
- Write a temp JSON file under `jobs/<job_id>/results/` for the matcher.

**D) `evaluate` stage — LLM criterion matching**

- **`run_matching_process`** reads that JSON, calls the LLM per patient–trial pair, writes **`matching_results`**.

**E) `rank` stage — scores + final order**

- **`run_aggregation_process`** writes **`aggregation_results`**.  
- Final ordering → **`final_ranking`**.  
- Job row → **`COMPLETED`**.

### 4.6 Example — check status

`GET /api/jobs/a1b2c3d4-..../status`

You will see fields like `compose_status`, `retrieve_status`, `evaluate_status`, `rank_status` move from `PENDING` → `RUNNING` → `COMPLETED`.

### 4.7 Example — one trial deep dive (P2T)

`GET /api/jobs/{job_id}/nct-inference?nct_id=NCT01234567`

Builds a friendly explanation using:

- scores already stored for that job + trial  
- trial inclusion/exclusion text from **`trialgpt_corpus`**  
- patient story from **`compose_summary_block`**

---

<a id="section-5-t2p"></a>

## 5. Trial → Patients (T2P)

**Detailed T2P backend (SQL, stages, `retrieval_results` semantics):** [HEKMA_PIPELINE_T2P_TECHNICAL.md](./HEKMA_PIPELINE_T2P_TECHNICAL.md)

### 5.1 What the user story is

The sponsor picks **one clinical trial** (by **NCT id**). The system finds **patient candidates**, runs the **same style of LLM matching**, then returns a **ranked list of patients** for that trial.

### 5.2 UI call order (simple)

1. `GET /health` *(optional)*  
2. `POST /api/trial-to-patients/start` → `job_id`  
3. Poll `GET /api/jobs/{job_id}/status`  
4. `GET /api/jobs/{job_id}/results` → ranked patients *(same endpoint as P2T — the server uses the job’s `flow_type` to shape the response)*  
5. `GET /api/jobs/{job_id}/patient-inference?patient_id=...` *(optional)* → explain one patient vs that trial  

### 5.3 Example — start a T2P job (RAG)

**URL:** `POST http://127.0.0.1:8000/api/trial-to-patients/start`  

**Headers:** same JWT + `logged-in-user-type` as P2T (T2P also allows `Administrator` → `ADMIN` in code).

**Body example:**

```json
{
  "nct_id": "NCT00002288",
  "site_id": "SITE-1",
  "prospective_patient_count": 20,
  "retrieval_mode": "rag",
  "debug": true
}
```

| Field | Simple meaning |
|--------|----------------|
| `nct_id` | Which trial we are recruiting for. |
| `site_id` | Stored on the job for auditing / product use. |
| `prospective_patient_count` | **How many patients** to pull after retrieval (RAG: top‑k; legacy: top BM25 hits). |
| `retrieval_mode` | `"legacy"` = rank all compose patients with **BM25** on summaries. `"rag"` = **Qdrant** vector search over the patient collection. |
| `debug` | Extra log lines (counts, missing summaries, etc.). |

**Optional body fields:** `corpus`, `model`, `llm_service` — same meaning as P2T.

**Example response:**

```json
{
  "job_id": "e5f6....",
  "flow_type": "T2P",
  "status": "STARTED",
  "message": "Patient retrieval initiated"
}
```

Note: T2P **does not** repeat the P2T “return an old completed job” shortcut in code — each `start` creates a **new** job row.

### 5.4 What the server does step by step

| Step | Plain English | Technical detail |
|------|----------------|-------------------|
| 1 | “Book the work.” | Insert **`matching_jobs`** with `flow_type = 'T2P'`, `query_id = nct_id`, full JSON body in `parameters`. |
| 2 | “Run in background.” | **`run_trial_to_patients_workflow_db`** reads those parameters and calls **`run_trial_to_patients_workflow`** (`workflows/trial_to_patients.py`). |

### 5.5 Inside the workflow

**`compose` stage**

- Load the trial from **`trialgpt_corpus`** with `fetch_trial_by_id(nct_id)`.  
- If missing → stage **FAILED**, job stops.  
- Build one “fat” trial object (title, summary, criteria lists) for later steps.  
- Mark **`compose` COMPLETED** (no keyword file like P2T — trial is already structured in DB).

**`retrieve` stage**

- **RAG mode:** build a small dict from the trial → **`retrieve_patient_ids_for_trial`** (Qdrant hybrid + RRF on **`patient_profiles_hybrid_v1`**). Then load **all** patient summaries with **`fetch_compose_summaries_map()`** and keep only patients that returned from RAG **and** still have text in compose.  
- **Legacy mode:** load every row from **`fetch_all_compose_summaries()`**, tokenize summaries, run **BM25** against the trial text, take top **`prospective_patient_count`**.  
- Save patient ids under that trial into **`retrieval_results`** with `flow_type = 'T2P'` (here `query_id` is the **NCT id** and each `candidate_id` is a **patient subject id**).

**`evaluate` stage**

- Build matching input: **each patient** gets the **same trial** as the single `candidate`.  
- **`run_matching_process`** → **`matching_results`** (`query_id` = NCT, `candidate_id` = patient).

**`rank` stage**

- **`run_aggregation_process`** → **`aggregation_results`**.  
- Combine scores → **`final_ranking`** (`query_id` = NCT, `candidate_id` = patient).  
- Mark job **`COMPLETED`**.

### 5.6 Example — patient inference (T2P)

`GET /api/jobs/{job_id}/patient-inference?patient_id=...`

`patient_id` can be:

- the **subject UUID** returned in T2P results, **or**  
- the external **patient id** — the API tries UUID first, otherwise looks up MySQL like P2T.

Uses **`fetch_patient_inference_data`** — same pattern as NCT inference but swaps who is “query” vs “candidate” in the stored tables.

### 5.7 Tips that help QA

| Symptom | Likely cause |
|---------|----------------|
| Empty or tiny patient list in RAG | Qdrant patient index out of date vs Postgres, or **subject id** mismatch between Qdrant points and `compose_summary_block.patient_id`. Re-run export + ingest (see runbook). Logs: `RAG hydrated summaries kept=0`. |
| Trial not found early | `nct_id` missing from **`trialgpt_corpus`**. |

---

<a id="section-6-shared-endpoints"></a>

## 6. Endpoints both flows use

| Endpoint | What it is for |
|-----------|----------------|
| `GET /api/jobs/{job_id}/status` | Wait bar for the UI — same shape for P2T and T2P. |
| `GET /api/jobs/{job_id}/results` | Final ranked list — server picks layout using stored `flow_type`. |
| `GET /api/jobs` *(if enabled in your build)* | List jobs for a user / filter — see `main.py`. |

---

<a id="section-7-diagram-map"></a>

## 7. How the diagram maps to this app

| Diagram label (Direction A — P2T) | In this product |
|------------------------------------|-------------------|
| `mimic_patient_summary` + Claude + `block_summaries` | Real patients usually arrive through **`compose_summary_block`** (summary + structured JSON). Offline lab: `TrialGPT_RAG/block_summaries.py`. |
| `patient_block_summaries.json` + `ingest_patients_block.py` | Same idea: JSON profiles → **Qdrant** `patient_profiles_hybrid_v1`. Compose path: `scripts/export_compose_profiles_for_qdrant.py` then ingest script. |
| `corpus.jsonl` + `ingest_trials.py` | Trials in **`trialgpt_corpus`** + vectors in **`clinical_trials_hybrid_v1`**. |
| `retrieve_patients_block.py` + `retrieved.json` | **API RAG:** `services/rag_retrieval_service.py` + table **`retrieval_results`** (no need for `retrieved.json` in production). |
| `matching_blocks.py` + `reasoning_results.json` | **API:** `trialgpt_matching/run_matching.py` + Postgres **`matching_results`** / **`aggregation_results`** / **`final_ranking`**. |

| Diagram label (Direction B — T2P) | In this product |
|------------------------------------|-------------------|
| `trial_2_patient_blocks.py` | **Not a filename.** Use **`workflows/trial_to_patients.py`** + the same matching/ranking stack. |

---

<a id="section-8-code-index"></a>

## 8. Where to look in the code

| Topic | Main files |
|--------|------------|
| HTTP routes | `main.py` |
| P2T workflow | `workflows/patient_to_trials.py` |
| T2P workflow | `workflows/trial_to_patients.py` |
| RAG vector search | `services/rag_retrieval_service.py` |
| Patient text in Postgres | `repositories/compose_repo.py` |
| Trials in Postgres | `repositories/trialgpt_corpus_repo.py` |
| Jobs + stages | `repositories/matching_jobs_repo.py`, `core/job_manager.py` |
| Saving retrieval rows | `repositories/retrieval_results_repo.py` |
| Results + inference JSON | `core/response_builders.py`, `core/inference_builders.py`, `repositories/inference_repo.py`, `repositories/results_repo.py` |
| External id → subject UUID | `repositories/mysql_repo.py` |
| Offline / lab scripts (diagram names) | `TrialGPT_RAG/block_summaries.py`, `ingest_patients_block.py`, `ingest_trials.py`, `retrieve_patients_block.py`, `matching_blocks.py` |

**More step-by-step ops:** [P2T_T2P_END_TO_END_RUNBOOK.md](./P2T_T2P_END_TO_END_RUNBOOK.md)  
**RAG QA checklist:** [RAG_P2T_QA_CHECKLIST.md](./RAG_P2T_QA_CHECKLIST.md) (includes T2P log hints)
