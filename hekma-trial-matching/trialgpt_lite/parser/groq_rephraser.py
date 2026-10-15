"""
Real-Time Clinical Trial Eligibility Question Rephraser using Groq LPU Inference.
Converts complex clinical protocol criteria into patient-friendly 6th-8th grade English Yes/No questions.
Operates as a dedicated, high-speed LPU engine with zero fallbacks.
"""

import json
import logging
import re
import time
from typing import Any, Optional

from trialgpt_lite.config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_TIMEOUT_SECONDS,
)
from trialgpt_lite.schemas.study import TrialStudy
from trialgpt_lite.schemas.match_result import (
    EligibilityQuestion,
    EligibilityQuestionnaireResponse,
    PatientStudySummaryResponse,
    TermExplanation,
)
from trialgpt_lite.parser.question_generator import (
    LAB_AND_NOISE_REGEX,
    DEMOGRAPHIC_FILTER_REGEX,
    _clean_text,
)

logger = logging.getLogger("trialgpt_lite.groq_rephraser")

SYSTEM_PROMPT = """You are an empathetic clinical trial patient navigator and medical translator.
Your task is to translate complex clinical trial inclusion and exclusion criteria into simple, conversational Yes/No questions that an ordinary patient (6th to 8th grade reading level) can easily understand and answer.

RULES:
1. Simplify medical jargon into plain, everyday language (e.g., "metastatic" -> "spread to other parts of your body", "ECOG 0-1" -> "able to do daily personal activities like dressing and walking without help", "prior systemic therapy" -> "previous cancer treatments like chemotherapy").
2. Every question MUST be answerable with 'YES', 'NO', or 'NOT SURE'.
3. For INCLUSION criteria: The favorable answer MUST be "YES" (e.g., "Have you been diagnosed with...?").
4. For EXCLUSION criteria: The favorable answer MUST be "NO" (e.g., "Do you currently have or have you had...?").
5. Keep question_text concise (under 20 words).
6. Provide a concise 'why_it_matters' explanation (1 sentence) written gently to explain why doctors check this.
7. Return ONLY valid JSON in the exact schema requested. No markdown formatting, no code fences.
8. SCIENTIFIC & DRUG LOCALIZATION: Ordinary patients do not know scientific pharmaceutical names, antibodies, or medical jargon. Whenever a specific drug name (e.g. lebrikizumab, pembrolizumab, osimertinib, dupilumab), therapy class (e.g. corticosteroids, biologics, immunosuppressants), biomarker (e.g. EGFR, HER2, FGFR2), or medical condition (e.g. atopic dermatitis, hypertension, nephropathy) is mentioned:
   You MUST localize and explain it immediately in simple everyday conversational English in parentheses or natural wording so any patient can understand.
   Examples:
   - "lebrikizumab" -> "lebrikizumab (a targeted injection medicine for severe eczema)"
   - "atopic dermatitis" -> "atopic dermatitis (eczema, a condition that causes red, itchy skin)"
   - "systemic corticosteroids" -> "steroid medications (like prednisone pills or cortisone injections)"
   - "ECOG performance status 0-1" -> "able to do daily personal activities like dressing and walking without help"
   - "hepatic impairment" -> "liver problems or serious liver disease"
   - "renal insufficiency" -> "kidney disease or reduced kidney function"
"""


# Priority heuristics for clinical inclusion criteria
INCLUSION_PRIORITY_PATTERNS = [
    # Tier 1: Primary condition, histology, molecular biomarker/genetics
    (re.compile(r"diagnos|histolog|cytolog|patholog|confirmed|mutation|fusion|amplification|positive|negative|rearrangement|biomarker", re.I), 10),
    # Tier 2: Staging, recurrence, progression, surgical setting
    (re.compile(r"stage\s*(?:iv|4|iii|3)|metastat|advanced|unresectable|relapsed|refractory|recurrent|progression|ambulatory|outpatient|day\s*surgery", re.I), 8),
    # Tier 3: Treatment history, lines of therapy, surgical status
    (re.compile(r"prior|treatment|therapy|chemotherapy|systemic|line\s+of|surgery|surgical|radiation|resected", re.I), 6),
    # Tier 4: Functional / Performance status (ECOG, Karnofsky, daily activities)
    (re.compile(r"ecog|performance\s+status|karnofsky|daily\s+activit", re.I), 4),
]

