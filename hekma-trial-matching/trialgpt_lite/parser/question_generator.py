"""
100% Offline Clinical Trial Eligibility Question Generator and Evaluator.
Transforms parsed inclusion/exclusion criteria into patient-friendly, easy English Yes/No questions.
Zero external LLMs, zero API keys, execution time < 1ms.
"""

import re
from typing import Any
from trialgpt_lite.schemas.study import TrialStudy
from trialgpt_lite.schemas.match_result import (
    EligibilityQuestion,
    EligibilityQuestionnaireResponse,
    EligibilityEvaluationResponse,
    CriterionEvaluationItem,
    OverallEligibility,
)

# 1. Regex to skip technical laboratory values, cellular cutoffs, and legal/consent boilerplate
LAB_AND_NOISE_REGEX = re.compile(
    r"(?:\banc\b|\bplatelet|\bneutrophil|\bcreatinine|\bbilirubin|\bast\b|\balt\b|\binr\b|\bqtcf\b|"
    r"\blvef\b|\buln\b|mg/dl|g/dl|ml/min|x\s*10\^|informed consent|willing and able|"
    r"life expectancy|contraception|reproductive potential|archival tissue|"
    r"adequate bone marrow|adequate organ|organ function|laboratory values|"
    r"fridericia|washout period|compliance with study|institutional guidelines)",
    re.IGNORECASE,
)

# Regex to skip pure demographic criteria (already automatically matched from user profile)
DEMOGRAPHIC_FILTER_REGEX = re.compile(
    r"^(?:(?:patient\s+is\s+)?age\s*(?:≥|>=|>|of|is)?\s*18|18\s*years\s*(?:of\s*age\s*)?(?:or\s*older|and\s*older)|"
    r"male\s+or\s+female|males?\s+and\s+females?)\b",
    re.IGNORECASE,
)


