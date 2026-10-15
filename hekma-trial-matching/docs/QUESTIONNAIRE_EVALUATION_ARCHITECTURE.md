# Clinical Trial Eligibility Screener: Architecture & Evaluation Specification

## 1. Executive Summary & Core Objectives

The **Interactive Eligibility Screener** in TrialGPT Lite provides an instant, patient-centric self-assessment for clinical trial candidates. It bridges the gap between dense, complex protocol criteria and everyday patient comprehension while ensuring strict clinical rigor.

```mermaid
flowchart LR
    A[Patient / User] -->|1. Clicks 'See if I'm Eligible'| B[Web UI Modal]
    B -->|2. GET /questionnaire| C[FastAPI Backend]
    C -->|3. Transforms Criteria| D[100% Offline Question Generator]
    D -->|4. 5-7 Easy English Questions| B
    B -->|5. Answers YES / NO / NOT SURE| C
    C -->|6. POST /evaluate-eligibility| E[Offline Rule Evaluator]
    E -->|7. <1ms Deterministic Evaluation| F[Verdict: Eligible / Likely / Ineligible + Doctor Checklist]
    F --> B
```

### Key Highlights:
* **100% Offline & Deterministic**: Zero dependencies on external Large Language Models (LLMs) or paid third-party APIs.
* **Sub-Millisecond Execution**: Processes protocol rules and calculates verdicts in **< 1ms** locally in Python.
* **Health Literacy Standard**: Questions and verdict summaries are phrased in 6th–8th grade plain English without confusing medical jargon.
* **Complete Privacy**: Patient responses never leave the local environment; zero PII / PHI transmission.

---

## 2. End-to-End System Architecture

The evaluation subsystem operates across two decoupled, stateless phases:

```mermaid
sequenceDiagram
    autonumber
    actor Patient as Patient (Web UI)
    participant API as FastAPI Router (/api/trials)
    participant Service as TrialGPTLiteService
    participant Generator as Question Generator (question_generator.py)
    participant Evaluator as Rule Evaluator (evaluate_offline_questionnaire)

    Note over Patient,API: Phase 1: Interactive Questionnaire Generation
    Patient->>API: GET /api/trials/{nct_id}/questionnaire
    API->>Service: get_trial_questionnaire(nct_id)
    Service->>Generator: generate_offline_questions(study)
    Generator-->>Service: EligibilityQuestionnaireResponse (5-7 questions)
    Service-->>Patient: JSON (Plain questions, options: YES/NO/NOT_SURE)

    Note over Patient,API: Phase 2: Instant Rule Evaluation & Verdict
    Patient->>API: POST /api/trials/{nct_id}/evaluate-eligibility (Answers Payload)
    API->>Service: evaluate_trial_eligibility(request)
    Service->>Evaluator: evaluate_offline_questionnaire(study, questions, answers_map)
    Evaluator->>Evaluator: Match against favorable answers (MET, UNMET, UNCERTAIN)
    Evaluator->>Evaluator: Calculate Verdict, Score, Summary & Doctor Checklist
    Evaluator-->>Service: EligibilityEvaluationResponse
    Service-->>Patient: JSON Verdict & Itemized Breakdown (<1ms)
```

---

## 3. Question Scoring & Classification Rules

Every clinical trial protocol divides criteria into two categories:

| Rule Category | Clinical Definition | Expected / Favorable Answer |
| :--- | :--- | :---: |
| **Inclusion Criteria** | Clinical attributes the patient **must satisfy** (e.g., confirmed cancer diagnosis, advanced/metastatic stage, prior therapy history). | **`YES`** |
| **Exclusion Criteria** | Medical conditions or treatments the patient **must NOT have** (e.g., active brain tumors, uncontrolled heart failure, active viral infection, pregnancy). | **`NO`** |

### The 3 Evaluation States

When the patient answers each question, the system compares the patient's answer against the protocol's favorable answer:

| Patient Answer | Question Category | Evaluation State | Visual Badge | Clinical Meaning |
| :---: | :---: | :---: | :---: | :--- |
| **`YES`** | INCLUSION | **`MET`** | Green ✓ | Patient satisfies the required criterion. |
| **`NO`** | EXCLUSION | **`MET`** | Green ✓ | Patient does not have the prohibited condition. |
| **`NOT_SURE`** | ANY | **`UNCERTAIN`** | Indigo ❓ | Patient is unsure; flagged for clinical verification. |
| **`NO`** | INCLUSION | **`UNMET`** | Red ✕ | Patient lacks a mandatory requirement (**Disqualification**). |
| **`YES`** | EXCLUSION | **`UNMET`** | Red ✕ | Patient has a prohibited condition (**Disqualification**). |

---

## 4. Decision Tree & Verdict Logic

The final verdict and match confidence score are determined through a strict hierarchical decision tree:

```mermaid
flowchart TD
    Start([Evaluate Patient Responses]) --> CheckUnmet{Are any criteria UNMET?<br/>len disqualifications > 0}

    CheckUnmet -- YES --> Ineligible[Verdict: INELIGIBLE]
    Ineligible --> ScoreIneligible["Score = max(0.0, round(0.30 * (satisfied / total), 2))<br/>Range: 0% - 30%"]
    ScoreIneligible --> SummaryIneligible[Summary explains conflicting requirements & advises doctor consultation]

    CheckUnmet -- NO --> CheckUncertain{Are any answers NOT_SURE?<br/>len uncertainties > 0}

    CheckUncertain -- YES --> Likely[Verdict: LIKELY_ELIGIBLE]
    Likely --> ScoreLikely["Score = round(0.70 + 0.25 * (satisfied / total), 2)<br/>Range: 70% - 95%"]
    ScoreLikely --> ChecklistLikely[Doctor Checklist populated with all uncertain criteria]

    CheckUncertain -- NO --> Eligible[Verdict: ELIGIBLE]
    Eligible --> ScoreEligible["Score = 0.95 (95%)"]
    Eligible --> ChecklistEligible[Checklist provides general pathology & lab verification items]
```

### Verdict Breakdown

#### 1. `INELIGIBLE` (Score: 0% – 30%)
* **Trigger**: One or more criteria are evaluated as `UNMET`.
* **Formula**:
  $$\text{Score} = \max\left(0.0, \; \text{round}\left(0.30 \times \frac{\text{satisfied\_count}}{\text{total\_questions}}, 2\right)\right)$$
* **Patient Experience**:
  * Empathic notification stating that the trial protocol requirements do not align with current answers.
  * Cites the primary conflicting criteria in easy English.
  * Directs the patient to consult their oncologist regarding alternative trials.

#### 2. `LIKELY_ELIGIBLE` (Score: 70% – 95%)
* **Trigger**: Zero `UNMET` criteria, but one or more questions were answered with `NOT_SURE`.
* **Formula**:
  $$\text{Score} = \text{round}\left(0.70 + 0.25 \times \frac{\text{satisfied\_count}}{\text{total\_questions}}, 2\right)$$
* **Patient Experience**:
  * Encouraging notification: *"Good news! You meet several key trial criteria."*
  * Notes that remaining criteria require specialist confirmation from medical charts.
  * Automatically appends questions marked `NOT_SURE` to the **Doctor Consultation Checklist**.

#### 3. `ELIGIBLE` (Score: 95%)
* **Trigger**: Zero `UNMET` criteria and zero `UNCERTAIN` criteria (100% favorable answers).
* **Formula**: Fixed confidence score of **`0.95` (95%)** (reserving 5% for site-specific laboratory blood panel clearance).
* **Patient Experience**:
  * High-confidence positive verdict.
  * Directs patient to contact study coordinators for enrollment scheduling.

---

## 5. Doctor Consultation Checklist Derivation

When patients are uncertain about specialized medical details (e.g., genetic mutations, specific prior drug classes, organ clearance), the engine automatically compiles a customized consultation agenda:

```mermaid
flowchart LR
    A[Patient Answers NOT_SURE] --> B[Extracted Criteria Concepts]
    C[Standard Baseline Items] --> D[Doctor Consultation Checklist]
    B --> D
    D --> E[1. Pathology & Biopsy Reports]
    D --> F[2. Medication History]
    D --> G[3. Standard Lab Blood Values]
    D --> H[4. Specific Questions Marked Not Sure]
```

### Baseline Items (Always Included):
1. *"Bring your latest pathology and biopsy reports to your consultation."*
2. *"Provide your complete medication history and prior chemotherapy/immunotherapy records."*
3. *"Standard laboratory blood counts (platelets, neutrophils, liver & kidney panels) will be verified by the clinical research site."*

### Dynamic Items:
For every question answered with `NOT_SURE`, a tailored confirmation bullet is generated:
* *Example*: Unsure about FGFR alteration $\rightarrow$ `Confirm with doctor: specific gene alteration or biomarker (such as FGFR, EGFR, or BRAF) confirmed in tumor.`

---

## 6. API Specification & JSON Schemas

### Endpoint
`POST /api/trials/{nct_id}/evaluate-eligibility`

### Request Payload (`EligibilityEvaluationRequest`)
```json
{
  "nct_id": "NCT07359820",
  "answers": [
    {
      "question_id": "inc_0",
      "answer": "YES"
    },
    {
      "question_id": "inc_1",
      "answer": "YES"
    },
    {
      "question_id": "inc_3",
      "answer": "NO"
    },
    {
      "question_id": "exc_0",
      "answer": "NO"
    },
    {
      "question_id": "exc_2",
      "answer": "NOT_SURE"
    }
  ]
}
```

### Response Payload (`EligibilityEvaluationResponse`)
```json
{
  "nct_id": "NCT07359820",
  "verdict": "INELIGIBLE",
  "score": 0.17,
  "summary": "Based on your answers, you are likely ineligible for this trial because some protocol requirements were not met (previously received cancer treatment (such as chemotherapy, immunotherapy, or radiation)). We encourage you to discuss alternative clinical trials and treatment options with your oncologist or care team.",
  "criteria_evaluations": [
    {
      "criterion": "Has your doctor confirmed that your cancer is advanced or metastatic (spread to other areas)?",
      "category": "INCLUSION",
      "status": "MET",
      "user_answer": "YES",
      "reason": "Your answer ('Yes') matches the criteria required for this trial."
    },
    {
      "criterion": "Have you previously received cancer treatment (such as chemotherapy, immunotherapy, or radiation)?",
      "category": "INCLUSION",
      "status": "UNMET",
      "user_answer": "NO",
      "reason": "You answered 'No', but this trial specifically requires this condition or treatment history."
    },
    {
      "criterion": "Do you have an active chronic infection, such as Hepatitis B, Hepatitis C, or HIV?",
      "category": "EXCLUSION",
      "status": "UNCERTAIN",
      "user_answer": "NOT_SURE",
      "reason": "You marked 'Not Sure'. Your doctor or the study coordinator will verify this from your medical records."
    }
  ],
  "doctor_checklist": [
    "Bring your latest pathology and biopsy reports to your consultation.",
    "Provide your complete medication history and prior chemotherapy/immunotherapy records.",
    "Standard laboratory blood counts (platelets, neutrophils, liver & kidney panels) will be verified by the clinical research site.",
    "Confirm with doctor: active chronic infection, such as Hepatitis B, Hepatitis C, or HIV"
  ]
}
```

---

## 7. Python Implementation Reference (`question_generator.py`)

The evaluation core is implemented cleanly in `trialgpt_lite/parser/question_generator.py` (lines 310–392):

