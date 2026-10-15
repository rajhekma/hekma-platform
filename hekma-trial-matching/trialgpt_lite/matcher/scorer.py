"""
Eligibility scorer and verdict aggregator.
Combines fast filter outcomes and criterion-level rule evaluations into an overall verdict,
confidence score, and detailed protocol output models.
"""

from typing import Optional
from trialgpt_lite.schemas.match_result import (
    OverallEligibility,
    CriterionEvaluation,
    FastFilterResult,
    TrialMatchResult,
)
from trialgpt_lite.schemas.study import TrialStudy


def _format_age_display(study: TrialStudy) -> str:
    """Formats demographic age constraints into human-readable label."""
    d = study.demographics
    if d.minimum_age_years is not None and d.maximum_age_years is not None:
        return f"{d.minimum_age_years:g} to {d.maximum_age_years:g} Years"
    elif d.minimum_age_years is not None:
        return f"≥ {d.minimum_age_years:g} Years"
    elif d.maximum_age_years is not None:
        return f"≤ {d.maximum_age_years:g} Years"
    elif d.minimum_age_text:
        return d.minimum_age_text
    return "All Ages"


def _format_sex_display(study: TrialStudy) -> str:
    """Formats biological sex restrictions."""
    s = (study.demographics.sex or "ALL").upper()
    if s == "FEMALE":
        return "Female Only"
    elif s == "MALE":
        return "Male Only"
    return "All / Both"


def _format_location_display(study: TrialStudy) -> str:
    """Creates a concise summary of primary clinical facility and site count."""
    locs = study.contacts.locations
    if not locs:
        return "Locations not listed"
    
    first = locs[0]
    parts = []
    if first.facility:
        parts.append(first.facility)
    if first.city:
        parts.append(first.city)
    if first.country and first.country not in parts:
        parts.append(first.country)
        
    main_loc = ", ".join(parts) if parts else "Clinical Site"
    if len(locs) > 1:
        return f"{main_loc} (+{len(locs) - 1} more sites)"
    return main_loc


def score_and_aggregate_trial(
    study: TrialStudy,
    fast_filter: FastFilterResult,
    evaluations: list[CriterionEvaluation],
    has_patient_context: bool,
) -> TrialMatchResult:
    """
    Computes overall eligibility status, score (0.0 - 1.0), clinical reasoning summary,
    and populates all primary and detailed protocol fields.
    """
    age_str = _format_age_display(study)
    sex_str = _format_sex_display(study)
    loc_str = _format_location_display(study)

    base_result = TrialMatchResult(
        # 1. Primary Output Fields
        nct_id=study.nct_id,
        title=study.brief_title,
        conditions=study.conditions,
        overall_status=study.overall_status,
        phases=study.phases,
        study_type=study.study_type or "INTERVENTIONAL",
        interventions=study.interventions,
        age_display=age_str,
        sex_display=sex_str,
        location_display=loc_str,
        web_url=study.web_url,
        fast_filter=fast_filter,
        criteria_evaluations=evaluations,
        participation_criteria=study.criteria,

        # 2. Detailed Multi-Section Protocol Fields
        brief_summary=study.brief_summary,
        detailed_interventions=study.detailed_interventions,
        demographics=study.demographics,
        design=study.design,
        enrollment=study.enrollment,
        lead_sponsor=study.lead_sponsor,
        collaborators=study.collaborators,
        locations=study.contacts.locations,
        timeline=study.timeline,
        primary_outcomes=study.primary_outcomes,
        secondary_outcomes=study.secondary_outcomes,
        contacts=study.contacts,
    )

    # Case 1: Fast demographic / status filter failed
    if not fast_filter.passed:
        base_result.verdict = OverallEligibility.FILTERED_OUT
        base_result.eligibility_score = 0.0
        base_result.summary_reasoning = f"Filtered out in pre-screening: {'; '.join(fast_filter.reasons)}"
        return base_result

    # Case 2: Condition-only search (no patient profile supplied)
    if not has_patient_context or not evaluations:
        base_result.verdict = OverallEligibility.RETRIEVED_ONLY
        status_scores = {
            "RECRUITING": 1.0,
            "ENROLLING_BY_INVITATION": 0.9,
            "ACTIVE_NOT_RECRUITING": 0.75,
            "NOT_YET_RECRUITING": 0.6,
        }
        base_result.eligibility_score = status_scores.get(study.overall_status.upper(), 0.5)
        base_result.summary_reasoning = (
            f"Study retrieved for condition. Status is '{study.overall_status}'. "
            "Provide patient clinical note for criterion-level eligibility scoring."
        )
        return base_result

    # Case 3: Criterion-level evaluations available
    inc_evals = [e for e in evaluations if e.criterion_type == "inclusion"]
    exc_evals = [e for e in evaluations if e.criterion_type == "exclusion"]

    disqualified_by_exclusion = [e for e in exc_evals if e.label == "excluded"]
    disqualified_by_inclusion = [e for e in inc_evals if e.label == "not included"]

    # Definite ineligibility
    if disqualified_by_exclusion or disqualified_by_inclusion:
        base_result.verdict = OverallEligibility.INELIGIBLE
        base_result.eligibility_score = 0.05
        disqualifiers = []
        if disqualified_by_exclusion:
            disqualifiers.append(f"Triggered {len(disqualified_by_exclusion)} exclusion criteria")
        if disqualified_by_inclusion:
            disqualifiers.append(f"Failed {len(disqualified_by_inclusion)} inclusion criteria")
        base_result.summary_reasoning = (
            f"Patient is ineligible: {', '.join(disqualifiers)}. "
            f"Primary reason: {(disqualified_by_exclusion or disqualified_by_inclusion)[0].reasoning}"
        )
        return base_result

    # Tally inclusion metrics
    inc_included = len([e for e in inc_evals if e.label == "included"])
    inc_info_needed = len([e for e in inc_evals if e.label == "not enough information"])
    inc_total_relevant = inc_included + inc_info_needed

    # Check for complete eligibility
    if inc_info_needed == 0 and inc_included > 0:
        base_result.verdict = OverallEligibility.ELIGIBLE
        base_result.eligibility_score = 0.98
        base_result.summary_reasoning = (
            f"Patient satisfies all {inc_included} evaluated inclusion criteria with no exclusion contraindications."
        )
        return base_result

    # Likely eligible or pending info
    if inc_included > 0:
        base_result.verdict = OverallEligibility.LIKELY_ELIGIBLE
        # Score proportional to confirmed criteria ratio
        ratio = inc_included / max(1, inc_total_relevant)
        base_result.eligibility_score = round(0.55 + 0.35 * ratio, 2)
        base_result.summary_reasoning = (
            f"Likely eligible: {inc_included} inclusion criteria confirmed; "
            f"{inc_info_needed} criteria require additional clinical data."
        )
    else:
        base_result.verdict = OverallEligibility.UNCERTAIN
        base_result.eligibility_score = 0.40
        base_result.summary_reasoning = (
            "Patient status uncertain: Key criteria require specific clinical documentation not present in note."
        )

    return base_result