# Priority heuristics for clinical exclusion criteria
EXCLUSION_PRIORITY_PATTERNS = [
    # Tier 1: Universal hard safety contraindications
    (re.compile(r"pregnant|pregnancy|nursing|breastfeeding", re.I), 10),
    (re.compile(r"brain|cns|central\s+nervous|cerebral|leptomeningeal", re.I), 10),
    (re.compile(r"heart\s+failure|cardiac|myocardial|arrhythmia|infarction|qtcf", re.I), 9),
    (re.compile(r"hiv|hepatitis|hbv|hcv|active\s+infection|tuberculosis", re.I), 9),
    (re.compile(r"kidney\s+disease|renal\s+failure|dialysis|cirrhosis|liver\s+failure", re.I), 8),
    # Tier 2: Conflicting therapy / medication contraindications
    (re.compile(r"prior\s+treatment\s+with|concurrent|investigational|live\s+vaccine|immunosuppress|steroid", re.I), 7),
    # Tier 3: Secondary malignancies / other active conditions
    (re.compile(r"second\s+malignancy|other\s+cancer|autoimmune|uncontrolled", re.I), 6),
]

HEADER_NOISE_REGEX = re.compile(
    r"^(?:for screening\b|inclusion criteria\b|exclusion criteria\b|cohort [a-z]\b|screening\s*\.\.\.|randomization\s*\.\.\.)",
    re.I,
)


def _score_criterion_priority(text: str, is_inclusion: bool) -> int:
    """Calculates clinical impact score (1-10) to rank patient-actionable criteria."""
    patterns = INCLUSION_PRIORITY_PATTERNS if is_inclusion else EXCLUSION_PRIORITY_PATTERNS
    for pat, score in patterns:
        if pat.search(text):
            return score
    return 2


def _prepare_criteria_for_llm(
    study: TrialStudy, target_total: int = 7
) -> list[dict[str, str]]:
    """
    Intelligently filters, ranks, and dynamically balances inclusion vs exclusion criteria.
    Handles highly skewed real-world distributions (e.g. 2 inclusions & 14 exclusions, or 10 inclusions & 1 exclusion).
    Ensures primary disease confirmation is always present and selects the top-ranked patient-actionable rules.
    """
    clean_inc: list[tuple[int, int, str]] = []
    clean_exc: list[tuple[int, int, str]] = []

    # 1. Filter and score all candidate inclusions
    for idx, inc in enumerate(study.criteria.inclusion_criteria):
        clean = _clean_text(inc)
        if len(clean) < 10 or HEADER_NOISE_REGEX.search(clean) or LAB_AND_NOISE_REGEX.search(clean) or DEMOGRAPHIC_FILTER_REGEX.search(clean):
            continue
        priority = _score_criterion_priority(clean, is_inclusion=True)
        clean_inc.append((priority, idx, clean))

    # 2. Filter and score all candidate exclusions
    for idx, exc in enumerate(study.criteria.exclusion_criteria):
        clean = _clean_text(exc)
        if len(clean) < 10 or HEADER_NOISE_REGEX.search(clean) or LAB_AND_NOISE_REGEX.search(clean) or DEMOGRAPHIC_FILTER_REGEX.search(clean):
            continue
        priority = _score_criterion_priority(clean, is_inclusion=False)
        clean_exc.append((priority, idx, clean))

    # Sort descending by clinical priority
    clean_inc.sort(key=lambda x: x[0], reverse=True)
    clean_exc.sort(key=lambda x: x[0], reverse=True)

    # 3. Dynamic Budget Allocation (Target 5-7 questions)
    items_to_rephrase: list[dict[str, str]] = []
    n_inc = len(clean_inc)
    n_exc = len(clean_exc)

    # If 0 inclusions exist, synthesize primary disease confirmation inclusion
    primary_synthesized = False
    if n_inc == 0:
        cond_str = ", ".join(study.conditions) if study.conditions else "the targeted medical condition"
        items_to_rephrase.append({
            "id": "inc_0",
            "category": "INCLUSION",
            "criterion": f"Confirmed diagnosis of {cond_str}",
            "favorable_answer": "YES",
        })
        primary_synthesized = True
        n_inc = 1

    # Adaptive quota calculation
    if n_inc <= 2 and not primary_synthesized:
        # Inclusions are scarce: take ALL inclusions, fill remainder with top exclusions
        inc_quota = n_inc
        exc_quota = min(target_total - inc_quota, n_exc)
    elif primary_synthesized:
        inc_quota = 0
        exc_quota = min(target_total - 1, n_exc)
    elif n_exc <= 2:
        # Exclusions are scarce: take ALL exclusions, fill remainder with top inclusions
        exc_quota = n_exc
        inc_quota = min(target_total - exc_quota, n_inc)
    else:
        # Both abundant: balanced 3-4 split
        inc_quota = min(4, n_inc)
        exc_quota = min(target_total - inc_quota, n_exc)

    # Add selected ranked inclusions
    if not primary_synthesized:
        for _, orig_idx, text in clean_inc[:inc_quota]:
            items_to_rephrase.append({
                "id": f"inc_{orig_idx}",
                "category": "INCLUSION",
                "criterion": text,
                "favorable_answer": "YES",
            })

    # Add selected ranked exclusions
    for _, orig_idx, text in clean_exc[:exc_quota]:
        items_to_rephrase.append({
            "id": f"exc_{orig_idx}",
            "category": "EXCLUSION",
            "criterion": text,
            "favorable_answer": "NO",
        })

    return items_to_rephrase