# 2. Medical dictionary for standard plain-language transformations (6th-8th Grade Reading Level)
# Format: (Regex pattern, Template string, Favorable answer for inclusion/exclusion)
PATTERNS = [
    # --- Exclusions (Favorable answer: NO) ---
    (
        re.compile(r"pregnant|pregnancy|nursing|breastfeeding", re.I),
        "Are you currently pregnant, planning to become pregnant, or breastfeeding?",
        "NO",
    ),
    (
        re.compile(r"(?:brain|cns|central\s+nervous\s+system|cerebral|leptomeningeal).*?(?:tumor|metastas|lesion)", re.I),
        "Has the cancer spread to your brain (brain metastases), or do you have active brain tumors?",
        "NO",
    ),
    (
        re.compile(r"(?:hiv|hepatitis\s+[bc]|hbv|hcv|active\s+viral\s+infection)", re.I),
        "Do you have an active chronic infection, such as Hepatitis B, Hepatitis C, or HIV?",
        "NO",
    ),
    (
        re.compile(r"(?:autoimmune\s+disease|lupus|crohn|colitis|rheumatoid\s+arthritis)", re.I),
        "Do you have an active autoimmune illness (such as lupus, rheumatoid arthritis, or Crohn's disease)?",
        "NO",
    ),
    (
        re.compile(r"(?:congestive\s+heart\s+failure|myocardial\s+infarction|unstable\s+angina|cardiac\s+arrhythmia|cardiovascular\s+disease|heart\s+disease)", re.I),
        "Do you have a history of serious heart disease, heart failure, or active cardiac problems?",
        "NO",
    ),
    (
        re.compile(r"(?:uncontrolled\s+comorbidit|other\s+active\s+(?:medical\s+)?(?:condition|illness))", re.I),
        "Do you have any other serious medical illnesses that are active or poorly controlled?",
        "NO",
    ),
    (
        re.compile(r"(?:prior|previous)\s+treatment\s+with\s+(?:an?\s+)?([A-Za-z0-9\-]+)", re.I),
        "Have you previously received treatment with {0}?",
        "NO",
    ),
    (
        re.compile(r"(?:other|second|concurrent|history\s+of)\s+malignancy", re.I),
        "Have you been diagnosed with or treated for another active cancer in the past 2 to 3 years?",
        "NO",
    ),
    (
        re.compile(r"(?:live\s+(?:attenuated\s+)?vaccine)", re.I),
        "Have you received a live vaccine in the past 4 weeks?",
        "NO",
    ),
    (
        re.compile(r"(?:steroid|corticosteroid|prednisone|immunosuppress)", re.I),
        "Are you currently taking high-dose steroids or medicines that suppress your immune system?",
        "NO",
    ),
    (
        re.compile(r"(?:kidney\s+disease|renal\s+failure|dialysis)", re.I),
        "Do you have severe kidney disease or are you currently receiving dialysis?",
        "NO",
    ),
    (
        re.compile(r"(?:cirrhosis|severe\s+liver\s+disease|hepatic\s+impairment)", re.I),
        "Do you have severe liver disease or cirrhosis?",
        "NO",
    ),

    # --- Inclusions (Favorable answer: YES) ---
    (
        re.compile(r"(?:ecog\s*(?:performance)?\s*(?:status)?\s*[012]|karnofsky|daily\s+activit)", re.I),
        "Are you able to walk and perform everyday personal activities (such as dressing and eating) on your own?",
        "YES",
    ),
    (
        re.compile(r"(?:stage\s*(?:iv|4)|metastatic|unresectable|locally\s+advanced)", re.I),
        "Has your doctor confirmed that your cancer is advanced or metastatic (spread to other areas)?",
        "YES",
    ),
    (
        re.compile(r"(?:fgfr\d*|egfr|braf|kras|alk|ros1|her2|ret|brca\d*|met|ntrk|msi-h|dmmr|pd-l1).*?(?:mutation|fusion|rearrangement|alteration|positive)", re.I),
        "Has genetic or biomarker testing confirmed a specific gene alteration (such as FGFR, EGFR, or BRAF) in your cancer?",
        "YES",
    ),
    (
        re.compile(r"(?:biomarker\s+testing|molecular\s+testing|genetic\s+testing)", re.I),
        "Have you had genetic or molecular testing performed on your tumor or blood?",
        "YES",
    ),
    (
        re.compile(r"(?:previously|prior|received|treated).*?(?:chemotherapy|systemic\s+therapy|immunotherapy|radiation|line\s+of\s+therapy)", re.I),
        "Have you previously received cancer treatment (such as chemotherapy, immunotherapy, or radiation)?",
        "YES",
    ),
    (
        re.compile(r"not\s+received\s+prior\s+treatment\s+with\s+(?:an?\s+)?([A-Za-z0-9\-]+)", re.I),
        "Confirm: You have NOT previously received treatment with {0} or a similar targeted medication?",
        "YES",
    ),
    (
        re.compile(r"(?:recurrent|relapsed|refractory|progressed)", re.I),
        "Has your condition recurred or worsened after prior standard medical treatment?",
        "YES",
    ),
    (
        re.compile(r"(?:histologically|cytologically|patholog)\w*\s+(?:or\s+cytologically\s+)?confirmed\s+(.+)", re.I),
        "Has a doctor or pathology lab confirmed your diagnosis of {0} through a tissue biopsy?",
        "YES",
    ),
    (
        re.compile(r"(?:measurable\s+disease|measurable\s+lesion|recist)", re.I),
        "Do you have a tumor or lesion that can be measured on a scan (like a CT scan or MRI)?",
        "YES",
    ),
]


def _clean_text(text: str) -> str:
    """Removes bullet points, excess whitespace, and trailing periods."""
    cleaned = re.sub(r"^[-*•\d\.\)]\s*", "", text).strip()
    return cleaned.rstrip(".")


