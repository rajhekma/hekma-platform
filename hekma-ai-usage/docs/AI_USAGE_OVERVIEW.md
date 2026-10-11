# AI Usage — what it is and why it is built this way

For product, leadership, and engineers who need the problem, the outcome, and the architecture choices. The developer design is [AI_USAGE_HLD.md](./AI_USAGE_HLD.md).

---

## 1. The problem

Hekma pays OpenAI, Claude, and other model providers for Scan AI, Health Summary, and Trial Match. That spend was invisible at the only grain the business can act on: **a patient**.

| Product | Before |
|---------|--------|
| Scan AI | The vision call returned token counts. The pipeline ignored them. |
| Health Summary | Tokens existed on the HTTP response for that request, then disappeared. A cache hit looked like zero usage. |
| Trial Match | Matching computed tokens and dropped them before they were saved. |

Provider invoices showed a monthly total. They could not say which patient, which product, or which model produced it. There was no way to see cost before and after a change, or to price a customer later.

Historical calls cannot be reconstructed. The counts were never stored.

---

## 2. What we implemented

**AI Usage** is a ledger inside hekma-platform. Each successful model call becomes one event: patient, product, feature, provider, model, and token counts. No prompts and no clinical text.

The ledger prices the event at that moment and stores the USD amount. A later price-list change does not rewrite history.

Anyone with a patient id can ask:

- total tokens and USD
- split by Scan AI, Health Summary, and Trial Match
- split by OpenAI, Claude, Gemini, Groq, and model
- the list of individual API calls

A local dashboard shows that for one patient. Dev and QA each need the API deployed with their own database. The dashboard stays on a laptop and points at whichever environment you want to read.

---

## 3. What it achieves

| Outcome | Why it matters |
|---------|----------------|
| Cost per patient | Unit economics for Scan AI and Trial Match, which are meant to be sold per use |
| Cost per product | See whether a scan, a summary, or a match is the expensive step |
| Cost per provider and model | Compare GPT-4o and Claude on the same patient without opening two invoices |
| A number that does not move later | Finance and engineering look at the same stored cost |
| A hook for every future service | A new model caller emits one event. It does not build its own cost table |
| Safe for clinical traffic | The patient request does not wait on the ledger, and the ledger never stores the chart or the prompt |

Failed calls and cache hits are not billed. That matches what the provider charged.

---

## 4. Architecture choices

### One owner, not a new microservice

Platform architecture is five deployables. Metering belongs in **hekma-platform** with the gateway, entitlements, and future billing, because they share customer, plan, and usage data.

A library inside each service would create two price lists and two answers for the same patient. A separate “AI cost service” would add another database and another release for a log that billing will need anyway.

Product services keep a small emitter. The ledger, the catalog, and the query API stay in `hekma-ai-usage`.

### The patient request does not depend on the ledger

The emitter never raises and does not block. In a deployed environment the event can go to SQS (`ai-usage-recorded`) so a ledger outage does not fail a scan. Locally, services POST straight to the API.

### Cost is frozen at ingest

The query sums stored dollars. It does not re-price when OpenAI changes a list price. Unknown models are stored as unpriced at `$0` so the call is not lost. New catalog rows apply to new events only.

### No clinical content

The event is counts and identifiers. Prompts, completions, and documents stay in the product that called the model.

### One ledger per environment

Dev, QA, and a laptop each have their own database. A local dashboard can read a remote ledger by pointing `AI_COST_BASE_URL` at that environment’s API. It cannot see remote traffic while it still reads the laptop database.

Dev and QA services must send events to the AI Usage API **in that same environment**. `127.0.0.1` on a developer machine is not that API.

### Patient id is the Hekma id

Every event uses the MySQL patient id used by the patient app. Trial Match’s internal subject id is not the key. That is what makes one query cover scanner, summary, and matching.

---

## 5. What this does not do yet

- Invoices, subscriptions, or quotas. Those are the rest of commerce. They should reuse these events, not a second usage table.
- PHI Shield.
- Trial ingest that rewrites a trial and has no patient id. That call is not stored on a patient.
- Groq study summaries. The hook is in place, but the summary is cached per trial and has no patient id, so the recorder drops it.
- Embeddings that run outside a patient job, including corpus ingest and the Qdrant health-check ping. Embeddings inside a patient match are recorded.
- Offline scripts (trial structuring, Synthea and MIMIC batch files, and the `TrialGPT_RAG` tree).
- A public or deployed dashboard. The UI is a local monitor.
- Spend from before this was turned on.

---

## 6. Benefit in one line

Hekma can now say what a patient’s AI usage cost, which product and which model produced it, and can add the next service without inventing a new cost system.