def _emit_groq_usage(usage) -> None:
    try:
        from services.ai_usage import emit_llm_usage

        emit_llm_usage(
            product="trial_match",
            feature="trial_match.study_summary",
            provider="groq",
            model=GROQ_MODEL,
            usage=usage,
            source_service="hekma-trialgpt",
        )
    except Exception:
        logger.debug("AI usage emit skipped", exc_info=True)


def _chat_completion_with_groq(
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    max_tokens: int = 850,
) -> str:
    """
    Executes a chat completion call against Groq LPU API.
    Attempts to use the official 'groq' Python SDK if installed;
    if 'groq' is not installed (e.g. in container environments before package install),
    seamlessly falls back to Groq's official REST endpoint via httpx/requests with zero downtime.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured in the server environment.")

    # 1. Try official groq SDK if installed
    try:
        from groq import Groq  # type: ignore

        client = Groq(api_key=GROQ_API_KEY, timeout=GROQ_TIMEOUT_SECONDS)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
        )
        _emit_groq_usage(getattr(response, "usage", None))
        return response.choices[0].message.content or "{}"
    except (ImportError, ModuleNotFoundError):
        logger.info("groq SDK package not installed; executing via direct Groq LPU REST API (httpx).")
    except Exception as sdk_err:
        raise sdk_err

    # 2. Resilient Direct HTTP to Groq LPU endpoint
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        import httpx

        resp = httpx.post(endpoint, headers=headers, json=payload, timeout=GROQ_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        _emit_groq_usage(data.get("usage"))
        return data["choices"][0]["message"]["content"] or "{}"
    except Exception as http_err:
        try:
            import requests

            resp = requests.post(endpoint, headers=headers, json=payload, timeout=GROQ_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            _emit_groq_usage(data.get("usage"))
            return data["choices"][0]["message"]["content"] or "{}"
        except Exception as req_err:
            raise RuntimeError(f"Groq LPU REST API call failed: {req_err}") from req_err


def _call_groq(items: list[dict[str, str]], trial_title: str) -> Optional[list[dict[str, Any]]]:
    """Invokes Groq API with JSON mode for ultra-fast rephrasing."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured in the server environment.")

    user_prompt = f"""Clinical Trial Title: {trial_title}

Translate the following eligibility criteria into patient-friendly Yes/No questions in 6th-grade English:
{json.dumps(items, indent=2)}

Respond with JSON format:
{{
  "questions": [
    {{
      "id": "item id matching input",
      "category": "INCLUSION or EXCLUSION",
      "question_text": "Simple question for patient ending in ?",
      "why_it_matters": "One gentle sentence explaining why doctors check this",
      "original_criterion": "the original input criterion",
      "favorable_answer": "YES for inclusion, NO for exclusion"
    }}
  ]
}}"""

    try:
        content = _chat_completion_with_groq(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=800,
        )

        parsed = json.loads(content)
        questions = parsed.get("questions", [])
        if isinstance(questions, list) and len(questions) > 0:
            return questions
        logger.warning(f"Groq returned empty question list: {content[:100]}")
        return None
    except Exception as e:
        logger.error(f"Groq rephrasing encountered error: {e}")
        raise RuntimeError(f"Groq rephrasing failed: {e}") from e