def _convert_to_easy_english(raw_text: str, category: str) -> str:
    """
    Fallback converter that simplifies clinical protocol wording into easy English for patients.
    Replaces medical jargon with common words and removes formatting escapes.
    """
    t = raw_text

    # 1. Clean LaTeX and math formatting
    t = re.sub(r"\\>", "more than ", t)
    t = re.sub(r"\\<", "less than ", t)
    t = re.sub(r"[≥>=]+", "at least ", t)
    t = re.sub(r"[≤<=]+", "up to ", t)

    # 2. Strip parenthetical boilerplate
    t = re.sub(r"\s*\([^)]*(?:defined in protocol|per recist|investigator|institutional guidelines)[^)]*\)", "", t, flags=re.I)
    t = re.sub(r"\s*per\s+local\s+testing\s+of\s+blood\s+and/or\s+tumor", "", t, flags=re.I)
    t = re.sub(r"\s*\(other\s+than\s+[^)]+\)", "", t, flags=re.I)

    # 3. Simplify common medical terms into plain words
    t = re.sub(r"\bsystemic\s+therapy\b", "cancer treatment", t, flags=re.I)
    t = re.sub(r"\bcomorbidit(?:y|ies)\b", "serious medical illnesses", t, flags=re.I)
    t = re.sub(r"\bmalignanc(?:y|ies)\b", "cancers", t, flags=re.I)
    t = re.sub(r"\btoxicities\b", "side effects", t, flags=re.I)
    t = re.sub(r"\bconcomitant\s+medications\b", "other medicines", t, flags=re.I)
    t = re.sub(r"\bhistologically\s+confirmed\b", "biopsy-confirmed", t, flags=re.I)
    t = re.sub(r"\badverse\s+events\b", "side effects", t, flags=re.I)

    # Clean whitespace and trailing punctuation
    t = re.sub(r"\s+", " ", t).strip().rstrip(".:;")

    # Keep under ~18 words for readability
    words = t.split()
    if len(words) > 18:
        t = " ".join(words[:18])

    if category == "INCLUSION":
        if re.match(r"^(?:previously|prior|received|treated|had)\b", t, re.I):
            return f"Have you {t[0].lower() + t[1:]}?"
        elif re.match(r"^(?:documented|confirmed)\b", t, re.I):
            return f"Has your doctor or lab test {t[0].lower() + t[1:]}?"
        elif re.match(r"^(?:patient|subject)\s+(?:has|must\s+have|is)\b", t, re.I):
            t = re.sub(r"^(?:patient|subject)\s+(?:has|must\s+have|is)\s+", "", t, flags=re.I)
            return f"Do you have {t}?"
        else:
            return f"Have you been diagnosed with or do you currently have {t[0].lower() + t[1:]}?"
    else:
        # Exclusion
        t = re.sub(r"^(?:patient\s+has|subject\s+has|history\s+of|an?\s+)\s*", "", t, flags=re.I)
        return f"Do you currently have or have you experienced {t[0].lower() + t[1:]}?"


