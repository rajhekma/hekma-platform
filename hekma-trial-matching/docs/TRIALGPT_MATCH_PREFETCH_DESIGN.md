# TrialGPT Match Prefetch & Incremental Refresh Design

**Status:** Proposed  
**Audience:** Backend / platform  
**Goal:** Make Patient→Trials (P2T) and Trial→Patients (T2P) **feel instant** for onboarded Fasten patients by precomputing durable match artifacts in the background, and **keeping them fresh** when clinical data changes.

---

## 1. Problem statement

Today, interactive P2T is expensive and multi-stage:

1. Ensure patient summary + structured profile exist (`trialgpt_eligible_patients`)
2. Ensure patient vectors exist in Qdrant (`patient_profiles_hybrid_v1`)
3. RAG retrieve candidate trials
4. LLM matching (criteria-level)
5. LLM aggregation
6. Ranking + persist job tables

Steps 4–5 dominate latency (minutes). Job-parameter caching (`force_rerun` / `find_completed_job_by_parameters`) helps **identical re-requests**, but:

- First Find for a disease/region still pays full cost
- Cache is job-shaped, not patient-profile-shaped
- Data updates (new labs from Fasten) do not invalidate or refresh matches
- T2P still depends on up-to-date patient embeddings + summaries

**Desired:** On onboard (and continuously afterward), TrialGPT materializes a **patient match map** so UI Find returns precomputed results; background workers refresh when data or trial corpus changes.

---

## 2. Design principles (staff-engineer constraints)

| Principle | Implication |
|-----------|-------------|
| **Separate “prepare” from “serve”** | Interactive path reads materialized results; never blocks on LLM unless cold miss. |
| **Layered artifacts** | Don’t only cache final rankings — cache summary, embedding, retrieval shortlist, and matching independently so refreshes are incremental. |
| **Event-driven invalidation** | Prefer Fasten/webhooks + `last_data_timestamp` over blind nightly full recompute. |
| **Idempotent workers** | Upserts keyed by `(subject_id, scope_hash, artifact_version)`. Safe retries. |
| **Cost-aware** | Full LLM match is selective; cheap stages (summary/embed/retrieve) run more often. |
| **Graceful degradation** | Cold patient → async job + status poll (current UX); warm patient → instant read. |
| **Scope is explicit** | Prefetch is never “all trials × all diseases”; use disease/region scopes derived from patient + product rules. |

---

## 3. Recommended architecture (high level)

```
┌─────────────────┐     webhook / onboard      ┌──────────────────────┐
│ Fasten Health   │ ─────────────────────────► │ Ingest / Change bus  │
│ (labs, FHIR)    │                            │ (queue: patient.changed)
└─────────────────┘                            └──────────┬───────────┘
                                                          │
                    ┌─────────────────────────────────────▼───────────────┐
                    │              TrialGPT Prefetch Orchestrator         │
                    │  (state machine per subject_id)                     │
                    └──────┬──────────────┬───────────────┬──────────────┘
                           │              │               │
              ┌────────────▼──┐  ┌────────▼────────┐  ┌──▼──────────────┐
              │ L1 Summary    │  │ L2 Embed        │  │ L3 Match map    │
              │ + structured  │  │ Qdrant upsert   │  │ retrieval+LLM   │
              │ Postgres      │  │                 │  │ materialized    │
              └───────────────┘  └─────────────────┘  └─────────────────┘
                                                          │
                                              ┌───────────▼───────────┐
                                              │ Serve path (API)      │
                                              │ read match map first  │
                                              │ else enqueue + poll   │
                                              └───────────────────────┘
```

### Why not “only Redis-cache the job response”?

Job cache is necessary but insufficient:

- Doesn’t survive disease/region variants cleanly without combinatorial explosion
- Doesn’t refresh on FHIR changes
- Doesn’t help T2P (needs embeddings/summaries, not a single job blob)

Prefer a **materialized match store** + optional Redis for hot API responses.

---

## 4. Artifact layers (what to precompute)

### L1 — Clinical profile (already largely exists)

| Artifact | Store | Trigger |
|----------|-------|---------|
| `summary_text`, `structured_json`, `disease_list`, `last_data_timestamp` | `trialgpt_eligible_patients` | Onboard + FHIR update |
| Deterministic age/BMI injection | Serve-time (already in `compose_repo`) | Always |

**SLA:** seconds–low minutes per patient (LLM summary).  
**Idempotency:** skip if `source_data_hash` unchanged.

