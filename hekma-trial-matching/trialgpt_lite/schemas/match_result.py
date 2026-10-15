"""
Pydantic data models for evaluation outputs, verdicts, and match reports.
Provides explicit fields for primary outputs and deep-dive protocol sections.
"""

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field

from trialgpt_lite.schemas.study import (
    ContactsAndLocations,
    StudyLocation,
    DemographicCriteria,
    InterventionItem,
    ParsedCriteria,
    StudyDesign,
    StudyEnrollment,
    StudyTimeline,
    StudyOutcome,
)



class CriterionVerdict(str, Enum):
    # Inclusion outcomes
    INCLUDED = "included"
    NOT_INCLUDED = "not included"
    
    # Exclusion outcomes
    NOT_EXCLUDED = "not excluded"
    EXCLUDED = "excluded"
    
    # Shared outcomes
    NOT_ENOUGH_INFO = "not enough information"
    NOT_APPLICABLE = "not applicable"


class OverallEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    LIKELY_ELIGIBLE = "LIKELY_ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNCERTAIN = "UNCERTAIN"
    FILTERED_OUT = "FILTERED_OUT"
    RETRIEVED_ONLY = "RETRIEVED_ONLY"


class CriterionEvaluation(BaseModel):
    """Detailed evaluation result for a single inclusion or exclusion criterion."""
    criterion_index: int = Field(..., description="0-indexed criterion number.")
    criterion_type: str = Field(..., description="'inclusion' or 'exclusion'.")
    criterion_text: str = Field(..., description="Text of the criterion.")
    reasoning: str = Field(..., description="Clinical reasoning justification.")
    sentence_ids: list[int] = Field(default_factory=list, description="Referenced sentence IDs from patient note.")
    label: str = Field(..., description="Verdict label (e.g. included, excluded, not enough information).")


class FastFilterResult(BaseModel):
    """Outcome of Level 1 fast heuristic pre-screening."""
    passed: bool = Field(default=True, description="Whether study passed demographic and status filters.")
    reasons: list[str] = Field(default_factory=list, description="Exclusion reasons if failed.")


class TrialMatchResult(BaseModel):
    """
    Full matching evaluation for a single clinical trial.
    Contains both top-level summary output fields and detailed multi-section protocol data.
    """
    # --- 1. Primary Output Fields ---
    nct_id: str = Field(..., description="NCT ID, e.g. NCT05801029.")
    title: str = Field(..., description="Trial title.")
    conditions: list[str] = Field(default_factory=list, description="Conditions / diseases.")
    overall_status: str = Field(default="UNKNOWN", description="Recruitment status (e.g. RECRUITING).")
    phases: list[str] = Field(default_factory=list, description="Study phase (e.g. PHASE2).")
    study_type: str = Field(default="INTERVENTIONAL", description="Study type (e.g. INTERVENTIONAL, OBSERVATIONAL).")
    interventions: list[str] = Field(default_factory=list, description="Intervention names and summaries.")
    age_display: str = Field(default="All Ages", description="Formatted age requirement (e.g. '≥ 18 Years').")
    sex_display: str = Field(default="All / Both", description="Formatted sex restriction (e.g. 'Female Only', 'Both Sexes').")
    location_display: str = Field(default="Location not listed", description="Primary facility / city / country summary.")
    verdict: OverallEligibility = Field(default=OverallEligibility.RETRIEVED_ONLY, description="Match status verdict.")
    summary_reasoning: str = Field(default="", description="Reasons for match, likelihood, or disqualification.")
    eligibility_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score 0.0 to 1.0.")
    web_url: str = Field(default="", description="ClinicalTrials.gov NCT direct link.")

    # --- 2. Detailed Protocol Information (for 'More Details' View) ---
    brief_summary: Optional[str] = Field(default=None, description="Overview: Brief summary.")
    detailed_interventions: list[InterventionItem] = Field(default_factory=list, description="Treatment: Detailed interventions.")
    criteria_evaluations: list[CriterionEvaluation] = Field(default_factory=list, description="Eligibility: Evaluated inclusion/exclusion criteria when a patient note is provided.")
    participation_criteria: ParsedCriteria = Field(default_factory=ParsedCriteria, description="Protocol Participation Criteria (inclusion/exclusion) from ClinicalTrials.gov, always populated.")
    demographics: DemographicCriteria = Field(default_factory=DemographicCriteria, description="Age/Sex: Full demographic eligibility.")
    design: Optional[StudyDesign] = Field(default=None, description="Study Design: Allocation, masking, model, purpose.")
    enrollment: Optional[StudyEnrollment] = Field(default=None, description="Enrollment: Target participant count & type.")
    lead_sponsor: Optional[str] = Field(default=None, description="Sponsor: Lead sponsor organization.")
    collaborators: list[str] = Field(default_factory=list, description="Sponsor: Collaborating institutions.")
    locations: list[StudyLocation] = Field(default_factory=list, description="Locations: All site facilities/cities/countries.")
    timeline: Optional[StudyTimeline] = Field(default=None, description="Timeline: Key dates (start, completion).")
    primary_outcomes: list[StudyOutcome] = Field(default_factory=list, description="Outcomes: Primary clinical outcomes.")
    secondary_outcomes: list[StudyOutcome] = Field(default_factory=list, description="Outcomes: Secondary clinical outcomes.")
    contacts: ContactsAndLocations = Field(default_factory=ContactsAndLocations, description="Contact: Central contacts and officials.")
    fast_filter: FastFilterResult = Field(default_factory=FastFilterResult)