def generate_offline_questions(study: TrialStudy, max_questions: int = 7) -> EligibilityQuestionnaireResponse:
    """
    Generates 5-7 patient-friendly questions 100% offline from study protocol criteria in easy English.
    Filters out laboratory measurements and legal boilerplate.
    """
    questions: list[EligibilityQuestion] = []
    seen_texts: set[str] = set()

    # Pre-populate verified demographic criteria
    demographics_summary: dict[str, Any] = {
        "minimum_age": study.demographics.minimum_age_text or "All Ages",
        "maximum_age": study.demographics.maximum_age_text or "No Upper Limit",
        "sex_restriction": study.demographics.sex,
        "note": "Age and sex eligibility are pre-screened based on your profile.",
    }

    # --- 1. Process Inclusion Criteria (favorable answer: YES) ---
    inc_criteria = study.criteria.inclusion_criteria
    for idx, inc in enumerate(inc_criteria):
        clean_raw = _clean_text(inc)
        if len(clean_raw) < 10 or LAB_AND_NOISE_REGEX.search(clean_raw) or DEMOGRAPHIC_FILTER_REGEX.search(clean_raw):
            continue

        q_text = None
        for pattern, template, _ in PATTERNS:
            match = pattern.search(clean_raw)
            if match:
                groups = match.groups()
                q_text = template.format(*groups) if groups else template
                break

        if not q_text:
            q_text = _convert_to_easy_english(clean_raw, "INCLUSION")

        if q_text and q_text not in seen_texts:
            seen_texts.add(q_text)
            questions.append(EligibilityQuestion(
                id=f"inc_{idx}",
                category="INCLUSION",
                question_text=q_text,
                original_criterion=inc,
                favorable_answer="YES",
            ))

        if len(questions) >= 4:
            break

    # --- 2. Process Exclusion Criteria (favorable answer: NO) ---
    exc_criteria = study.criteria.exclusion_criteria
    for idx, exc in enumerate(exc_criteria):
        clean_raw = _clean_text(exc)
        if len(clean_raw) < 10 or LAB_AND_NOISE_REGEX.search(clean_raw) or DEMOGRAPHIC_FILTER_REGEX.search(clean_raw):
            continue

        q_text = None
        for pattern, template, _ in PATTERNS:
            match = pattern.search(clean_raw)
            if match:
                groups = match.groups()
                q_text = template.format(*groups) if groups else template
                break

        if not q_text:
            q_text = _convert_to_easy_english(clean_raw, "EXCLUSION")

        if q_text and q_text not in seen_texts:
            seen_texts.add(q_text)
            questions.append(EligibilityQuestion(
                id=f"exc_{idx}",
                category="EXCLUSION",
                question_text=q_text,
                original_criterion=exc,
                favorable_answer="NO",
            ))

        if len(questions) >= max_questions:
            break

    # Fallback if trial protocol had 0 extractable criteria (e.g. empty eligibility block)
    if not questions:
        cond_str = ", ".join(study.conditions) if study.conditions else "the targeted medical condition"
        questions.append(EligibilityQuestion(
            id="inc_fallback",
            category="INCLUSION",
            question_text=f"Have you been diagnosed with {cond_str}?",
            original_criterion="Primary study condition diagnosis",
            favorable_answer="YES",
        ))

    return EligibilityQuestionnaireResponse(
        nct_id=study.nct_id,
        trial_title=study.official_title or study.brief_title,
        total_questions=len(questions),
        questions=questions,
        pre_answered_demographics=demographics_summary,
    )


def _normalize_answer_val(val: Any) -> str:
    """Normalizes any user answer input (boolean, integer, string, casing) to YES, NO, or NOT_SURE."""
    if val is None:
        return "NOT_SURE"
    s = str(val).strip().upper().replace(" ", "_").replace("-", "_")
    if s in ("YES", "Y", "TRUE", "1", "PASS", "CLEARED", "MET"):
        return "YES"
    if s in ("NO", "N", "FALSE", "0", "FAIL", "DISQUALIFIED", "UNMET"):
        return "NO"
    return "NOT_SURE"


def _resolve_user_answer(answers_map: dict[str, Any], q: EligibilityQuestion, idx: int) -> str:
    """
    Robust multi-key answer lookup. Prevents user answers from being lost
    due to question ID formatting, index casing, or prefix variations.
    """
    # 1. Exact q.id match
    if q.id in answers_map:
        return _normalize_answer_val(answers_map[q.id])

    # 2. Case-insensitive q.id match
    lower_map = {str(k).strip().lower(): v for k, v in answers_map.items()}
    q_id_lower = str(q.id).strip().lower()
    if q_id_lower in lower_map:
        return _normalize_answer_val(lower_map[q_id_lower])

    # 3. Numeric index match (e.g. "0" or 0)
    if str(idx) in answers_map:
        return _normalize_answer_val(answers_map[str(idx)])
    if idx in answers_map:
        return _normalize_answer_val(answers_map[idx])

    # 4. Standard alternative prefix keys (e.g. "q_0", "inc_0", "exc_0")
    for alt_key in (f"q_{idx}", f"q{idx}", f"inc_{idx}", f"exc_{idx}"):
        if alt_key in lower_map:
            return _normalize_answer_val(lower_map[alt_key])

    # 5. Fallback: default to NOT_SURE
    return "NOT_SURE"


