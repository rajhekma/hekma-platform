"""
Fast Level 1 Heuristic and Demographic Pre-Filter.
Filters out studies that conclusively do not match patient demographics or study status,
saving LLM compute and latency.
"""

from typing import Optional
from trialgpt_lite.schemas.study import TrialStudy
from trialgpt_lite.schemas.request import PatientProfile
from trialgpt_lite.schemas.match_result import FastFilterResult


def evaluate_fast_filter(
    study: TrialStudy,
    patient: Optional[PatientProfile] = None,
    recruiting_only: bool = True,
    allowed_statuses: Optional[list[str]] = None,
) -> FastFilterResult:
    """
    Checks if a trial passes preliminary status and demographic requirements.
    """
    reasons: list[str] = []

    # 1. Overall Status Check
    status = (study.overall_status or "").upper()
    if recruiting_only:
        active_statuses = ["RECRUITING", "ENROLLING_BY_INVITATION", "ACTIVE_NOT_RECRUITING"]
        if status not in active_statuses:
            reasons.append(f"Status '{status}' is not recruiting/active.")
    elif allowed_statuses:
        allowed_upper = [s.upper() for s in allowed_statuses]
        if status not in allowed_upper:
            reasons.append(f"Status '{status}' not in allowed statuses ({', '.join(allowed_statuses)}).")

    # If no patient demographics provided, return status verdict
    if not patient:
        return FastFilterResult(passed=(len(reasons) == 0), reasons=reasons)

    # 2. Biological Sex Filter
    demographics = study.demographics
    if patient.sex and demographics.sex != "ALL":
        patient_sex = patient.sex.strip().upper()
        if patient_sex != demographics.sex:
            reasons.append(
                f"Sex mismatch: Patient is {patient_sex}, study requires {demographics.sex}."
            )

    # 3. Age Restrictions Filter
    if patient.age is not None:
        p_age = float(patient.age)
        if demographics.minimum_age_years is not None and p_age < demographics.minimum_age_years:
            reasons.append(
                f"Age below minimum: Patient is {p_age}y, minimum required is {demographics.minimum_age_years}y."
            )
        if demographics.maximum_age_years is not None and p_age > demographics.maximum_age_years:
            reasons.append(
                f"Age exceeds maximum: Patient is {p_age}y, maximum allowed is {demographics.maximum_age_years}y."
            )

    return FastFilterResult(passed=(len(reasons) == 0), reasons=reasons)