### L2 — Vector index

| Artifact | Store | Trigger |
|----------|-------|---------|
| Dense + sparse patient vectors | Qdrant `patient_profiles_hybrid_v1` | After L1 changes |

**SLA:** seconds (batched OpenAI embeddings).  
**Critical for T2P** and RAG P2T recall.

### L3 — Match map (new — the product win)

Precompute **P2T rankings for a bounded set of scopes**, not the entire trial corpus.

#### Scope model

A **scope** is what the UI Find button uses:

```text
scope = {
  subject_id,
  diseases: [...],      # from disease_list or UI selection set
  regions:  [...] | null,  # null = “all regions” / nation-wide mode if product allows
  corpus / retrieval_mode / model fingerprint
}
scope_key = sha256(canonical_json(scope))
```

**Scope selection policy (onboard):**

1. Take patient’s top N diseases from `disease_list` / ICD entries (e.g. N=5–10, ranked by recency/severity heuristic).
2. For each disease, resolve region list via existing `fetch_locations_by_diseases` (already normalized).
3. Prefetch:
   - `(disease, top_K_regions)` — e.g. K=3 nearest or product-priority sites  
   - OR `(disease, region=null)` if UI allows “any location”  
4. Cap total scopes per patient (e.g. ≤ 15) to control LLM cost.

#### Match map table (new)

```sql
-- migration sketch
CREATE TABLE trialgpt_patient_match_map (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_id      UUID NOT NULL,
  scope_key       TEXT NOT NULL,
  scope_json      JSONB NOT NULL,           -- diseases, regions, model, etc.
  status          TEXT NOT NULL,            -- PENDING|RUNNING|READY|STALE|FAILED
  source_data_hash TEXT,                    -- hash of L1 inputs used
  trial_corpus_version TEXT,                -- see §7
  ranking_json    JSONB,                    -- compact evaluations[] payload
  top_nct_ids     TEXT[],                   -- convenience index
  metrics         JSONB,                    -- counts, token usage, latency
  error           TEXT,
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now(),
  ready_at        TIMESTAMPTZ,
  UNIQUE (subject_id, scope_key)
);

CREATE INDEX ON trialgpt_patient_match_map (subject_id, status);
CREATE INDEX ON trialgpt_patient_match_map (status, updated_at);
```

`ranking_json` should be the **same shape** as `/api/jobs/{id}/results` evaluations (or a thin wrapper), so the UI can reuse one renderer.

#### Optional L3b — criterion detail cache

Store matching inclusion/exclusion blobs keyed by `(subject_id, nct_id, criteria_hash)` so inference deep-dives don’t re-LLM. Can reuse existing `matching_results` tables with `flow_type='P2T_PREFETCH'` and a synthetic `job_id` per map row.

---

## 5. When to run what (lifecycle)

### A. Patient onboard (Fasten connected) — **best primary trigger**

```
onboard(subject_id):
  enqueue PatientPipeline(subject_id, reason=ONBOARD, priority=HIGH)
```

Pipeline stages (sequential, checkpointed):

1. **Ingest FHIR** → update raw tables / Fasten sync marker  
2. **L1** summary + structured (+ disease_list)  
3. **L2** embed → Qdrant  
4. **Build scopes** from disease_list + region policy  
5. **L3** for each scope (parallel workers, rate-limited)  
6. Mark patient `trialgpt_ready=true`

**UX:** Onboarding UI shows “Preparing trial matches…”; Find becomes instant when L3 READY for that disease/region.

### B. Continuous / backfill — **required for existing ~30k cohort**

- Queue: `PatientPipeline(reason=BACKFILL, priority=LOW)`
- Shard by `subject_id` hash (same pattern as `run_patient_summary_embed_job`)
- Fair scheduling: never starve ONBOARD behind BACKFILL (separate queues or priority weights)

### C. Data update (lab / med / condition change) — **invalidation + selective refresh**

```
on_fhir_change(subject_id, change_set):
  new_hash = hash(clinical_fingerprint(subject_id))
  if new_hash == stored_hash: return

  mark L1/L2 STALE
  mark all match_map rows for subject STALE

  enqueue PatientPipeline(reason=DATA_UPDATE, priority=HIGH if user active else NORMAL)
```

**Selective L3 refresh:**

