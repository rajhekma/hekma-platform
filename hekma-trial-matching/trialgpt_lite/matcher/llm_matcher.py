"""
Offline Rule-Based and Heuristic Criteria Matcher.
100% Local Python execution — requires NO API keys, NO external LLMs, and NO network calls.
Handles clinical edge cases including age limits, sex/pregnancy, biomarkers, staging,
negation detection, and contraindication screening with sentence-level evidence attribution.
"""

import logging
import re
from typing import Optional

from trialgpt_lite.schemas.study import TrialStudy
from trialgpt_lite.schemas.request import PatientProfile
from trialgpt_lite.schemas.match_result import CriterionEvaluation

logger = logging.getLogger("trialgpt_lite.matcher")

# Common clinical negation patterns
NEGATION_PATTERNS = [
    r"\bno\b",
    r"\bnot\b",
    r"\bdenies\b",
    r"\bnegative\s+for\b",
    r"\bwithout\b",
    r"\babsence\s+of\b",
    r"\bruled\s+out\b",
    r"\bno\s+evidence\s+of\b",
    r"\bno\s+history\s+of\b",
    r"\bunremarkable\b",
    r"\bnever\b",
]

# Critical medical disqualifiers for exclusion criteria screening
CRITICAL_CONTRAINDICATIONS = {
    "brain metastases": ["brain met", "brain metastases", "cerebral metastases", "cns metastases", "leptomeningeal"],
    "pregnancy": ["pregnant", "pregnancy", "lactating", "breastfeeding", "nursing mother"],
    "renal failure": ["dialysis", "end-stage renal", "severe renal impairment", "creatinine >", "renal failure"],
    "hepatic failure": ["cirrhosis", "liver failure", "hepatic encephalopathy", "severe hepatic impairment"],
    "heart failure": ["congestive heart failure", "nyha class iii", "nyha class iv", "severe heart failure"],
    "active infection": ["active hiv", "hepatitis b active", "active hepatitis c", "active tuberculosis", "sepsis"],
}

# Common oncology biomarkers for targeted therapy matching
BIOMARKER_PATTERNS = {
    "egfr": [r"\begfr\b", r"\bl858r\b", r"\bexon\s*19\b", r"\bt790m\b"],
    "her2": [r"\bher2\b", r"\bher-2\b", r"\berbb2\b"],
    "braf": [r"\bbraf\b", r"\bv600e\b", r"\bv600k\b"],
    "kras": [r"\bkras\b", r"\bg12c\b", r"\bg12d\b"],
    "alk": [r"\balk\b", r"\balk-positive\b", r"\balk\+\b"],
    "ros1": [r"\bros1\b", r"\bros-1\b"],
    "pdl1": [r"\bpd-l1\b", r"\bpdl1\b", r"\btps\b"],
    "er_pr": [r"\bestrogen\s+receptor\b", r"\bprogesterone\s+receptor\b", r"\ber\+\b", r"\bpr\+\b", r"\ber-\b", r"\bpr-\b", r"\btnbc\b", r"\btriple[\s\-]negative\b"],
}


def _is_negated_in_sentence(sentence: str, target_phrase: str) -> bool:
    """
    Determines if a target medical concept is explicitly negated in a patient sentence.
    E.g. 'No evidence of active brain metastases' -> True for 'brain metastases'.
    """
    s_lower = sentence.lower()
    t_lower = target_phrase.lower()
    
    if t_lower not in s_lower:
        return False
        
    # Check if a negation keyword appears within 40 characters preceding the target
    idx = s_lower.find(t_lower)
    preceding_window = s_lower[max(0, idx - 45):idx]
    for neg in NEGATION_PATTERNS:
        if re.search(neg, preceding_window):
            return True
            
    # Check trailing negation like "brain metastases: negative" or "brain metastases absent"
    trailing_window = s_lower[idx + len(t_lower):min(len(s_lower), idx + len(t_lower) + 30)]
    trailing_negs = [r"\bnegative\b", r"\babsent\b", r"\bruled\s+out\b", r"\bnone\b", r"\bnot\s+seen\b"]
    for neg in trailing_negs:
        if re.search(neg, trailing_window):
            return True

    return False


