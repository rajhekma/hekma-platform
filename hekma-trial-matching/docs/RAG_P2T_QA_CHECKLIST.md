# RAG P2T QA Checklist and Test Runbook

This runbook validates that `retrieval_mode: "rag"` is working end-to-end in the API flow and follows the new implementation path.

## Scope

- Flow: Patient to Trials (P2T)
- APIs:
  - `POST /api/patient-to-trials/start`
  - `GET /api/jobs/{job_id}/status`
  - `GET /api/jobs/{job_id}/results`
  - `GET /api/jobs/{job_id}/nct-inference?nct_id=<trial_id>`

## Prerequisites

- API server is running on `http://127.0.0.1:8000`
- Qdrant is running and reachable (`localhost:6333`)
- Required collections exist:
  - `patient_profiles_hybrid_v1`
  - `clinical_trials_hybrid_v1`
- Patient data exists in DB for requested patient
- Trial corpus table (`trialgpt_corpus`) is populated
- Auth token/header is available (if your environment enforces JWT)

## Test Payload (Example)

Use this payload for P2T RAG testing:

```json
{
  "patient_id": "203375",
  "selected_disease": ["diabetes"],
  "selected_region": ["Hefei, Anhui, China"],
  "retrieval_mode": "rag",
  "debug": true
}
```

## Step-by-Step QA

### 1) Start Job

- Endpoint: `POST /api/patient-to-trials/start`
- Expected response:
  - `job_id` is present
  - `flow_type` is `P2T`
  - `status` is `STARTED`

Pass criteria:
- Non-empty `job_id`
- HTTP 200 response

---

### 2) Check Job Status

- Endpoint: `GET /api/jobs/{job_id}/status`
- Wait until `status` becomes `COMPLETED`

Expected:
- `status: COMPLETED`
- `compose_status: COMPLETED`
- `retrieve_status: COMPLETED`
- `evaluate_status: COMPLETED`
- `rank_status: COMPLETED`
- `error: null`

Fail criteria:
- Any stage is `FAILED`
- `error` is non-null

---

### 3) Validate RAG Path from Logs (Mandatory)

For same `job_id`, verify these lines exist in server logs:

- `[P2T] Start workflow retrieval_mode=rag ...`
- `[RAG:P2T] Retrieving trials ...`
- `collections(patient=patient_profiles_hybrid_v1,trial=clinical_trials_hybrid_v1)`
- `[P2T] RAG retrieval returned <X> candidates`

With `debug: true`, also expect:
- `[P2T][DEBUG] Generated keyword keys=...`
- `[RAG:P2T][DEBUG] profile_fields=... base_text_chars=...`
- `[RAG:P2T][DEBUG] expanded_text_chars=...`
- `[P2T][DEBUG] Trial map built with ...`
- `[P2T][DEBUG] qid=... candidates_kept=... dropped_missing=...`

Pass criteria:
- RAG markers are present
- No evidence of legacy path being used as primary retrieval branch

---

### 4) Validate Results Payload

- Endpoint: `GET /api/jobs/{job_id}/results`

Expected:
- `parameters.retrieval_mode == "rag"`
- `parameters.debug == true` (if sent)
- `evaluations` exists
- Each evaluation has valid `trial_id` values

Notes:
- It is possible to have fewer evaluations than retrieved candidates due to hydration mismatch or filtering.

---

### 5) Validate NCT Inference

- Endpoint:
  - `GET /api/jobs/{job_id}/nct-inference?nct_id=<trial_id_from_results>`

Important:
- Use `trial_id` from `results.evaluations[].trial_id` for the same `job_id`.

Expected success:
- `failed: false`
- `error: null`
- Includes criteria-level breakdown (`inclusion_criteria`, `exclusion_criteria`, explanations)

Expected failure case:
- If using a trial not in this job's ranking/matching rows:
  - `failed: true`
  - `error: "Inference data not found"`

## Validation Matrix

Mark each line as PASS/FAIL/WARN:

1. Start API returned valid `job_id`  
2. Job reached `COMPLETED` with all stages completed  
3. Logs confirm RAG path and Qdrant collection usage  
4. Results payload confirms `retrieval_mode=rag`  
5. Inference success for trial from results  
6. Retrieval-to-hydration ratio acceptable (`X` retrieved vs `Y` hydrated)  
7. `fastembed` warning absent (or tracked as warning if present)  