| Change type | Recompute |
|-------------|-----------|
| Demographics only (age-affecting DOB rare) | L1 light + L3 for age-sensitive scopes |
| New labs / HbA1c / BMI vitals | L1 + L2 + L3 for metabolic scopes |
| New condition in disease_list | L1 + L2 + add new scopes + refresh overlapping |
| Noise / unchanged coded data | no-op via hash |

### D. Trial corpus change

When trials are ingested/updated in `trialgpt_corpus` / Qdrant:

- Bump global `trial_corpus_version`
- Mark match maps with older version **STALE** (lazy) or enqueue region/disease-affected scopes (targeted)

Do **not** recompute all 30k patients synchronously; use lazy recompute on next Find + background drain of STALE rows.

---

## 6. Interactive serve path (API contract change)

### Fast path (warm)

```
POST /api/patient-to-trials/start
  → resolve subject_id + scope_key
  → if match_map READY and source_data_hash current and corpus_version current:
        create matching_jobs row status=COMPLETED (or return cached:true + map_id)
        return results from ranking_json  # < 200ms
  → else:
        enqueue / continue pipeline for that scope
        return STARTED + job_id  # existing poll UX
```

### Compatibility

Keep today’s job tables for audit and deep inference. Prefetch can:

- **Option A (recommended):** Materialize into `trialgpt_patient_match_map`, and on hit **copy** into `final_ranking` / `matching_results` under a real `job_id` so `/results` and `/nct-inference` stay unchanged; or  
- **Option B:** Teach `/results` to read from match_map when `parameters.prefetch=true`.

Option A minimizes frontend churn.

### T2P note

Prefetching every trial×patient is impossible at scale. For T2P:

- Keep **L1+L2 always fresh** (this is the main T2P win)
- Optionally maintain reverse indexes: `trial_shortlist_patients[nct_id]` refreshed periodically for **active recruiting trials** only
- Interactive T2P still runs LLM match on RAG shortlist, but retrieval quality/latency improves when L2 is warm

---

## 7. Versioning & freshness keys

```text
source_data_hash = sha256(
  fhir_last_updated,
  summary_text fingerprint,
  structured_json fingerprint,
  disease_list
)

match_engine_version = "p2t-rag-v3"   # ranking formula, prompts, filters
trial_corpus_version = ingest watermark / max(updated_at) of corpus
llm_fingerprint = f"{llm_service}:{model}"
```

A map row is **servable** iff:

```text
status == READY
AND source_data_hash == current
AND trial_corpus_version == current
AND match_engine_version == current
AND llm_fingerprint matches request (or request allows default)
```

Else treat as miss → refresh.

---

## 8. Worker / queue design (scalability)

### Queues (suggested)

| Queue | Priority | Payload |
|-------|----------|---------|
| `trialgpt.patient.high` | Onboard, active-user updates | `{subject_id, reason, stages?}` |
| `trialgpt.patient.low` | Backfill, stale drain | same |
| `trialgpt.match.scope` | Per-scope LLM work | `{subject_id, scope_key, scope_json}` |

Use Redis Streams / SQS / Rabbit / Celery — any durable queue. Prefer **at-least-once** + idempotent upserts.

### Concurrency controls

- Global LLM semaphore (already have `TRIALGPT_LLM_WORKERS`)
- Per-patient lock: only one pipeline active per `subject_id` (avoid duplicate spend)
- Per-scope dedupe: if RUNNING, don’t enqueue duplicate
- Embed batching for L2 (already have `embed_batch`)

### Throughput sketch (order-of-magnitude)

Assume:

- L1: ~$0.01–0.05 / patient, 10–60s  
- L2: fractions of a cent, <5s  
- L3: ~$0.05–0.30 / scope (depends on candidate count × model)

For 30k patients × 5 scopes ≈ 150k L3 jobs → **must** be staged, prioritized, and capped. Start with:

1. Active patients (logged in last 30/90 days)  
2. Onboard-as-you-go  
3. Passive fill of remaining cohort

---

## 9. Cost control levers (must-have)

1. **Candidate cap per scope** — e.g. RAG 20 after disease/region filter (already improved).  
2. **Skip aggregation LLM** for prefetch if ranking from matching scores is enough for list UI; run aggregation on-demand for inference drill-down.  
3. **Cheaper model for prefetch** (`haiku` / `gpt-4o-mini`), upgrade on user open.  
4. **Scope budget** — max scopes/patient/day.  
5. **Debounce** FHIR webhooks (e.g. 15–60 min coalesce window).  
6. **Partial update** — if only BMI/age line changes and summary body hash same, skip full L1 LLM; recompute deterministic prefix + maybe skip L3 if criteria unaffected (conservative: still mark metabolic scopes STALE).