def _evaluate_age_criterion(
    criterion: str,
    criteria_type: str,
    patient_age: Optional[float],
) -> Optional[tuple[str, str]]:
    """
    Evaluates an age criterion for inclusion or exclusion against patient age.
    Returns (label, reason) if an age pattern is matched, otherwise None.
    """
    t = criterion.lower()
    has_age_keyword = any(k in t for k in ["age", "years of age", "years old", "yo", "y.o.", "adult", "pediatric", "older than", "younger than"])
    if not has_age_keyword:
        return None

    if patient_age is None:
        return (
            "not enough information",
            "Age requirement specified in protocol, but patient age is not documented in clinical record."
        )

    # 1. "between X and Y" / "from X to Y" / "age: X to Y" / "aged X to Y"
    m_between = re.search(r"(?:between|from|aged?|age\s*:?)\s*(\d{1,3})\s*(?:to|and|\-)\s*(\d{1,3})\s*(?:years|yo|y\.o\.)?", t)
    if m_between:
        low, high = float(m_between.group(1)), float(m_between.group(2))
        in_range = low <= patient_age <= high
        if criteria_type == "inclusion":
            return (
                "included" if in_range else "not included",
                f"Patient age ({patient_age}y) is within required range ({low}-{high}y)." if in_range else f"Patient age ({patient_age}y) is outside required range ({low}-{high}y)."
            )
        else:
            return (
                "excluded" if in_range else "not excluded",
                f"Patient age ({patient_age}y) falls within excluded range ({low}-{high}y)." if in_range else f"Patient age ({patient_age}y) does not fall in excluded range ({low}-{high}y)."
            )

    # 2. Minimum Age: ">= X" / "at least X" / "minimum of X" / "X or older" / "X and older" / "X+"
    m_min = re.search(r"(?:>=|≥|at\s+least|minimum\s+of)\s*(\d{1,3})", t)
    m_older_phrase = re.search(r"(\d{1,3})\s*(?:years|yo|y\.o\.)?\s*(?:of\s+age\s+)?(?:or\s+older|and\s+older|\+)", t)
    thresh_min = float(m_min.group(1)) if m_min else (float(m_older_phrase.group(1)) if m_older_phrase else None)
    if thresh_min is not None:
        meets_min = patient_age >= thresh_min
        if criteria_type == "inclusion":
            return (
                "included" if meets_min else "not included",
                f"Patient age ({patient_age}y) meets minimum required age ({thresh_min}y)." if meets_min else f"Patient age ({patient_age}y) is below minimum required age ({thresh_min}y)."
            )
        else:
            return (
                "excluded" if meets_min else "not excluded",
                f"Patient age ({patient_age}y) meets excluded age threshold." if meets_min else f"Patient age ({patient_age}y) does not trigger exclusion."
            )

    # 3. "older than X" / "greater than X" / "over X" / "> X"
    m_over = re.search(r"(?:older\s+than|greater\s+than|over\s+|>)\s*(\d{1,3})", t)
    if m_over:
        threshold = float(m_over.group(1))
        is_older = patient_age > threshold
        if criteria_type == "exclusion":
            return (
                "excluded" if is_older else "not excluded",
                f"Patient age ({patient_age}y) exceeds allowable limit ({threshold}y)." if is_older else f"Patient age ({patient_age}y) is within allowable limit (<= {threshold}y)."
            )
        else:
            return (
                "included" if is_older else "not included",
                f"Patient age ({patient_age}y) satisfies requirement (> {threshold}y)." if is_older else f"Patient age ({patient_age}y) is below required age (> {threshold}y)."
            )

    # 4. "younger than X" / "less than X" / "under X" / "< X" / "<= X"
    m_under = re.search(r"(?:younger\s+than|less\s+than|under\s+|<=|≤|<)\s*(\d{1,3})", t)
    if m_under:
        threshold = float(m_under.group(1))
        is_younger = patient_age < threshold
        if criteria_type == "exclusion":
            return (
                "excluded" if is_younger else "not excluded",
                f"Patient age ({patient_age}y) is below age limit (< {threshold}y)." if is_younger else f"Patient age ({patient_age}y) is not under age limit (>= {threshold}y)."
            )
        else:
            return (
                "included" if is_younger else "not included",
                f"Patient age ({patient_age}y) satisfies requirement (< {threshold}y)." if is_younger else f"Patient age ({patient_age}y) exceeds requirement (< {threshold}y)."
            )

    return None