def _identify_cohort_inclusion_questions(
    questions: list[EligibilityQuestion],
    study: TrialStudy,
) -> dict[int, str]:
    """
    Identifies inclusion questions that represent distinct alternative condition cohorts.
    Returns mapping of question index -> matched condition name.
    """
    if not study.conditions or len(study.conditions) < 2:
        return {}

    condition_keywords: dict[str, list[str]] = {}
    stopwords = {"disorder", "syndrome", "disease", "type", "with", "and", "for", "the", "group", "cohort"}
    for cond in study.conditions:
        clean = re.sub(r"[^\w\s]", " ", cond.lower())
        tokens = [t for t in clean.split() if len(t) >= 3 and t not in stopwords]
        if tokens:
            condition_keywords[cond] = tokens

    matched_indices: dict[int, str] = {}
    for idx, q in enumerate(questions):
        if q.category != "INCLUSION":
            continue
        text_to_search = (q.question_text + " " + (getattr(q, "original_criterion", "") or "")).lower()
        for cond, tokens in condition_keywords.items():
            if any(t in text_to_search for t in tokens):
                matched_indices[idx] = cond
                break

    # Only treat as alternative cohorts if at least two distinct conditions matched
    matched_conditions = set(matched_indices.values())
    if len(matched_conditions) >= 2:
        return matched_indices
    return {}