## Common Issues and Meaning

### A) `Inference data not found`

Cause:
- `nct_id` not part of this job's final ranked/matched records.

Fix:
- Call inference using a `trial_id` from `GET /api/jobs/{job_id}/results`.

### B) `RAG retrieval returned X` but only `Hydrated Y` (Y << X)

Cause:
- Qdrant trial IDs and SQL `trialgpt_corpus` IDs are not aligned.

Fix:
- Reconcile and re-ingest trial corpus so NCT IDs match between vector index and DB.

### C) `fastembed unavailable; using hashed sparse fallback`

Cause:
- `onnxruntime/fastembed` failed in current environment (common on Windows).

Impact:
- Pipeline still works, but sparse retrieval is fallback mode.

Fix:
- Install/fix compatible `onnxruntime` runtime and dependencies.

### D) Job IDs mismatch between calls

Cause:
- Using a different `job_id` in status/results/inference than from start response.

Fix:
- Always copy exact `job_id` from start API response.

## Suggested QA Report Template

Use this after each run:

```text
Run timestamp:
Job ID:
Payload:

1) Start API: PASS/FAIL
2) Status completion: PASS/FAIL
3) RAG log markers: PASS/FAIL
4) Results consistency: PASS/FAIL
5) Inference consistency: PASS/FAIL
6) Retrieval->Hydration ratio: X->Y (PASS/WARN/FAIL)
7) fastembed status: OK/WARN

Final verdict: PASS / PASS with warnings / FAIL
Notes:
```

## Optional Additional QA (A/B)

Run same patient once with:
- `retrieval_mode: "legacy"`
- `retrieval_mode: "rag"`

Compare:
- Candidate list
- Ranking differences
- Inference breakdown consistency

This confirms branch routing and behavior differences between implementations.

---

## T2P RAG QA Checklist

Use this section to validate Trial to Patients flow with `retrieval_mode: "rag"`.

### T2P Test Payload (Example)

Endpoint: `POST /api/trial-to-patients/start`

```json
{
  "nct_id": "NCT06375031",
  "site_id": "SITE-1",
  "prospective_patient_count": 20,
  "retrieval_mode": "rag",
  "debug": true
}
```

### T2P Validation Steps

1. Start T2P job and capture `job_id`.
2. Poll `GET /api/jobs/{job_id}/status` until complete.
3. Confirm all stages are completed with no error.
4. Fetch `GET /api/jobs/{job_id}/results` and validate returned patient list.
5. Validate patient inference using:
   - `GET /api/jobs/{job_id}/patient-inference?patient_id=<external_patient_id>`
   - Note: this endpoint expects external patient ID (mapped internally to subject ID).

### T2P RAG Log Markers (Required)

For same job id, verify logs contain:

- `[T2P] Start workflow ... retrieval_mode=rag ... debug=True`
- `[T2P][DEBUG] retrieval inputs prospective_patient_count=... rag_threshold=...`
- `[T2P][DEBUG] rag_trial fields title_len=... text_len=... diseases=... drugs=...`
- `[RAG:T2P] Retrieving patients ...`
- `[RAG:T2P] Retrieved <X> patient candidates`
- `[T2P] RAG retrieval returned <X> patient candidates`
- `[T2P][DEBUG] RAG hydrated summaries kept=<Y> requested=<X>`
- `[T2P][DEBUG] Persisting retrieval mapping nct_id=... patient_ids=...`
- `[T2P] Matching stage completed`
- `[T2P] Aggregation stage completed`
- `[T2P][DEBUG] final ranked patients=...`

### T2P Pass/Fail Criteria

Pass when:

- Start API responds with valid `job_id`
- Job status reaches `COMPLETED`
- RAG markers appear in logs
- Results endpoint returns expected structure
- Patient inference succeeds for patient IDs returned in results

Warn when:

- `RAG retrieved X` but hydrated/usable patients are much lower (`Y << X`)
- Sparse fallback warning appears (`fastembed unavailable`)

Fail when:

- Any stage fails
- No RAG markers in logs despite `retrieval_mode=rag`
- Inference called with wrong patient identifier type (subject UUID instead of external ID)
