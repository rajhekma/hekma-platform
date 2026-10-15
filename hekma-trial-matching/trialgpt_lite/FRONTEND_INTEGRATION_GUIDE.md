# TrialGPT Lite: Frontend Integration Guide & API Specification

This guide provides everything the frontend engineering team (React / Next.js / Vue / Angular / Mobile) needs to integrate the **Trial Matching Engine** and **Live Registry Monitoring Dashboard**.

---

## 🚀 1. Interactive Swagger / OpenAPI Documentation

FastAPI auto-generates interactive API documentation:
- **Interactive Swagger UI**: `http://localhost:8050/docs`
- **ReDoc UI**: `http://localhost:8050/redoc`
- **OpenAPI JSON Schema**: `http://localhost:8050/openapi.json`

---

## 📡 2. Complete REST API Specifications

### Feature A: Clinical Trial Matching & Search

#### `POST /api/match`
Searches ClinicalTrials.gov and performs 100% offline rule-based criteria matching (zero external LLMs, zero API keys).
Leverages PostgreSQL Cache-Aside (Lazy Loading) for sub-millisecond retrieval on repeated or overlapping searches.

##### Request Payload:
```json
{
  "condition": "non-small cell lung cancer",
  "city_or_zip": "Boston, MA",
  "search_radius_miles": 30,
  "patient": {
    "age": 58,
    "sex": "FEMALE",
    "clinical_note": "Patient is a 58yo female diagnosed with stage IV NSCLC. Biopsy confirmed EGFR exon 19 deletion. ECOG status 1. Prior carboplatin/pemetrexed."
  },
  "page_size": 10,
  "page_token": null,
  "recruiting_only": true,
  "force_refresh": false
}
```

> **Single Match, Pagination, Geo Proximity & Caching**:
> - Each match request returns **top 10 results** by default (`"page_size": 10`).
> - **Geo-Proximity (`city_or_zip` & `search_radius_miles`)**: Pass `city_or_zip: "Boston, MA"` or `"90210"` with optional `"search_radius_miles": 30`. The backend automatically geocodes the location into GPS coordinates and queries ClinicalTrials.gov with `filter.geo=distance(lat,lon,rad)`. Alternatively, provide explicit coordinates in `geo_filter`.
> - To fetch the next 10 results, send the same request body with `"page_token": "<next_page_token>"`.
> - When `"next_page_token"` is `null`, you have reached the last page.
> - **Cache-Aside (`cache_hit: true`)**: If this condition/page was queried previously, results and full protocols are served instantly from PostgreSQL JSONB cache.
> - **Force Refresh (`"force_refresh": true`)**: Set to `true` to bypass the cache and force a live re-fetch from the NIH ClinicalTrials.gov API.
> - **Fast Search Mode**: If you omit `patient` or omit `clinical_note`, the engine runs fast search without criteria evaluations. You can also explicitly pass `"max_criteria_evals": 0`.