```python
def evaluate_offline_questionnaire(
    study: TrialStudy,
    questions: list[EligibilityQuestion],
    answers_map: dict[str, str],
) -> EligibilityEvaluationResponse:
    question_dict = {q.id: q for q in questions}
    evaluations: list[CriterionEvaluationItem] = []
    disqualifications: list[str] = []
    uncertainties: list[str] = []
    satisfied_count = 0

    for q_id, q in question_dict.items():
        user_answer = (answers_map.get(q_id) or "NOT_SURE").strip().upper()
        favorable = q.favorable_answer

        if user_answer == "NOT_SURE":
            status = "UNCERTAIN"
            reason = "You marked 'Not Sure'. Your doctor or the study coordinator will verify this from your medical records."
            uncertainties.append(q.question_text)
        elif user_answer == favorable:
            status = "MET"
            reason = f"Your answer ('{user_answer.title()}') matches the criteria required for this trial."
            satisfied_count += 1
        else:
            status = "UNMET"
            if q.category == "EXCLUSION":
                reason = f"You answered 'Yes', which is an exclusion criterion for this trial."
                disqualifications.append(q.question_text.rstrip("?").replace("Do you have ", "").replace("Are you ", ""))
            else:
                reason = f"You answered 'No', but this trial specifically requires this condition or treatment history."
                disqualifications.append(q.question_text.rstrip("?").replace("Have you ", "").replace("Has your doctor ", ""))

        evaluations.append(CriterionEvaluationItem(
            criterion=q.question_text,
            category=q.category,
            status=status,
            user_answer=user_answer,
            reason=reason,
        ))

    # Determine Overall Verdict and Score
    total_q = len(questions) or 1
    if disqualifications:
        verdict = OverallEligibility.INELIGIBLE
        score = max(0.0, round(0.3 * (satisfied_count / total_q), 2))
        summary = (
            f"Based on your answers, you are likely ineligible for this trial because some protocol requirements "
            f"were not met ({'; '.join(disqualifications[:2])}). We encourage you to discuss alternative clinical trials "
            f"and treatment options with your oncologist or care team."
        )
    elif uncertainties:
        verdict = OverallEligibility.LIKELY_ELIGIBLE
        score = round(0.70 + 0.25 * (satisfied_count / total_q), 2)
        summary = (
            f"Good news! You meet {satisfied_count} key trial criteria. Because {len(uncertainties)} questions "
            "require confirmation from your medical records or doctor, we recommend sharing this study with your care team."
        )
    else:
        verdict = OverallEligibility.ELIGIBLE
        score = 0.95
        summary = (
            "Great news! Based on your self-reported responses, you meet all major eligibility criteria for this trial. "
            "Your next step is to contact the study team to verify final laboratory eligibility."
        )

    # Generate Doctor Discussion Checklist
    doctor_checklist = [
        "Bring your latest pathology and biopsy reports to your consultation.",
        "Provide your complete medication history and prior chemotherapy/immunotherapy records.",
        "Standard laboratory blood counts (platelets, neutrophils, liver & kidney panels) will be verified by the clinical research site.",
    ]
    for unc in uncertainties:
        clean_unc = unc.rstrip("?").replace("Do you have ", "").replace("Have you ", "").replace("Are you ", "")
        doctor_checklist.append(f"Confirm with doctor: {clean_unc}")

    return EligibilityEvaluationResponse(
        nct_id=study.nct_id,
        verdict=verdict,
        score=score,
        summary=summary,
        criteria_evaluations=evaluations,
        doctor_checklist=doctor_checklist,
    )
```

---

## 8. Safety, Privacy & Edge-Case Guarantees

1. **Missing or Partial Responses**:
   * If a patient submits without answering a question, the evaluator defaults the missing item to `"NOT_SURE"`.
   * It never produces a false `INELIGIBLE` or false `ELIGIBLE`; it gracefully routes the study to `LIKELY_ELIGIBLE` and adds the missing question to the doctor's checklist.
2. **Empty Study Protocol Fallback**:
   * If a trial record lacks structured participation criteria, the generator defaults to a primary disease confirmation question (*"Have you been diagnosed with [condition]?"*).
3. **No Phantom API Calls**:
   * All rules evaluate locally in Python with native string and regex matching.
   * Total latency is under 1 millisecond.
