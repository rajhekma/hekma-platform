# TrialGPT Eligible Patients — Load Design

design for loading ~30k patients for TrialGPT (summaries + Qdrant).

---

## Goal

Make the **~30,637** patients in `trialgpt_eligible_patients` usable in TrialGPT (P2T / T2P with RAG).

**Write summaries into** `trialgpt_eligible_patients`, not `compose_summary_block`.  
`compose_summary_block` will be removed from the code after cutover.

---

## Big picture

```text
MySQL Patient (IDs)
        │
        ▼
trialgpt_eligible_patients  ←── cohort list (~30k) + summaries go HERE
        ▲
        │ read FHIR
Postgres FHIR tables (patient, condition, meds, labs, …)
        │
        ▼
   LLM (or other) creates:
   • summary_text
   • structured_json (7 blocks)
        │
        ▼
   OpenAI embed → Qdrant (patient vectors)
        │
        ▼
   TrialGPT API (P2T / T2P)
```

Trials are already loaded (~2,508 in Qdrant). This job is **patients only**.

---



## Why these fields?


| Field                        | Needed?       | Why                                                                 |
| ---------------------------- | ------------- | ------------------------------------------------------------------- |
| `summary_text`               | **Yes**       | Matching, keywords, T2P patient text. Job fails without it.         |
| `structured_json` (7 blocks) | **Yes (RAG)** | Used to find trials/patients in Qdrant.                             |
| `disease_list`               | No            | Nice for UI; not required for matching. Skip ICD LLM on first pass. |


**LLM is not mandatory** — you need the *fields*. LLM is the usual way to build them from FHIR. Rule-based or copy from another table also works if quality is OK.

**Raw FHIR alone is not enough** today — P2T/T2P do not read raw `condition` / `observation` tables.

### 7 blocks inside `structured_json`

`demographics`, `allergies`, `conditions`, `procedures`, `medications`, `observations`, `immunizations`

---



## Table design (`trialgpt_eligible_patients`)

Already has ~30,637 ID rows. **Add** summary columns:


| Column                | Purpose                                      |
| --------------------- | -------------------------------------------- |
| `subject_id`          | Primary key (UUID) — same as API subjectId   |
| `mysql_patient_id`    | External API patient id                      |
| `summary_text`        | Clinical narrative                           |
| `structured_json`     | 7-block profile (JSONB)                      |
| `disease_list`        | Optional                                     |
| `last_data_timestamp` | FHIR data time (skip/resume)                 |
| `last_generated_at`   | When summary was created                     |
| `summary_status`      | `pending` / `ready` / `failed`               |
| Existing flags        | `has_pg_patient`, `clinical_latest_ts`, etc. |


Replace `in_compose_summary_block` with `summary_status` (or “has summary_text”).

---



## Qdrant


| Item                 | Value                                             |
| -------------------- | ------------------------------------------------- |
| Collection           | `patient_profiles_hybrid_v1`                      |
| Dense vector         | OpenAI `text-embedding-3-large` from the 7 blocks |
| Sparse vector        | Local BM25 (free)                                 |
| Point id             | Stable id from `subject_id`                       |
| Skip query expansion | Yes (saves chat LLM cost)                         |


---



## How we run (no cascade failure)

1. Read IDs from `trialgpt_eligible_patients` where summary is missing
2. Load FHIR → build input
3. Create `summary_text` + `structured_json` (2 LLM calls, or 1 combined later)
4. Update the **same row** in `trialgpt_eligible_patients`
5. Embed into Qdrant
6. On error: log to DLQ, continue next patient
7. Restart = resume (skip rows already `ready`)
8. Use **4 shards** for the full ~30k run

**Pilot first:** 100 → 1,000 → full.

---



## Cost (main money = Claude)


| Step                       | Share    | ~30k mid cost          |
| -------------------------- | -------- | ---------------------- |
| LLM summary + 7-block JSON | **~99%** | **~$700–900** (Sonnet) |
| OpenAI embeddings          | **~1%**  | **~$2–3**              |
| BM25 / DB / Qdrant ops     | —        | Not per-token AI       |



| Cohort  | Mid total (Sonnet + embed) |
| ------- | -------------------------- |
| 100     | ~$3                        |
| 1,000   | ~$25–30                    |
| ~30,600 | ~$700–905                  |


**Cheaper options:** Haiku (~~⅓), shorter FHIR input, one LLM call, Batch API (~~50% off).

Table name does **not** change cost.

---



## What you need

- Postgres + `trialgpt_eligible_patients` (IDs done)  
- FHIR data in Postgres (already used for eligibility)  
- `ANTHROPIC_API_KEY` (summaries)  
- `OPENAI_API_KEY` (embeddings)  
- Qdrant (trials already OK)  
- Code change: read/write eligible table instead of `compose_summary_block`  
- Budget ~$700–900 (or less with Haiku)

---



## Cutover (remove `compose_summary_block`)

1. Add summary columns to `trialgpt_eligible_patients`
2. Point summarize + embed + P2T/T2P to this table
3. Copy any existing compose rows into eligible (if still needed)
4. Verify P2T / T2P
5. Remove `compose_summary_block` from code, then drop table

**Do not drop compose before the code switch.**

---



## Note on MIMIC

`mimic_patient_summary` has **3,003** rows but **0 overlap** with this 30k cohort. Cannot copy those summaries into eligible for free.

---



## Success

- ~30k rows have `summary_text` + 7-block `structured_json`  
- ~30k points in Qdrant patient collection  
- P2T / T2P RAG work for sample patients  
- Failures only in DLQ and retriable

---



## One-line summary

**Store TrialGPT patient summaries on** `trialgpt_eligible_patients`**, embed them to Qdrant; almost all cost is LLM for summary + 7 blocks (~$700–900 for 30k on Sonnet).**