##### Response Schema (`ConditionMatchReport`):
```json
{
  "searched_condition": "non-small cell lung cancer",
  "total_trials_in_registry": 1996,
  "retrieved_trials_count": 10,
  "evaluated_trials_count": 3,
  "page_size": 10,
  "current_page_token": null,
  "next_page_token": "ZVNj7o2Elu8o3lpwTcito62tmpOQJJxtY_ek0A",
  "cache_hit": true,
  "execution_time_seconds": 0.04,
  "trials": [

    {
      "nct_id": "NCT05801029",
      "title": "Study of Osimertinib and Amivantamab in Advanced NSCLC",
      "conditions": ["Non-Small Cell Lung Cancer (NSCLC)"],
      "overall_status": "RECRUITING",
      "phases": ["PHASE2"],
      "study_type": "INTERVENTIONAL",
      "interventions": ["Drug: Osimertinib", "Drug: Amivantamab"],
      "age_display": "≥ 18 Years",
      "sex_display": "All / Both",
      "location_display": "Memorial Sloan Kettering, New York, US (+12 sites)",
      "verdict": "INELIGIBLE",
      "summary_reasoning": "Patient is ineligible: Triggered 1 exclusion criteria. Primary reason: Prior systemic chemotherapy for advanced disease.",
      "eligibility_score": 0.05,
      "web_url": "https://clinicaltrials.gov/study/NCT05801029",
      
      "brief_summary": "This study evaluates the safety and efficacy of combined targeted therapies...",
      "detailed_interventions": [
        {"type": "DRUG", "name": "Osimertinib", "description": "80mg oral daily"}
      ],
      "demographics": {
        "minimum_age": "18 Years",
        "maximum_age": null,
        "sex": "ALL",
        "accepts_healthy_volunteers": false
      },
      "design": {
        "allocation": "RANDOMIZED",
        "intervention_model": "PARALLEL",
        "primary_purpose": "TREATMENT",
        "masking": "DOUBLE"
      },
      "enrollment": {"count": 450, "type": "ESTIMATED"},
      "lead_sponsor": "Memorial Sloan Kettering Cancer Center",
      "collaborators": ["National Cancer Institute (NCI)"],
      "timeline": {
        "start_date": "2023-04-15",
        "primary_completion_date": "2026-12-31",
        "completion_date": "2027-06-30"
      },
      "primary_outcomes": [
        {"measure": "Progression-Free Survival (PFS)", "time_frame": "Up to 24 months"}
      ],
      "contacts": {
        "central_contacts": [{"name": "Clinical Trials Office", "phone": "1-800-525-2225", "email": "trials@mskcc.org"}],
        "overall_officials": [{"name": "Dr. Helena Zhang, MD", "affiliation": "MSKCC", "role": "PRINCIPAL_INVESTIGATOR"}],
        "locations": [{"facility": "MSKCC Main Campus", "city": "New York", "state": "NY", "country": "United States", "status": "RECRUITING"}]
      },
      "criteria_evaluations": [
        {
          "criterion_index": 0,
          "criterion_type": "inclusion",
          "criterion_text": "Age >= 18 years",
          "reasoning": "Patient is 58 years old, satisfying the minimum age threshold.",
          "sentence_ids": [0],
          "label": "included"
        },
        {
          "criterion_index": 1,
          "criterion_type": "exclusion",
          "criterion_text": "Prior exposure to systemic anti-cancer therapy",
          "reasoning": "Patient received carboplatin and pemetrexed.",
          "sentence_ids": [4],
          "label": "excluded"
        }
      ]
    }
  ]
}
```

---

#### `GET /api/trials/{nct_id}`
Fetches the full 14-section protocol details on-demand for a single trial by its NCT ID.
Leverages PostgreSQL Cache-Aside for sub-millisecond retrieval (~1ms on cached trials).

- **Path Parameter**:
  - `nct_id` (string, required): e.g. `NCT05801029`
- **Query Parameter**:
  - `force_refresh` (boolean, optional, default: `false`): Set `true` to bypass cache and re-query NIH ClinicalTrials.gov API.

##### Example Request:
```bash
GET /api/trials/NCT05801029?force_refresh=false
```

##### When to Use:
1. **Instant Client-Side Expansion**: In the main matching view, all 14 protocol sections are *already* included in each item of `trials[]` returned by `POST /api/match`. Clicking "More" expands the details instantly in the client (0ms latency, zero extra API calls).
2. **On-Demand Single Fetch**: Use `GET /api/trials/{nct_id}` if your frontend builds a dedicated trial detail page (e.g. `/trials/[nctId]` route in Next.js/React Router), or if a user opens a direct bookmark.

---

### Feature B: System Health & PostgreSQL Cache Diagnostics

#### 1. `GET /api/health`
Returns system health, offline matching engine status, and PostgreSQL Cache status.

#### 2. `GET /api/cache/stats`
Returns live statistics on PostgreSQL Cache-Aside performance:
```json
{
  "status": "online",
  "engine": "PostgreSQL 15 JSONB Cache-Aside",
  "cached_queries_count": 14,
  "query_cache_hits": 82,
  "cached_studies_count": 140,
  "study_cache_hits": 620,
  "query_ttl_seconds": 86400,
  "study_ttl_seconds": 604800
}
```

---


### Feature B: Live Registry Monitoring (`status=RECRUITING`)

#### 1. `GET /api/registry/metrics`
Returns global counts, 24h deltas, 7-day rolling metrics, and sync status.

- **Query Parameters**:
  - `force_refresh` (boolean, optional): Set `true` to bypass server cache.