def evaluate_offline_questionnaire(
    study: TrialStudy,
    questions: list[EligibilityQuestion],
    answers_map: dict[str, str],
) -> EligibilityEvaluationResponse:
    """
    Evaluates patient responses against study protocol with clinical rigour and mathematical parity.
    Correctly categorizes into ELIGIBLE, LIKELY_ELIGIBLE, UNCERTAIN, or INELIGIBLE.
    Covers all edge cases: alternative cohorts (OR logic), 0 questions, only exclusions, partial certainty.
    """
    evaluations: list[CriterionEvaluationItem] = []

    # Granular tracking of inclusion and exclusion outcomes
    inc_met: list[str] = []
    inc_unmet: list[str] = []
    inc_unsure: list[str] = []

    exc_met: list[str] = []      # Answered NO to exclusion (cleared - no contraindication)
    exc_unmet: list[str] = []    # Answered YES to exclusion (disqualified - active contraindication)
    exc_unsure: list[str] = []

    # Medical domain detection for clinical care team terminology
    title_text = study.official_title or study.brief_title or ""
    all_conds = " ".join(study.conditions or [])
    combined_medical_text = (title_text + " " + all_conds).lower()
    is_psychiatry = bool(
        re.search(r"bipolar|depress|schizophr|psychiatr|mental\s+health|anxiety|ptsd|mood\s+disorder|personality|psycholog", combined_medical_text)
    )
    is_cancer = bool(
        re.search(r"cancer|carcinoma|sarcoma|melanoma|lymphoma|leukemia|tumor|oncolog|neoplasm|myeloma", combined_medical_text)
    )
    is_cardiac = bool(
        re.search(r"cardio|heart|myocardial|coronary|arrhythmia|cardiac|hypertension|heart\s+failure", combined_medical_text)
    )
    is_neurology = bool(
        re.search(r"neurolog|alzheimer|parkinson|stroke|epilepsy|sclerosis|dementia|migraine", combined_medical_text)
    )
    is_pediatric = bool(
        (study.demographics.maximum_age_years is not None and study.demographics.maximum_age_years < 18)
        or re.search(r"\b(?:pediatric|children|child|infant|adolescent|neonat)\b", combined_medical_text)
    ) and not (is_psychiatry or is_cancer)

    if is_psychiatry:
        care_team_label = "your psychiatrist, psychologist, or mental health specialist"
    elif is_cancer:
        care_team_label = "your oncologist or cancer care team"
    elif is_cardiac:
        care_team_label = "your cardiologist or cardiovascular care team"
    elif is_neurology:
        care_team_label = "your neurologist or neurological care team"
    elif is_pediatric:
        care_team_label = "your pediatrician or specialist care team"
    else:
        care_team_label = "your physician or clinical specialist care team"

    # Multi-Cohort (OR Logic) resolution:
    # If the study has multiple disease arms and the patient confirmed one arm with YES,
    # answering NO to the other cohort arms is an alternative arm requirement, not a failure.
    cohort_map = _identify_cohort_inclusion_questions(questions, study)
    user_qualified_cohort: Optional[str] = None
    for c_idx, c_name in cohort_map.items():
        ans = _resolve_user_answer(answers_map, questions[c_idx], c_idx)
        if ans == "YES":
            user_qualified_cohort = c_name
            break

    for idx, q in enumerate(questions):
        user_answer = _resolve_user_answer(answers_map, q, idx)
        # Clinical invariant: Inclusions require YES, Exclusions require NO
        favorable = "YES" if q.category == "INCLUSION" else "NO"
        clean_q = q.question_text.rstrip("?")

        # Check for alternative cohort satisfaction
        if idx in cohort_map and user_qualified_cohort:
            c_name = cohort_map[idx]
            if user_answer == "YES":
                status = "MET"
                reason = f"You answered 'Yes'. This confirms eligibility for the study under the {c_name} cohort arm."
                inc_met.append(clean_q)
            else:
                # Answered NO or NOT_SURE to an alternative cohort arm
                status = "MET"
                reason = (
                    f"Alternative Study Arm: You qualified under the {user_qualified_cohort} cohort arm. "
                    f"Having this alternative condition ({c_name}) is not required."
                )
                inc_met.append(clean_q)
        elif user_answer == "NOT_SURE":
            status = "UNCERTAIN"
            reason = "You marked 'Not Sure'. Your medical team will verify this from diagnostic records."
            if q.category == "INCLUSION":
                inc_unsure.append(clean_q)
            else:
                exc_unsure.append(clean_q)
        elif user_answer == favorable:
            status = "MET"
            if q.category == "INCLUSION":
                reason = f"You answered 'Yes'. This confirms a required study inclusion: {clean_q}."
                inc_met.append(clean_q)
            else:
                reason = f"You answered 'No'. Having no condition satisfies this exclusion rule: {clean_q}."
                exc_met.append(clean_q)
        else:
            status = "UNMET"
            why_hint = f" ({q.why_it_matters})" if getattr(q, "why_it_matters", None) else ""
            if q.category == "EXCLUSION":
                reason = f"You answered 'Yes'. Having this condition is a disqualifying exclusion rule: {clean_q}{why_hint}."
                exc_unmet.append(clean_q)
            else:
                reason = f"You answered 'No'. This clinical trial requires: {clean_q}{why_hint}."
                inc_unmet.append(clean_q)

        evaluations.append(CriterionEvaluationItem(
            criterion=q.question_text,
            category=q.category,
            status=status,
            user_answer=user_answer,
            reason=reason,
        ))

    total_q = len(questions)
    total_satisfied = len(inc_met) + len(exc_met)
    total_disqualified = len(inc_unmet) + len(exc_unmet)
    total_uncertain = len(inc_unsure) + len(exc_unsure)
    total_inc = len(inc_met) + len(inc_unmet) + len(inc_unsure)
    total_exc = len(exc_met) + len(exc_unmet) + len(exc_unsure)

    # ========================================================
    # CLINICAL VERDICT & CONFIDENCE SCORE DETERMINATION
    # Parity with trialgpt_lite/matcher/scorer.py
    # ========================================================

    # Edge Case 1: 0 questions in protocol (demographics-only study)
    if total_q == 0:
        return EligibilityEvaluationResponse(
            nct_id=study.nct_id,
            verdict=OverallEligibility.ELIGIBLE,
            score=0.95,
            summary="All study requirements are cleared based on your verified demographic profile.",
            criteria_evaluations=[],
            doctor_checklist=["Verify trial location and open study availability with the site coordinator."],
        )

    # Case 2: Definite Ineligibility (Any exclusion contraindication triggered OR inclusion missing)
    if total_disqualified > 0:
        verdict = OverallEligibility.INELIGIBLE
        # Parity with scorer.py: 0.05 for 1 disqualifier, 0.00 for multiple
        score = 0.05 if total_disqualified == 1 else 0.00

        reasons_list = []
        if exc_unmet:
            reasons_list.append(f"triggered {len(exc_unmet)} exclusion contraindication{'s' if len(exc_unmet) > 1 else ''} ({'; '.join(exc_unmet[:2])})")
        if inc_unmet:
            reasons_list.append(f"did not meet {len(inc_unmet)} required inclusion criteria ({'; '.join(inc_unmet[:2])})")

        summary = (
            f"Ineligible: Based on your answers, you do not currently qualify for this clinical trial because you "
            f"{' and '.join(reasons_list)}. We recommend discussing other treatment options and active studies with {care_team_label}."
        )

    # Case 3: Definite Complete Eligibility (All criteria confirmed, 0 contraindications, 0 uncertainties)
    elif total_uncertain == 0:
        verdict = OverallEligibility.ELIGIBLE
        # Full parity with scorer.py: 0.98 for 100% protocol clearance
        score = 0.98 if total_inc > 0 else 0.95
        if user_qualified_cohort:
            summary = (
                f"Great news! You meet all major eligibility criteria for the {user_qualified_cohort} study cohort "
                f"and have cleared all study safety exclusions. "
                f"Your next step is to contact the study team to verify final site-specific laboratory clearances."
            )
        elif total_inc > 0:
            summary = (
                f"Great news! You meet all major eligibility criteria and core inclusion rules, and have cleared all study safety exclusions. "
                f"Your next step is to contact the study team to verify final site-specific laboratory clearances."
            )
        else:
            summary = (
                f"Great news! You meet all major eligibility criteria and cleared all {len(exc_met)} study safety exclusion rules with zero contraindications. "
                f"Your next step is to contact the study coordinator to confirm final enrollment availability."
            )

    # Case 4: Likely Eligible (Some inclusions confirmed, zero contraindications, but some items 'Not Sure')
    elif len(inc_met) > 0:
        verdict = OverallEligibility.LIKELY_ELIGIBLE
        # Weighted clinical confidence: 60% inclusion confirmation ratio + 40% exclusion clearance ratio
        r_inc = len(inc_met) / max(1, len(inc_met) + len(inc_unsure))
        r_exc = (len(exc_met) / max(1, len(exc_met) + len(exc_unsure))) if total_exc > 0 else 1.0
        r_overall = (0.60 * r_inc + 0.40 * r_exc) if total_exc > 0 else r_inc
        # Score scaled between 0.55 and 0.90 (parity with scorer.py)
        score = round(0.55 + 0.35 * r_overall, 2)

        summary = (
            f"Promising match! You confirmed {len(inc_met)} key inclusion criteria with zero disqualifying exclusions. "
            f"Because {total_uncertain} item{' requires' if total_uncertain == 1 else 's require'} verification from medical records, "
            f"we recommend sharing this protocol with {care_team_label}."
        )

    # Case 5: Protocol had ONLY exclusion criteria and all were either cleared or unsure (0 inclusions existed)
    elif total_inc == 0 and len(exc_met) > 0:
        verdict = OverallEligibility.LIKELY_ELIGIBLE if len(exc_met) >= len(exc_unsure) else OverallEligibility.UNCERTAIN
        r_exc = len(exc_met) / max(1, len(exc_met) + len(exc_unsure))
        score = round(0.55 + 0.35 * r_exc, 2)
        summary = (
            f"Good progress! You cleared {len(exc_met)} exclusion contraindications with zero disqualifications. "
            f"Please verify the remaining {len(exc_unsure)} items with {care_team_label}."
        )

    # Case 6: Primary Inclusions Unconfirmed (0 inclusions met, but exclusions cleared)
    elif len(exc_met) > 0:
        verdict = OverallEligibility.UNCERTAIN
        # Base 0.40 (scorer.py parity) + modest bonus for cleared safety exclusions
        r_exc = len(exc_met) / max(1, total_exc)
        score = round(0.40 + 0.12 * r_exc, 2)
        summary = (
            f"Your eligibility is currently uncertain because primary inclusion requirements were marked 'Not Sure'. "
            f"You cleared {len(exc_met)} safety exclusion rules with zero contraindications. "
            f"Please take this questionnaire to {care_team_label} to confirm your official diagnostic reports."
        )

    # Case 7: All items marked NOT_SURE (0 Met, 0 Disqualified)
    else:
        verdict = OverallEligibility.UNCERTAIN
        score = 0.40  # Parity with scorer.py's 0.40
        summary = (
            f"Your eligibility is currently uncertain because all protocol questions were marked 'Not Sure'. "
            f"Please bring this questionnaire to {care_team_label} to review your medical history and clinical records."
        )

    # ========================================================
    # CONDITION-AWARE DOCTOR CONSULTATION CHECKLIST
    # ========================================================
    if is_psychiatry:
        doctor_checklist = [
            "Bring your psychiatric evaluation notes, formal DSM/ICD diagnosis history, and current therapy records.",
            "Provide your complete psychotropic medication list (antidepressants, mood stabilizers, or antipsychotics).",
            "Discuss study mood ratings, surveys, or clinical interviews with your mental health provider.",
        ]
    elif is_cancer:
        doctor_checklist = [
            "Bring your latest pathology, biopsy reports, and scan results (CT / MRI / PET).",
            "Provide your complete prior cancer treatment history (chemotherapy, targeted drugs, radiation).",
            "Site staff will verify laboratory safety panels (neutrophils, platelets, kidney, and liver function).",
        ]
    elif is_cardiac:
        doctor_checklist = [
            "Bring your recent electrocardiogram (ECG/EKG), echocardiogram, and cardiac imaging reports.",
            "Provide your complete cardiovascular medication regimen and symptom history.",
            "Review study exertion and monitoring protocols with your cardiologist.",
        ]
    elif is_pediatric:
        doctor_checklist = [
            "Bring your child's pediatric specialist consultation notes and diagnostic history.",
            "Confirm availability for study activities (e.g. journaling sessions, caregiver surveys, or follow-up interviews).",
            "Review study participation requirements with the pediatric clinical research coordinator.",
        ]
    else:
        cond_label = ", ".join(study.conditions[:2]) if study.conditions else "the targeted medical condition"
        doctor_checklist = [
            f"Bring your medical records and specialist consultation notes regarding {cond_label}.",
            "Provide your complete medication list and relevant diagnostic test results.",
            "Review study participation requirements (e.g. visit schedule, surveys, or daily activities) with the research team.",
        ]

    # Append specific uncertain items to doctor discussion checklist
    for unc in (inc_unsure + exc_unsure):
        doctor_checklist.append(f"Confirm with doctor: {unc}")

    criteria_met_count = len(inc_met) + len(exc_met)
    criteria_match_percentage = round((criteria_met_count / max(1, total_q)) * 100)

    return EligibilityEvaluationResponse(
        nct_id=study.nct_id,
        verdict=verdict,
        score=score,
        summary=summary,
        criteria_evaluations=evaluations,
        doctor_checklist=doctor_checklist,
        criteria_match_percentage=criteria_match_percentage,
        criteria_met_count=criteria_met_count,
        criteria_total_count=total_q,
        cohort_qualified=user_qualified_cohort,
    )
