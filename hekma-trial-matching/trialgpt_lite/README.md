# TrialGPT Lite

**TrialGPT Lite** is a lightweight, modular, and resilient clinical trial matching engine powered by the official [ClinicalTrials.gov REST API v2](https://clinicaltrials.gov/data-api/api).

It takes a **medical condition** (e.g., `"triple negative breast cancer"`, `"non-small cell lung cancer"`) and an optional **patient profile / EHR note**, retrieves matching studies, pre-filters demographics/status, and evaluates protocol criteria using a **100% offline rule-based & heuristic clinical engine** (NO external LLM, NO API keys required).

---

## 🚀 Features

- **ClinicalTrials.gov REST API v2**: Searches real-time trials via `https://clinicaltrials.gov/api/v2/studies` using `query.cond`, field projection (`fields=...`), and pagination tokens.
- **100% Local / Offline Rule-Based Matcher**:
  - **Zero External API Keys**: Operates entirely within local Python. No OpenAI, Gemini, or remote LLM endpoints required.
  - **Comprehensive Clinical Logic**: Handles numerical age boundaries, biological sex, pregnancy/lactation exclusions, oncology biomarkers (EGFR, HER2, BRAF, ALK, KRAS, PD-L1, ER/PR), staging/histology, and clinical contraindications.
  - **Negation Detection**: Advanced negation recognition prevents false positives (e.g. recognizing "no evidence of brain metastases" as non-contraindicating).
  - **Evidence Attribution**: Maps protocol requirements directly to individual patient clinical sentences.
- **Two-Tier Matching Pipeline**:
  - **Tier 1 (Fast Filter)**: Instant demographic (age, biological sex) and recruitment status screening in milliseconds.
  - **Tier 2 (Rule-Based Matcher)**: Detailed inclusion and exclusion criteria analysis with explainable clinical verdicts.
- **Resilient & Fault Tolerant**:
  - Query relaxation when specific multi-token queries yield 0 results.
  - Automatic exponential backoff retries on rate limits (HTTP 429) or transient 5xx errors.
- **Flexible Interface**: Use as a Python library, standalone FastAPI service, or via the interactive CLI.

---

## 📦 Installation

Ensure dependencies are installed (100% lightweight, no heavy AI packages):

```bash
pip install -r trialgpt_lite/requirements.txt
```

No API keys needed! The application runs completely offline and locally.

## 🌐 Web UI (Interactive Dashboard)

Start the local web application:

```bash
python -m trialgpt_lite.app
```

Then open your browser at **[http://localhost:8050](http://localhost:8050)**.

The UI includes:
- **1-Click Clinical Presets** (NSCLC, TNBC, Melanoma, Type 2 Diabetes)
- **Live Metrics Strip** (Total trials in registry, retrieved, evaluated, latency)
- **Interactive Verdict Filters** (Eligible ✅, Likely 🟡, Ineligible ❌)
- **Detailed Criteria Drawer** with clinical reasoning and cited facts per criterion
- **Direct NCT Registry Links**

## 📊 ClinicalTrials.gov Registry Monitoring (`status=RECRUITING`)

TrialGPT Lite features a built-in monitoring engine that tracks active global trial volume, daily new trial arrivals, and protocol amendments.

### Monitored Metrics:
- **Total Active Volume**: Total recruiting studies currently available in ClinicalTrials.gov (e.g. **64,486+**).
- **Daily Newly Added**: Studies newly approved and publicly posted by NLM in the past 24h / 7d (e.g. **+34 today**, **+197 this week**).
- **Daily Updated**: Existing recruiting trials with protocol amendments, site updates, or status changes in the past 24h / 7d (e.g. **458 today**, **2,108 this week**).
- **Persistent SQLite Snapshots**: Stored in `trialgpt_lite/data/trial_monitoring.db` for drift tracking and offline reliability.

### REST Endpoints:
```bash
# 1. Live stats & daily delta summary
curl http://localhost:8050/api/registry/metrics

# 2. Feed of newly added recruiting trials (last 7 days)
curl "http://localhost:8050/api/registry/feed?type=new&days=7&limit=25"

# 3. Feed of recently amended recruiting trials (last 7 days)
curl "http://localhost:8050/api/registry/feed?type=updated&days=7&limit=25"

# 4. Historical snapshot trend
curl "http://localhost:8050/api/registry/history?limit_days=30"
```

---

## 💻 CLI Usage

### 1. Condition Search (Fast Retrieval)

```bash
python -m trialgpt_lite.cli --condition "triple negative breast cancer" --max-trials 5
```

### 2. Patient Matching (Demographics + Clinical Note)

```bash
python -m trialgpt_lite.cli \
  --condition "non-small cell lung cancer" \
  --age 58 \
  --sex "FEMALE" \
  --patient-note "Patient is a 58-year-old female diagnosed with stage IV non-small cell lung cancer. Biopsy confirmed EGFR exon 19 deletion. ECOG performance status is 1. No brain metastases. Prior treatment with carboplatin and pemetrexed." \
  --max-trials 5 \
  --max-llm 2
```

### 3. JSON Output for Automation

```bash
python -m trialgpt_lite.cli --condition "melanoma" --max-trials 2 --json
```

---

## 🐍 Python API Usage

```python
from trialgpt_lite import TrialGPTLiteService, MatchRequest, PatientProfile

service = TrialGPTLiteService()

# 1. Condition-only query
report = service.search_and_match(
    MatchRequest(condition="glioblastoma", max_trials=5, recruiting_only=True)
)
print(f"Found {report.total_trials_in_registry} studies in registry.")

# 2. Patient Matching query
patient = PatientProfile(
    age=62.0,
    sex="MALE",
    condition="Melanoma",
    clinical_note="62 yo male with BRAF V600E mutated cutaneous melanoma. No prior checkpoint inhibitor therapy. Normal cardiac and renal function."
)

report = service.search_and_match(
    MatchRequest(
        condition="Melanoma",
        patient=patient,
        max_trials=10,
        max_llm_evals=3,
        recruiting_only=True
    )
)

for trial in report.trials:
    print(f"[{trial.verdict.value}] {trial.nct_id}: {trial.title}")
    print(f"Score: {trial.eligibility_score:.2f} | {trial.summary_reasoning}")
```

---

## 📁 Project Structure

```text
trialgpt_lite/
├── __init__.py           # Package exports
├── cli.py                # Command-line interface
├── config.py             # Environment configuration & defaults
├── requirements.txt      # Minimal dependencies
├── service.py            # Main TrialGPTLiteService orchestrator
├── client/
│   ├── __init__.py
│   └── ctgov_client.py   # ClinicalTrials.gov API v2 client
├── parser/
│   ├── __init__.py
│   ├── criteria_parser.py # Criteria text splitter & age parser
│   └── study_normalizer.py # Raw JSON to TrialStudy normalizer
├── matcher/
│   ├── __init__.py
│   ├── fast_filter.py    # Demographic & status pre-filter
│   ├── prompt_templates.py # Clinical prompt templates
│   ├── llm_matcher.py    # Criterion evaluator (OpenAI/Gemini/Heuristic)
│   └── scorer.py         # Confidence scoring & aggregation
├── schemas/
│   ├── __init__.py
│   ├── request.py        # Request & Patient data models
│   ├── study.py          # Study protocol models
│   └── match_result.py   # Verdicts, scores, and report models
└── tests/
    ├── test_criteria_parser.py
    ├── test_ctgov_client.py
    ├── test_fast_filter.py
    └── test_scorer.py
```