##### Response:
```json
{
  "status": "online",
  "total_recruiting": 64486,
  "newly_added": {
    "last_24h": 34,
    "last_7d": 197,
    "daily_average_7d": 28.1
  },
  "updated_studies": {
    "last_24h": 458,
    "last_7d": 2108,
    "daily_average_7d": 301.1
  },
  "dates": {
    "today": "2026-10-02",
    "yesterday": "2026-10-01",
    "week_ago": "2026-09-25",
    "month_ago": "2026-09-02"
  },
  "nlm_schedule_note": "NLM/NIH updates the public registry on US business days (Mon–Fri at ~9:00 PM EST).",
  "last_synced_at": "2026-10-02T11:21:56.241512+00:00"
}
```

---

#### 2. `GET /api/registry/feed`
Returns real-time list of studies added or modified within a date window.

- **Query Parameters**:
  - `type` (required): `"new"` (newly posted) or `"updated"` (amendments/site updates)
  - `days` (optional, default: `7`): Number of past days to query (`1`, `7`, or `30`)
  - `limit` (optional, default: `25`, max: `100`): Results per query

##### Response:
```json
[
  {
    "nct_id": "NCT07849023",
    "title": "Precision Partial Interspinous Ligament Preservation Trial",
    "status": "RECRUITING",
    "first_posted": "2026-09-30",
    "last_updated": "2026-10-01",
    "conditions": ["Lumbar Spinal Stenosis"],
    "lead_sponsor": "General Hospital of Western Theater Command",
    "web_url": "https://clinicaltrials.gov/study/NCT07849023"
  }
]
```

---

#### 3. `GET /api/registry/history`
Returns persistent daily snapshots from SQLite for trend graphs.

- **Query Parameters**:
  - `limit_days` (optional, default: `30`)

---

## 💻 3. Copy-Paste TypeScript Types & Client Service

Give this file directly to your frontend team:

```typescript
// types/trialgpt.ts

export type OverallVerdict = 
  | "ELIGIBLE"
  | "LIKELY_ELIGIBLE"
  | "INELIGIBLE"
  | "UNCERTAIN"
  | "RETRIEVED_ONLY"
  | "FILTERED_OUT";

export interface CriterionEvaluation {
  criterion_index: number;
  criterion_type: "inclusion" | "exclusion";
  criterion_text: string;
  reasoning: string;
  sentence_ids: number[];
  label: "included" | "not included" | "excluded" | "not excluded" | "not enough information" | "not applicable";
}

export interface StudyContact {
  name: string | null;
  role: string | null;
  phone: string | null;
  email: string | null;
}

export interface StudyOfficial {
  name: string | null;
  affiliation: string | null;
  role: string | null;
}

export interface StudyLocation {
  facility: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
}

export interface DemographicCriteria {
  minimum_age: string | null;
  maximum_age: string | null;
  sex: string;
  accepts_healthy_volunteers: boolean;
}

export interface InterventionItem {
  type: string;
  name: string;
  description: string | null;
}

export interface StudyDesign {
  allocation: string | null;
  intervention_model: string | null;
  primary_purpose: string | null;
  masking: string | null;
  observational_model: string | null;
  time_perspective: string | null;
}

export interface StudyEnrollment {
  count: number | null;
  type: string | null;
}

export interface StudyTimeline {
  start_date: string | null;
  start_date_type: string | null;
  primary_completion_date: string | null;
  completion_date: string | null;
  first_posted_date: string | null;
  last_update_posted_date: string | null;
}

export interface StudyOutcome {
  measure: string;
  time_frame: string | null;
  description: string | null;
}

export interface ContactsAndLocations {
  central_contacts: StudyContact[];
  overall_officials: StudyOfficial[];
  locations: StudyLocation[];
}

export interface TrialMatchResult {
  // === 1. Primary Output Fields ===
  nct_id: string;                                   // NCT ID (e.g. NCT05801029)
  title: string;                                    // Trial title
  conditions: string[];                             // Disease/condition
  overall_status: string;                           // Recruitment status (e.g. RECRUITING)
  phases: string[];                                 // Phase (e.g. ["PHASE2"])
  study_type: string;                               // Study type (e.g. "INTERVENTIONAL", "OBSERVATIONAL")
  interventions: string[];                          // Intervention names
  age_display: string;                              // Age requirement (e.g. "≥ 18 Years")
  sex_display: string;                              // Sex restriction (e.g. "All / Both", "Female Only")
  location_display: string;                         // Primary facility / city / country summary
  verdict: OverallVerdict;                          // Match status (ELIGIBLE, LIKELY_ELIGIBLE, INELIGIBLE, etc.)
  summary_reasoning: string;                        // Match status / reasons clinical summary
  eligibility_score: number;                        // Confidence score (0.0 to 1.0)
  web_url: string;                                  // ClinicalTrials.gov NCT direct link

  // === 2. Detailed Protocol Information (14 Sections for 'More Details') ===
  brief_summary: string | null;                     // Section 1: Overview (Brief summary)
  // Section 2: Condition -> conditions[]
  detailed_interventions: InterventionItem[];       // Section 3: Treatment (Type, Name, Description)
  criteria_evaluations: CriterionEvaluation[];      // Section 4: Eligibility (Inclusion/exclusion criteria)
  demographics: DemographicCriteria;                // Section 5: Age/Sex (Eligibility demographics)
  design: StudyDesign | null;                       // Section 6: Study Design (Randomized, masking, allocation)
  // Section 7: Phase -> phases[] & study_type
  enrollment: StudyEnrollment | null;               // Section 8: Enrollment (Planned enrollment)
  lead_sponsor: string | null;                      // Section 9: Sponsor (Lead sponsor)
  collaborators: string[];                          // Section 9: Sponsor (Collaborators)
  locations: StudyLocation[];                       // Section 10: Locations (Facilities/cities/countries)
  timeline: StudyTimeline | null;                   // Section 11: Timeline (Start/completion dates)
  primary_outcomes: StudyOutcome[];                 // Section 12: Outcomes (Primary outcomes)
  secondary_outcomes: StudyOutcome[];               // Section 12: Outcomes (Secondary outcomes)
  contacts: ContactsAndLocations;                   // Section 13: Contact (Study contacts & investigators)
  // Section 14: ClinicalTrials.gov -> web_url
}

export interface PatientProfile {
  age?: number | null;
  sex?: string | null;
  condition?: string | null;
  clinical_note?: string | null;
}

export interface MatchRequest {
  condition: string;
  patient?: PatientProfile | null;                // If omitted, runs fast condition search
  page_size?: number;                             // Default: 10 results per page
  page_token?: string | null;                     // Pass response.next_page_token for subsequent pages
  max_criteria_evals?: number | null;             // Optional limit on criteria matching (0 for fast search)
  recruiting_only?: boolean;                      // Filter for status=RECRUITING (default: true)
}

export interface ConditionMatchReport {
  searched_condition: string;
  total_trials_in_registry: number;
  retrieved_trials_count: number;
  evaluated_trials_count: number;
  page_size: number;                              // Defaults to 10
  current_page_token: string | null;              // Null for page 1
  next_page_token: string | null;                 // Pass as page_token to fetch next 10 results
  execution_time_seconds: number;
  trials: TrialMatchResult[];
}

export interface RegistryMetrics {
  status: string;
  total_recruiting: number;
  newly_added: {
    last_24h: number;
    last_7d: number;
    daily_average_7d: number;
  };
  updated_studies: {
    last_24h: number;
    last_7d: number;
    daily_average_7d: number;
  };
  nlm_schedule_note: string;
  last_synced_at: string;
}

export interface RegistryStudyFeedItem {
  nct_id: string;
  title: string;
  status: string;
  first_posted: string | null;
  last_updated: string | null;
  conditions: string[];
  lead_sponsor: string | null;
  web_url: string;
}
```

### TypeScript API Client Example with Pagination Support:

```typescript
// services/trialGptApi.ts
const BASE_URL = process.env.NEXT_PUBLIC_TRIALGPT_API_URL || "http://localhost:8050";

export const trialGptApi = {
  /**
   * Match or search studies with top-10 pagination.
   * - To get page 1: pass `{ condition: "lung cancer", page_size: 10 }`
   * - To get page 2+: pass `{ condition: "lung cancer", page_size: 10, page_token: response.next_page_token }`
   */
  async matchTrials(params: MatchRequest): Promise<ConditionMatchReport> {
    const res = await fetch(`${BASE_URL}/api/match`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_size: 10,
        recruiting_only: true,
        ...params,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // 2. Fetch live registry monitoring summary
  async getRegistryMetrics(forceRefresh = false): Promise<RegistryMetrics> {
    const res = await fetch(`${BASE_URL}/api/registry/metrics${forceRefresh ? "?force_refresh=true" : ""}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // 3. Fetch feed of new or updated studies
  async getRegistryFeed(type: "new" | "updated", days = 7, limit = 25): Promise<RegistryStudyFeedItem[]> {
    const res = await fetch(`${BASE_URL}/api/registry/feed?type=${type}&days=${days}&limit=${limit}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  // 4. Get Patient Eligibility Questionnaire (Real-time Groq LPU with 30-day PostgreSQL Cache)
  async getQuestionnaire(nctId: string, mode: "realtime" | "offline" = "realtime", forceRefresh = false): Promise<EligibilityQuestionnaireResponse> {
    const res = await fetch(`${BASE_URL}/api/trials/${encodeURIComponent(nctId)}/questionnaire?mode=${mode}${forceRefresh ? "&force_refresh=true" : ""}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // 5. Evaluate Patient Questionnaire Answers (Instant Verdict & Doctor Checklist)
  async evaluateEligibility(nctId: string, answers: { question_id: string; answer: "YES" | "NO" | "NOT_SURE" }[]): Promise<EligibilityEvaluationResponse> {
    const res = await fetch(`${BASE_URL}/api/trials/${encodeURIComponent(nctId)}/evaluate-eligibility`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nct_id: nctId, answers }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
};
```

---

## 📋 4. Patient Eligibility Screener API Specification

### Endpoint 1: `GET /api/trials/{nct_id}/questionnaire`
Generates 5 to 7 plain-language Yes/No questions in **6th–8th grade English** with patient context (`why_it_matters`).
- **Engine**: Powered in real-time by **Groq LPU (`qwen/qwen3.8-27b`)** with **~250ms latency**.
- **Failover Chain**: Groq LPU → OpenAI (`gpt-4o-mini`) → Offline Rule Generator.
- **Cache-Aside**: Results are cached in PostgreSQL for 30 days (`engine: "CACHE_HIT"`).

#### Query Parameters:
| Param | Type | Default | Description |
|:---|:---:|:---:|:---|
| `mode` | `string` | `"realtime"` | `"realtime"` (Groq LPU AI) or `"offline"` (Rule templates) |
| `force_refresh` | `boolean` | `false` | Bypasses PostgreSQL 30-day cache |

#### Response Schema (`EligibilityQuestionnaireResponse`):
```json
{
  "nct_id": "NCT05801029",
  "trial_title": "Study of Osimertinib and Amivantamab in Advanced NSCLC",
  "total_questions": 7,
  "engine": "GROQ",
  "questions": [
    {
      "id": "inc_0",
      "category": "INCLUSION",
      "question_text": "Do you have non-squamous non-small cell lung cancer?",
      "why_it_matters": "This study is designed specifically for this type of lung cancer.",
      "original_criterion": "Histologically or cytologically confirmed non-squamous NSCLC",
      "favorable_answer": "YES",
      "options": ["YES", "NO", "NOT_SURE"]
    },
    {
      "id": "exc_0",
      "category": "EXCLUSION",
      "question_text": "Do you have other serious health issues or a history of organ transplant?",
      "why_it_matters": "These conditions might make it unsafe for you to take part in this study.",
      "original_criterion": "History of other medical conditions or solid organ transplant",
      "favorable_answer": "NO",
      "options": ["YES", "NO", "NOT_SURE"]
    }
  ],
  "pre_answered_demographics": {
    "minimum_age": "18 Years",
    "maximum_age": "No Upper Limit",
    "sex_restriction": "ALL",
    "note": "Age and sex eligibility are pre-screened based on your profile."
  }
}
```

---

### Endpoint 2: `POST /api/trials/{nct_id}/evaluate-eligibility`
Evaluates patient responses (`YES`, `NO`, `NOT_SURE`) against protocol criteria rules and returns overall verdict, confidence score, itemized criterion checks, and an automated **Doctor Discussion Checklist**.

#### Request Payload:
```json
{
  "nct_id": "NCT05801029",
  "answers": [
    { "question_id": "inc_0", "answer": "YES" },
    { "question_id": "inc_1", "answer": "YES" },
    { "question_id": "exc_0", "answer": "NO" },
    { "question_id": "exc_1", "answer": "NOT_SURE" }
  ]
}
```

#### Response Schema (`EligibilityEvaluationResponse`):
```json
{
  "nct_id": "NCT05801029",
  "verdict": "LIKELY_ELIGIBLE",
  "score": 0.91,
  "summary": "Good news! You meet key trial criteria. Because 1 question requires confirmation from your doctor, we recommend sharing this study with your care team.",
  "criteria_evaluations": [
    {
      "criterion": "Do you have non-squamous non-small cell lung cancer?",
      "category": "INCLUSION",
      "status": "MET",
      "user_answer": "YES",
      "reason": "Your answer ('Yes') matches the criteria required for this trial."
    }
  ],
  "doctor_checklist": [
    "Bring your latest pathology and biopsy reports to your consultation.",
    "Provide your complete medication history and prior chemotherapy/immunotherapy records.",
    "Confirm with doctor: genetic or biomarker testing results"
  ]
}
```

---

### Endpoint 3: `GET /api/trials/{nct_id}/patient-summary`
Generates a compassionate, **6th–8th grade plain-English study summary** powered in real-time by **Groq LPU (~250ms)** with a dedicated **mini-glossary** translating all scientific, pharmaceutical, and healthcare jargon (e.g. *lebrikizumab*, *placebo*, *atopic dermatitis*, *biologics*).
- **Engine**: Dedicated **Groq LPU (`qwen/qwen3.8-27b`)** with **~250ms latency**.
- **Cache-Aside**: Results are cached in PostgreSQL for 30 days (`cached: true`, `engine: "CACHE_HIT"`).

#### Query Parameters:
| Param | Type | Default | Description |
|:---|:---:|:---:|:---|
| `force_refresh` | `boolean` | `false` | Bypasses PostgreSQL 30-day cache to re-generate via Groq LPU |

#### Response Schema (`PatientStudySummaryResponse`):
```json
{
  "nct_id": "NCT03443024",
  "trial_title": "A Study of Lebrikizumab in Participants With Moderate-to-Severe Atopic Dermatitis",
  "plain_title": "Testing a New Injection (Lebrikizumab) to Help Calm Down Severe Eczema",
  "what_this_study_is_about": "This study looks at whether a new medicine called lebrikizumab can help people with severe eczema feel better and have fewer flare-ups. We want to see if this new treatment is safe and works better than a sugar pill (placebo) that has no medicine in it.",
  "treatment_and_how_it_works": "Lebrikizumab is a type of medicine called a biologic. It works by targeting specific proteins in your body that cause inflammation, which is the swelling and redness you feel during an eczema flare-up. By blocking these proteins, the medicine helps calm your immune system so it stops attacking your skin as aggressively.",
  "what_participation_involves": "If you join this study, you will visit the clinic regularly for check-ups. You will receive an injection of either the new medicine or a placebo at scheduled times. Doctors will do blood tests and examine your skin to track progress.",
  "who_can_join_overview": "Doctors are looking for men and women 18 years or older who have had moderate to severe eczema for at least one year.",
  "complex_terms_explained": [
    {
      "term": "Atopic Dermatitis",
      "plain_english": "This is the medical name for eczema, a condition that makes your skin red, itchy, and dry."
    },
    {
      "term": "Lebrikizumab",
      "plain_english": "This is the new medicine being tested in this study to help reduce eczema symptoms."
    },
    {
      "term": "Placebo",
      "plain_english": "This is a fake treatment, like a sugar pill or shot with no medicine, used to compare against the real drug."
    },
    {
      "term": "Biological",
      "plain_english": "A type of targeted medicine made from living cells that helps change how specific immune proteins work."
    }
  ],
  "engine": "GROQ",
  "cached": false,
  "execution_time_ms": 248
}
```

---

## 🎨 5. Reference Working Implementation

The frontend team can reference the working UI code in this repository:
- HTML Layout & Wizard Modal: [`trialgpt_lite/ui/index.html`](file:///Users/deepak/projects/trailgpt/trialgpt_lite/ui/index.html)
- Client Logic, Wizard State Machine & Navigation: [`trialgpt_lite/ui/app.js`](file:///Users/deepak/projects/trailgpt/trialgpt_lite/ui/app.js)
- CSS Tokens, Wizard Animations & Dark/Light Styling: [`trialgpt_lite/ui/style.css`](file:///Users/deepak/projects/trailgpt/trialgpt_lite/ui/style.css)