def generate_realtime_questions(
    study: TrialStudy, max_questions: int = 7
) -> EligibilityQuestionnaireResponse:
    """
    Generates patient-friendly questions in real-time exclusively using Groq LPU.
    No OpenAI fallback and no offline rule fallback.
    """
    demographics_summary: dict[str, Any] = {
        "minimum_age": study.demographics.minimum_age_text or "All Ages",
        "maximum_age": study.demographics.maximum_age_text or "No Upper Limit",
        "sex_restriction": study.demographics.sex,
        "note": "Age and sex eligibility are pre-screened based on your profile.",
    }

    trial_title = study.official_title or study.brief_title or "Clinical Study"
    candidate_items = _prepare_criteria_for_llm(study, target_total=max_questions)

    # Edge Case: Protocol has no criteria text
    if not candidate_items:
        return EligibilityQuestionnaireResponse(
            nct_id=study.nct_id,
            trial_title=trial_title,
            total_questions=0,
            questions=[],
            engine="GROQ",
            pre_answered_demographics=demographics_summary,
        )

    # Invoke Groq LPU (Dedicated - Zero Fallbacks)
    raw_questions = _call_groq(candidate_items, trial_title)
    if not raw_questions:
        raise RuntimeError(
            f"Groq LPU questionnaire generation failed for trial {study.nct_id}. Dedicated Groq mode has zero fallbacks."
        )

    # Parse and validate questions
    final_questions: list[EligibilityQuestion] = []
    seen_texts: set[str] = set()

    for item in raw_questions:
        q_id = str(item.get("id") or f"q_{len(final_questions)}")
        raw_cat = str(item.get("category") or "").upper()
        if raw_cat in ("INCLUSION", "EXCLUSION"):
            cat = raw_cat
        else:
            cat = "EXCLUSION" if q_id.lower().startswith("exc") else "INCLUSION"

        q_text = str(item.get("question_text") or "").strip()
        why = str(item.get("why_it_matters") or "").strip()
        orig = str(item.get("original_criterion") or "").strip()
        # Strictly enforce clinical invariant: Inclusion is YES, Exclusion is NO
        fav = "YES" if cat == "INCLUSION" else "NO"

        if not q_text or q_text.lower() in seen_texts:
            continue
        if not q_text.endswith("?"):
            q_text += "?"

        seen_texts.add(q_text.lower())
        final_questions.append(
            EligibilityQuestion(
                id=q_id,
                category=cat,
                question_text=q_text,
                why_it_matters=why,
                original_criterion=orig,
                favorable_answer=fav,
            )
        )

        if len(final_questions) >= max_questions:
            break

    return EligibilityQuestionnaireResponse(
        nct_id=study.nct_id,
        trial_title=trial_title,
        total_questions=len(final_questions),
        questions=final_questions,
        engine="GROQ",
        pre_answered_demographics=demographics_summary,
    )


SUMMARY_SYSTEM_PROMPT = """You are an empathetic clinical trial patient navigator, health literacy specialist, and medical educator.
Your task is to translate a complex clinical trial protocol from ClinicalTrials.gov into an accessible, clear, and reassuring patient summary written at a 6th to 8th grade reading level.

CRITICAL RULES:
1. SCIENTIFIC & MEDICAL LOCALIZATION:
   Ordinary patients and families do NOT understand dense medical jargon or scientific terms.
   Whenever a specific prescription drug (e.g., lebrikizumab, pembrolizumab, osimertinib), biologic antibody, medical condition (e.g., atopic dermatitis, adenocarcinoma, thrombocytopenia), or procedure is mentioned:
   - Always translate and explain it immediately in simple, conversational language in the text.
   - Also extract it into the "complex_terms_explained" list with a clear, friendly 1-sentence plain-English explanation.
2. STRUCTURED SECTIONS:
   - "plain_title": A short, conversational 1-sentence title that anyone can understand (e.g. "Testing an Injection Medicine (Lebrikizumab) to Help Relieve Severe Eczema").
   - "what_this_study_is_about": 2 to 3 simple, comforting sentences explaining the main purpose of the study.
   - "treatment_and_how_it_works": Plain-English explanation of the drug or treatment being tested, what kind of medicine it is, and how it works inside the body.
   - "what_participation_involves": Clear, everyday explanation of what participants will actually do (e.g. clinic visit schedule, check-ups, blood draws, pills or injections, and how long the study lasts).
   - "who_can_join_overview": Simple, encouraging overview of who doctors are looking for (age range, key condition, health requirements).
   - "plain_inclusions": A list of 3 to 5 key participation requirements to join, written in simple, clear everyday English bullet points (e.g. ["Must be 18 years or older", "Diagnosed with moderate to severe eczema for at least 1 year"]).
   - "plain_exclusions": A list of 3 to 5 key safety rules that prevent joining, written in simple, clear everyday English bullet points (e.g. ["Currently taking strong immune-suppressing pills", "Active serious infection", "Pregnant or currently breastfeeding"]).
   - "complex_terms_explained": A list of objects with "term" and "plain_english" defining every scientific, healthcare, drug, or procedural term used in this study.
3. TONE: Empathetic, empowering, transparent, and easy to read.
4. Output MUST be valid JSON adhering strictly to the schema without markdown code blocks.
"""