class ConditionMatchReport(BaseModel):
    """Aggregated response returned to caller for a condition search and match query."""
    searched_condition: str
    total_trials_in_registry: int = Field(default=0, description="Total matching trials in ClinicalTrials.gov.")
    retrieved_trials_count: int = Field(default=0, description="Number of trials fetched in this page.")
    evaluated_trials_count: int = Field(default=0, description="Number of trials with criteria evaluation.")
    page_size: int = Field(default=10, description="Number of trials requested per page.")
    current_page_token: Optional[str] = Field(default=None, description="Page token used to retrieve this page (None for first page).")
    next_page_token: Optional[str] = Field(default=None, description="Token to fetch next page.")
    trials: list[TrialMatchResult] = Field(default_factory=list)
    cache_hit: bool = Field(default=False, description="Whether results were served from PostgreSQL Cache-Aside store.")
    execution_time_seconds: float = Field(default=0.0)


class EligibilityQuestion(BaseModel):
    """Patient-friendly eligibility question transformed from study criteria."""
    id: str = Field(..., description="Unique question identifier.")
    category: str = Field(..., description="'INCLUSION' or 'EXCLUSION'.")
    question_text: str = Field(..., description="Clear plain-language question in 6th-8th grade English.")
    why_it_matters: str = Field(default="", description="Compassionate, plain-English explanation of why the medical team checks this.")
    original_criterion: str = Field(default="", description="Original clinical criterion text from protocol.")
    favorable_answer: str = Field(..., description="Eligible answer: 'YES' or 'NO'.")
    options: list[str] = Field(default_factory=lambda: ["YES", "NO", "NOT_SURE"], description="Available answer choices.")


class EligibilityQuestionnaireResponse(BaseModel):
    """Questionnaire generated for a clinical trial for 'See if I'm Eligible'."""
    nct_id: str = Field(..., description="ClinicalTrials.gov NCT identifier.")
    trial_title: str = Field(..., description="Official or brief study title.")
    total_questions: int = Field(default=0, description="Total number of prioritized questions.")
    questions: list[EligibilityQuestion] = Field(default_factory=list, description="List of generated questions.")
    engine: str = Field(default="GROQ", description="Engine used: GROQ, OPENAI, OFFLINE_RULE_FALLBACK, or CACHE_HIT.")
    pre_answered_demographics: dict[str, Any] = Field(
        default_factory=dict,
        description="Pre-verified age and sex bounds so patient is not asked again.",
    )


class CriterionEvaluationItem(BaseModel):
    """Single criterion evaluation outcome from questionnaire response."""
    criterion: str = Field(..., description="Criterion or question text.")
    category: str = Field(..., description="'INCLUSION' or 'EXCLUSION'.")
    status: str = Field(..., description="Status verdict: 'MET', 'UNMET', or 'UNCERTAIN'.")
    user_answer: str = Field(..., description="Patient answer choice ('YES', 'NO', 'NOT_SURE').")
    reason: str = Field(..., description="Clinical explanation of why this answers satisfies or violates protocol.")


class EligibilityEvaluationResponse(BaseModel):
    """Result of evaluating patient questionnaire answers against study protocol."""
    nct_id: str = Field(..., description="ClinicalTrials.gov NCT identifier.")
    verdict: OverallEligibility = Field(..., description="Overall verdict (ELIGIBLE, INELIGIBLE, UNCERTAIN).")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Match confidence score between 0.0 and 1.0.")
    summary: str = Field(..., description="Patient-facing summary explanation.")
    criteria_evaluations: list[CriterionEvaluationItem] = Field(default_factory=list, description="Itemized criterion verdicts.")
    doctor_checklist: list[str] = Field(default_factory=list, description="Checklist items to discuss with doctor / oncologist.")
    criteria_match_percentage: int = Field(default=0, ge=0, le=100, description="Percentage of individual evaluated criteria satisfied.")
    criteria_met_count: int = Field(default=0, ge=0, description="Count of criteria evaluated as MET.")
    cohort_qualified: Optional[str] = Field(default=None, description="Specific study cohort/arm qualified under, if multi-arm.")


class TermExplanation(BaseModel):
    """Plain-English translation of a scientific, medical, or drug term."""
    term: str = Field(..., description="Scientific or pharmaceutical term (e.g. 'Lebrikizumab', 'Placebo', 'Atopic Dermatitis').")
    plain_english: str = Field(..., description="Simple conversational 1-sentence explanation of what this is in everyday words.")


class PatientStudySummaryResponse(BaseModel):
    """Patient-friendly plain-English summary of a clinical trial generated via Groq LPU."""
    nct_id: str = Field(..., description="ClinicalTrials.gov NCT identifier.")
    trial_title: str = Field(..., description="Official or brief trial title.")
    plain_title: str = Field(..., description="Simple conversational 1-sentence title (6th-8th grade level).")
    what_this_study_is_about: str = Field(..., description="Plain-English explanation of what doctors are researching (2-3 sentences).")
    treatment_and_how_it_works: str = Field(..., description="Everyday explanation of the study medicine or intervention and how it works in the body.")
    what_participation_involves: str = Field(..., description="Everyday explanation of clinic visits, check-ups, pills/injections, and timeline.")
    who_can_join_overview: str = Field(..., description="Conversational overview of who the doctors are looking for.")
    plain_inclusions: list[str] = Field(default_factory=list, description="Key participation requirements to join in simple plain English.")
    plain_exclusions: list[str] = Field(default_factory=list, description="Key safety rules or conditions that prevent joining in simple plain English.")
    complex_terms_explained: list[TermExplanation] = Field(default_factory=list, description="Mini-glossary explaining any scientific/drug/medical terms.")
    engine: str = Field(default="GROQ", description="Inference engine used: GROQ or CACHE_HIT.")
    cached: bool = Field(default=False, description="Whether this summary was served from PostgreSQL Cache-Aside store.")
    execution_time_ms: int = Field(default=0, description="Generation latency in milliseconds.")