---

## 10. API / product surface (suggested)

| Endpoint | Purpose |
|----------|---------|
| `POST /api/patient/{id}/trialgpt/prepare` | Explicit prepare (onboard hook) |
| `GET  /api/patient/{id}/trialgpt/ readiness` | `{l1,l2,scopes:[{scope,status,ready_at}]}` |
| Existing `POST .../patient-to-trials/start` | Prefer warm map; else async |
| Admin: `POST /api/admin/trialgpt/backfill` | Shard backfill controls |

Webhooks from Fasten → internal `prepare` with `reason=DATA_UPDATE`.

---

## 11. Consistency with current web UI bug

Prefetch **does not replace** status polling. Warm hits return `COMPLETED` immediately; cold hits still need:

```text
poll /status → then /results
```

Prefetch reduces how often users hit the cold path.

---

## 12. Phased rollout plan

### Phase 0 — Instrument (1–2 days)

- Log P2T stage timings + token cost per job  
- Measure % Find requests that are repeats vs new scopes  

### Phase 1 — Warm L1/L2 on onboard (1 week)

- Hook Fasten onboard → summary + embed pipeline (you largely have pieces)  
- Guarantee Qdrant point exists before first Find  
- **Immediate T2P + RAG quality win**; P2T still LLM-bound  

### Phase 2 — Match map for default scopes (2–3 weeks)

- Table + worker + serve-path short-circuit  
- Onboard: top diseases × priority regions  
- Feature flag per env  

### Phase 3 — Incremental refresh (1–2 weeks)

- `source_data_hash` + webhook debounce  
- STALE drain worker  
- Corpus version bump on trial ingest  

### Phase 4 — Optimize cost (ongoing)

- Aggregation-on-demand  
- Cheaper prefetch model  
- Active-cohort prioritization  

---

## 13. Decision: onboard-time vs pure background?

**Do both**, with clear priorities:

| Mode | Use |
|------|-----|
| **Onboard / active-user (HIGH)** | Best UX; pays cost when it matters |
| **Background backfill (LOW)** | Covers existing cohort without blocking product |
| **Update-triggered (HIGH/NORMAL)** | Correctness when labs change |

Pure onboard-only leaves legacy patients cold. Pure nightly-only leaves new patients waiting. Hybrid is the scalable answer.

---

## 14. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| LLM cost blow-up | Scope caps, cheaper models, skip aggregation, priority queues |
| Stale clinical advice | Strict hash/version gates; show `ready_at` / “last refreshed” in UI |
| Duplicate work | Per-subject lock + unique `(subject_id, scope_key)` |
| Empty disease∩region | Already possible; map READY with `evaluations=[]` is valid — UI must not treat as in-progress |
| Worker failure | Checkpoint stages; DLQ; partial READY (L1/L2 ready even if L3 pending) |

---

## 15. Success metrics

- P50/P95 time-to-first-Find-result for warm patients: **&lt; 1s**  
- Cold → READY after onboard: P50 **&lt; 5 min** for default scopes  
- % Finds served from match_map: target **&gt; 70%** after Phase 2  
- Cost per onboarded patient (L1+L2+L3): tracked weekly  
- Stale serve rate (served with outdated hash): **~0** (hard gate)

---

## 16. Concrete recommendation (what to build first)

1. **On Fasten onboard:** always run L1 + L2 (summary + Qdrant).  
2. **Add `trialgpt_patient_match_map`** and a scope worker for top diseases × filtered regions.  
3. **Change P2T start** to return cached COMPLETED from match_map when fresh.  
4. **On FHIR update:** recompute hash → mark STALE → re-enqueue.  
5. **Backfill** active patients only, then expand.

This yields instant Find for common paths without pretending you can precompute the entire trial×patient Cartesian product.

---

## 17. Relation to existing code

| Existing | Reuse |
|----------|-------|
| `trialgpt_eligible_patients` | L1 store |
| `services/patient_summary_batch_service.py` / embed jobs | L1/L2 workers |
| `filter_nct_ids_by_location_and_diseases` | Scope candidate filter |
| `workflows/patient_to_trials.py` | Core of L3 (extract “run_scope_match” function) |
| `find_completed_job_by_parameters` | Keep as secondary cache; match_map is primary |
| Job status polling | Still required for cold path |

---

*End of design.*