def generate_patient_study_summary(study: TrialStudy) -> PatientStudySummaryResponse:
    """
    Generates a comprehensive, patient-friendly plain-English summary of a clinical trial
    including translated participation criteria (inclusions & exclusions) using Groq LPU.
    """
    start_time = time.perf_counter()
    trial_title = study.official_title or study.brief_title or "Clinical Study"

    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured for plain-English study summary generation.")

    # Prepare context for LLM
    conditions_str = ", ".join(study.conditions) if study.conditions else "Unspecified"
    interventions_str = ", ".join(study.interventions) if study.interventions else "Standard clinical care"
    brief_desc = (study.brief_summary or "").strip()
    
    # Extract sample criteria for plain-English translation
    inc_items = (study.criteria.inclusion_criteria[:6] if getattr(study, "criteria", None) else [])
    exc_items = (study.criteria.exclusion_criteria[:6] if getattr(study, "criteria", None) else [])
    
    inc_text = "\n".join(f"- {item}" for item in inc_items) if inc_items else "Standard condition requirements"
    exc_text = "\n".join(f"- {item}" for item in exc_items) if exc_items else "Standard clinical safety contraindications"

    user_prompt = f"""Clinical Trial Protocol Details:
- Study Title: {trial_title}
- Target Conditions: {conditions_str}
- Investigational Interventions (Drugs / Procedures): {interventions_str}
- Phase: {', '.join(study.phases) if study.phases else 'Not specified'}
- Brief Summary: {brief_desc}

Core Study Inclusion Criteria:
{inc_text}

Core Study Exclusion Criteria:
{exc_text}

Translate this study into a compassionate, 6th-to-8th grade plain-English summary with plain participation criteria (inclusions & exclusions) following the exact JSON schema."""

    try:
        content = _chat_completion_with_groq(
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=850,
        )
        data = json.loads(content)
    except Exception as e:
        logger.error(f"Groq study summary generation failed for {study.nct_id}: {e}")
        raise RuntimeError(f"Groq LPU study summary generation failed for {study.nct_id}: {e}")

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    # Parse term explanations
    raw_terms = data.get("complex_terms_explained") or []
    terms_list: list[TermExplanation] = []
    if isinstance(raw_terms, list):
        for t in raw_terms:
            if isinstance(t, dict) and t.get("term") and t.get("plain_english"):
                terms_list.append(TermExplanation(
                    term=str(t["term"]).strip(),
                    plain_english=str(t["plain_english"]).strip(),
                ))

    # Parse plain inclusions and exclusions
    raw_inc = data.get("plain_inclusions") or []
    clean_inc: list[str] = [str(i).strip() for i in raw_inc if str(i).strip()] if isinstance(raw_inc, list) else []

    raw_exc = data.get("plain_exclusions") or []
    clean_exc: list[str] = [str(e).strip() for e in raw_exc if str(e).strip()] if isinstance(raw_exc, list) else []

    return PatientStudySummaryResponse(
        nct_id=study.nct_id,
        trial_title=trial_title,
        plain_title=data.get("plain_title") or f"Study on {conditions_str}",
        what_this_study_is_about=data.get("what_this_study_is_about") or brief_desc or "This study evaluates new medical approaches for this condition.",
        treatment_and_how_it_works=data.get("treatment_and_how_it_works") or f"Researchers are evaluating {interventions_str}.",
        what_participation_involves=data.get("what_participation_involves") or "Participants will attend scheduled clinic check-ups and diagnostic visits.",
        who_can_join_overview=data.get("who_can_join_overview") or f"Adults diagnosed with {conditions_str}.",
        plain_inclusions=clean_inc,
        plain_exclusions=clean_exc,
        complex_terms_explained=terms_list,
        engine="GROQ",
        cached=False,
        execution_time_ms=elapsed_ms,
    )