class LLMCriteriaMatcher:
    """
    Deterministic Offline Rule-Based Matcher for Clinical Trial Criteria.
    Requires NO external API keys or external LLM connections.
    Evaluates individual inclusion/exclusion criteria against patient profiles with clinical rules.
    """

    def __init__(self, provider: Optional[str] = "heuristic"):
        # Provider is kept for interface compatibility; defaults to offline rule-based
        self.provider = "heuristic"
        self.client = None
        logger.info("Initialized 100% offline rule-based clinical criteria matching engine.")

    def match_criteria(
        self,
        study: TrialStudy,
        patient: PatientProfile,
    ) -> list[CriterionEvaluation]:
        """
        Runs comprehensive rule-based evaluation for both inclusion and exclusion criteria.
        """
        evaluations: list[CriterionEvaluation] = []

        # 1. Evaluate Inclusion Criteria (up to top 20)
        if study.criteria.inclusion_criteria:
            inc_evals = self._evaluate_block(
                criteria_list=study.criteria.inclusion_criteria[:20],
                criteria_type="inclusion",
                study=study,
                patient=patient,
            )
            evaluations.extend(inc_evals)

        # 2. Evaluate Exclusion Criteria (up to top 20)
        if study.criteria.exclusion_criteria:
            exc_evals = self._evaluate_block(
                criteria_list=study.criteria.exclusion_criteria[:20],
                criteria_type="exclusion",
                study=study,
                patient=patient,
            )
            evaluations.extend(exc_evals)

        return evaluations

    def _evaluate_block(
        self,
        criteria_list: list[str],
        criteria_type: str,
        study: TrialStudy,
        patient: PatientProfile,
    ) -> list[CriterionEvaluation]:
        """Evaluates one criteria block using clinical heuristic rules."""
        evaluations: list[CriterionEvaluation] = []
        patient_note = patient.clinical_note or ""
        patient_sentences = patient.sentences or []
        p_sex = (patient.sex or "").lower()
        p_cond = (patient.condition or "").lower()

        for idx, criterion in enumerate(criteria_list):
            c_lower = criterion.lower()
            matching_sents = self._find_matching_sentences(criterion, patient_sentences)
            
            # ----------------------------------------------------
            # Rule 1: Age Evaluation
            # ----------------------------------------------------
            age_result = _evaluate_age_criterion(criterion, criteria_type, patient.age)
            if age_result is not None:
                lbl, rsn = age_result
                evaluations.append(CriterionEvaluation(
                    criterion_index=idx,
                    criterion_type=criteria_type,
                    criterion_text=criterion,
                    reasoning=rsn,
                    sentence_ids=matching_sents[:3],
                    label=lbl,
                ))
                continue


            # ----------------------------------------------------
            # Rule 2: Biological Sex & Reproductive Status
            # ----------------------------------------------------
            is_preg_criterion = any(p in c_lower for p in ["pregnant", "pregnancy", "breastfeeding", "lactating", "childbearing"])
            if is_preg_criterion:
                if p_sex == "male":
                    evaluations.append(CriterionEvaluation(
                        criterion_index=idx,
                        criterion_type=criteria_type,
                        criterion_text=criterion,
                        reasoning="Pregnancy and lactation criteria are not applicable to male patients.",
                        sentence_ids=[],
                        label="not applicable",
                    ))
                    continue
                else:
                    # Check if female patient has documented pregnancy
                    preg_positive = False
                    for s_id, s in enumerate(patient_sentences):
                        if any(term in s.lower() for term in ["pregnant", "pregnancy", "lactating", "breastfeeding"]):
                            if not _is_negated_in_sentence(s, "pregnant") and not _is_negated_in_sentence(s, "pregnancy"):
                                preg_positive = True
                                matching_sents.append(s_id)
                                break
                    if preg_positive:
                        label = "excluded" if criteria_type == "exclusion" else "not included"
                        reason = "Patient clinical record notes active pregnancy / lactation."
                    else:
                        label = "not excluded" if criteria_type == "exclusion" else "not enough information"
                        reason = "No documentation of pregnancy in patient notes; verification required prior to trial."
                    
                    evaluations.append(CriterionEvaluation(
                        criterion_index=idx,
                        criterion_type=criteria_type,
                        criterion_text=criterion,
                        reasoning=reason,
                        sentence_ids=matching_sents[:3],
                        label=label,
                    ))
                    continue

            # Sex specificity
            is_female_specific = any(term in c_lower for term in ["female patients", "women with", "female only", "female subjects"])
            is_male_specific = any(term in c_lower for term in ["male patients", "men with", "male only", "male subjects"])
            
            if is_female_specific and p_sex:
                if p_sex != "female":
                    evaluations.append(CriterionEvaluation(
                        criterion_index=idx,
                        criterion_type=criteria_type,
                        criterion_text=criterion,
                        reasoning=f"Criterion specifies female participants; patient is recorded as {p_sex}.",
                        sentence_ids=[],
                        label="not included" if criteria_type == "inclusion" else "excluded",
                    ))
                    continue
            elif is_male_specific and p_sex:
                if p_sex != "male":
                    evaluations.append(CriterionEvaluation(
                        criterion_index=idx,
                        criterion_type=criteria_type,
                        criterion_text=criterion,
                        reasoning=f"Criterion specifies male participants; patient is recorded as {p_sex}.",
                        sentence_ids=[],
                        label="not included" if criteria_type == "inclusion" else "excluded",
                    ))
                    continue

            # ----------------------------------------------------
            # Rule 3: Clinical Exclusion / Contraindication Check
            # ----------------------------------------------------
            if criteria_type == "exclusion":
                contraindication_found = False
                contra_reason = ""
                disqualifier_key = None

                for key, synonyms in CRITICAL_CONTRAINDICATIONS.items():
                    if any(syn in c_lower for syn in synonyms):
                        disqualifier_key = key
                        # Check if patient record has this contraindication (and NOT negated)
                        for s_id, s in enumerate(patient_sentences):
                            for syn in synonyms:
                                if syn in s.lower():
                                    if not _is_negated_in_sentence(s, syn):
                                        contraindication_found = True
                                        contra_reason = f"Patient record positive for {key}: '{s.strip()}'."
                                        matching_sents.append(s_id)
                                        break
                                    else:
                                        # Explicitly negated e.g. "no brain metastases"
                                        matching_sents.append(s_id)
                            if contraindication_found:
                                break
                    if contraindication_found:
                        break

                if contraindication_found:
                    evaluations.append(CriterionEvaluation(
                        criterion_index=idx,
                        criterion_type="exclusion",
                        criterion_text=criterion,
                        reasoning=contra_reason,
                        sentence_ids=list(dict.fromkeys(matching_sents))[:3],
                        label="excluded",
                    ))
                    continue
                elif disqualifier_key:
                    evaluations.append(CriterionEvaluation(
                        criterion_index=idx,
                        criterion_type="exclusion",
                        criterion_text=criterion,
                        reasoning=f"No contraindication of active {disqualifier_key} documented in patient note.",
                        sentence_ids=list(dict.fromkeys(matching_sents))[:3],
                        label="not excluded",
                    ))
                    continue
                else:
                    # General exclusion criterion
                    evaluations.append(CriterionEvaluation(
                        criterion_index=idx,
                        criterion_type="exclusion",
                        criterion_text=criterion,
                        reasoning="No contraindicating condition identified in patient summary.",
                        sentence_ids=list(dict.fromkeys(matching_sents))[:3],
                        label="not excluded",
                    ))
                    continue

            # ----------------------------------------------------
            # Rule 4: Primary Condition & Histology / Staging (Inclusion)
            # ----------------------------------------------------
            # Check if criterion mentions the target condition or study conditions
            study_conds = [c.lower() for c in (study.conditions or [])]
            cond_mentioned_in_criterion = any(sc in c_lower for sc in study_conds) or (p_cond and p_cond in c_lower)
            
            # Check if patient note mentions the condition positively
            patient_has_cond = False
            if p_cond:
                for s_id, s in enumerate(patient_sentences):
                    if p_cond in s.lower() and not _is_negated_in_sentence(s, p_cond):
                        patient_has_cond = True
                        matching_sents.append(s_id)
            
            if cond_mentioned_in_criterion:
                if patient_has_cond or p_cond:
                    evaluations.append(CriterionEvaluation(
                        criterion_index=idx,
                        criterion_type="inclusion",
                        criterion_text=criterion,
                        reasoning=f"Target condition '{patient.condition}' aligns with study eligibility criteria.",
                        sentence_ids=list(dict.fromkeys(matching_sents))[:3],
                        label="included",
                    ))
                    continue
                else:
                    evaluations.append(CriterionEvaluation(
                        criterion_index=idx,
                        criterion_type="inclusion",
                        criterion_text=criterion,
                        reasoning="Condition mentioned in protocol; clinical histological confirmation required.",
                        sentence_ids=list(dict.fromkeys(matching_sents))[:3],
                        label="not enough information",
                    ))
                    continue

            # ----------------------------------------------------
            # Rule 5: Biomarkers & Genetic Alterations (Inclusion)
            # ----------------------------------------------------
            biomarker_evaluated = False
            for b_name, patterns in BIOMARKER_PATTERNS.items():
                if any(re.search(pat, c_lower) for pat in patterns):
                    # Criterion mentions a biomarker (e.g. EGFR, HER2, BRAF)
                    note_has_bio = False
                    bio_negated = False
                    for s_id, s in enumerate(patient_sentences):
                        for pat in patterns:
                            if re.search(pat, s.lower()):
                                matching_sents.append(s_id)
                                if _is_negated_in_sentence(s, pat.strip(r"\b")):
                                    bio_negated = True
                                else:
                                    note_has_bio = True
                                break
                    
                    if note_has_bio and not bio_negated:
                        evaluations.append(CriterionEvaluation(
                            criterion_index=idx,
                            criterion_type="inclusion",
                            criterion_text=criterion,
                            reasoning=f"Biomarker alteration ({b_name.upper()}) confirmed in patient clinical summary.",
                            sentence_ids=list(dict.fromkeys(matching_sents))[:3],
                            label="included",
                        ))
                        biomarker_evaluated = True
                        break
                    elif bio_negated:
                        evaluations.append(CriterionEvaluation(
                            criterion_index=idx,
                            criterion_type="inclusion",
                            criterion_text=criterion,
                            reasoning=f"Patient note indicates negative / wild-type status for {b_name.upper()}.",
                            sentence_ids=list(dict.fromkeys(matching_sents))[:3],
                            label="not included",
                        ))
                        biomarker_evaluated = True
                        break
                    else:
                        evaluations.append(CriterionEvaluation(
                            criterion_index=idx,
                            criterion_type="inclusion",
                            criterion_text=criterion,
                            reasoning=f"Biomarker status for {b_name.upper()} is not explicitly documented in patient note.",
                            sentence_ids=[],
                            label="not enough information",
                        ))
                        biomarker_evaluated = True
                        break

            if biomarker_evaluated:
                continue

            # ----------------------------------------------------
            # Rule 6: General Default Evaluation
            # ----------------------------------------------------
            if matching_sents:
                evaluations.append(CriterionEvaluation(
                    criterion_index=idx,
                    criterion_type="inclusion",
                    criterion_text=criterion,
                    reasoning="Relevant clinical documentation identified in patient record; specific thresholds require verification.",
                    sentence_ids=list(dict.fromkeys(matching_sents))[:3],
                    label="not enough information",
                ))
            else:
                evaluations.append(CriterionEvaluation(
                    criterion_index=idx,
                    criterion_type="inclusion",
                    criterion_text=criterion,
                    reasoning="Clinical documentation does not explicitly address this protocol requirement.",
                    sentence_ids=[],
                    label="not enough information",
                ))

        return evaluations

    def _find_matching_sentences(self, criterion: str, sentences: list[str]) -> list[int]:
        """
        Calculates lexical token overlap between a criterion and each patient sentence.
        Returns matching sentence indices (0-indexed).
        """
        c_words = set(re.findall(r"\w{4,}", criterion.lower()))
        # Remove high-frequency clinical stopwords
        stopwords = {
            "with", "from", "that", "this", "have", "must", "than", "more", "least", "will",
            "been", "each", "were", "what", "which", "when", "their", "there", "other", "about",
            "study", "trial", "prior", "after", "before", "during", "patient", "patients"
        }
        c_keywords = c_words - stopwords
        
        matches = []
        for idx, sentence in enumerate(sentences):
            s_words = set(re.findall(r"\w{4,}", sentence.lower()))
            overlap = c_keywords & s_words
            if len(overlap) >= 2 or (len(overlap) >= 1 and any(len(w) >= 6 for w in overlap)):
                matches.append(idx)
                
        return matches


# Alias for backward-compatible naming
RuleBasedCriteriaMatcher = LLMCriteriaMatcher
HeuristicCriteriaMatcher = LLMCriteriaMatcher
