"""
TrialGPT Lite Service Orchestrator.
Coordinates ClinicalTrials.gov search, PostgreSQL Cache-Aside (Lazy Loading),
parsing, demographic pre-filtering, 100% offline rule-based matching, and report generation.
"""

import logging
import time
from typing import Optional

from trialgpt_lite.client.ctgov_client import ClinicalTrialsGovClient
from trialgpt_lite.cache.pg_cache import (
    PostgreSQLCache,
    get_pg_cache,
    compute_query_hash,
    compute_match_hash,
)
from trialgpt_lite.parser.study_normalizer import normalize_study
from trialgpt_lite.matcher.fast_filter import evaluate_fast_filter
from trialgpt_lite.matcher.llm_matcher import LLMCriteriaMatcher
from trialgpt_lite.matcher.scorer import score_and_aggregate_trial
from trialgpt_lite.schemas.study import TrialStudy
from trialgpt_lite.schemas.request import MatchRequest, ConditionSearchRequest, EligibilityEvaluationRequest
from trialgpt_lite.schemas.match_result import (
    ConditionMatchReport,
    TrialMatchResult,
    EligibilityQuestionnaireResponse,
    EligibilityEvaluationResponse,
    PatientStudySummaryResponse,
)
from trialgpt_lite.parser.question_generator import (
    generate_offline_questions,
    evaluate_offline_questionnaire,
)
from trialgpt_lite.parser.groq_rephraser import (
    generate_realtime_questions,
    generate_patient_study_summary,
)
from trialgpt_lite.config import DEFAULT_RECRUITMENT_STATUSES


logger = logging.getLogger("trialgpt_lite.service")


def study_has_participation_criteria(study: TrialStudy) -> bool:
    """True when the protocol includes inclusion, exclusion, or raw eligibility text."""
    criteria = getattr(study, "criteria", None)
    if criteria is None:
        return False
    return bool(
        criteria.inclusion_criteria
        or criteria.exclusion_criteria
        or (criteria.raw_text or "").strip()
    )


class TrialGPTLiteService:
    """
    High-level engine for condition-based clinical trial matching with PostgreSQL Cache-Aside.
    """

    def __init__(
        self,
        client: Optional[ClinicalTrialsGovClient] = None,
        matcher: Optional[LLMCriteriaMatcher] = None,
        cache: Optional[PostgreSQLCache] = None,
    ):
        self.client = client or ClinicalTrialsGovClient()
        self.matcher = matcher or LLMCriteriaMatcher()
        self.cache = cache or get_pg_cache()

    def search_and_match(self, request: MatchRequest) -> ConditionMatchReport:
        """
        Executes end-to-end condition search, demographic pre-filter,
        and criterion-level eligibility matching.
        Leverages PostgreSQL Cache-Aside with single-flight mutex stampede protection.
        """
        start_time = time.time()
        logger.info(f"Initiating search and match for condition: '{request.condition}'")

        page_size = request.page_size or request.max_trials or 10
        statuses = DEFAULT_RECRUITMENT_STATUSES if request.recruiting_only else None
        has_patient = bool(request.patient and request.patient.clinical_note)

        # Check Patient Match Cache (30-Day Retention)
        m_hash = None
        if has_patient:
            m_hash = compute_match_hash(
                condition=request.condition,
                patient_note=request.patient.clinical_note if request.patient else None,
                patient_age=request.patient.age if request.patient else None,
                patient_sex=request.patient.sex if request.patient else None,
                statuses=statuses,
                page_size=page_size,
                page_token=request.page_token,
                max_criteria_evals=request.max_criteria_evals,
            )
            if not request.force_refresh and hasattr(self.cache, "get_cached_match"):
                cached_match_data = self.cache.get_cached_match(m_hash)
                if isinstance(cached_match_data, dict) and "trials" in cached_match_data:
                    try:
                        cached_report = ConditionMatchReport.model_validate(cached_match_data)
                        cached_report.cache_hit = True
                        cached_report.execution_time_seconds = round(time.time() - start_time, 3)
                        logger.info(
                            f"[Match Cache-Aside HIT] Serving 30-day cached patient matching report for '{request.condition}' in ~2ms."
                        )
                        return cached_report
                    except Exception as m_ex:
                        logger.warning(f"Error deserializing cached match report: {m_ex}")

        # 1. Canonical query hash for Cache-Aside
        geo_tag = ""
        if request.geo_filter:
            lat = request.geo_filter.latitude
            lon = request.geo_filter.longitude
            rad = request.geo_filter.radius_miles
            if lat is not None and lon is not None:
                geo_tag = f"__geo_{lat:.3f}_{lon:.3f}_{rad:.1f}"
            elif request.geo_filter.city_or_zip:
                geo_tag = f"__loc_{request.geo_filter.city_or_zip.lower().strip()}_{rad:.1f}"

        q_hash = compute_query_hash(
            condition=f"{request.condition}{geo_tag}",
            statuses=statuses,
            page_size=page_size,
            page_token=request.page_token,
        )

        flight_lock = self.cache.get_flight_lock(q_hash)
        cache_hit = False
        normalized_studies: list[TrialStudy] = []
        total_found = 0
        next_token: Optional[str] = None
        query_used = request.condition

        # Single-Flight Mutex: Only one concurrent thread fetches from CT.gov on miss
        with flight_lock:
            # Check cache if not explicitly forced to refresh
            if not request.force_refresh:
                # 1. Try single-roundtrip CTE (fetches query meta + all study protocols together)
                cached_data = None
                if hasattr(self.cache, "get_cached_query_with_studies"):
                    cached_data = self.cache.get_cached_query_with_studies(q_hash)

                if isinstance(cached_data, tuple) and len(cached_data) == 2:
                    cached_q, cached_study_dicts = cached_data
                    total_found = cached_q.get("total_in_registry", 0)
                    next_token = cached_q.get("next_page_token")
                    try:
                        normalized_studies = [TrialStudy.model_validate(s) for s in cached_study_dicts]
                        cache_hit = True
                        logger.info(
                            f"[Cache-Aside HIT] Serving {len(normalized_studies)} trials for '{request.condition}' from PostgreSQL via atomic CTE."
                        )
                    except Exception as ex:
                        logger.warning(f"Error deserializing cached study protocols: {ex}")
                        cache_hit = False
                else:
                    # Fallback to separate query & entity lookups
                    cached_q = self.cache.get_cached_query(q_hash)
                    if cached_q:
                        cached_ncts = cached_q["nct_ids"]
                        total_found = cached_q["total_in_registry"]
                        next_token = cached_q["next_page_token"]
                        cached_studies = self.cache.get_cached_studies(cached_ncts)
                        if len(cached_ncts) == len(cached_studies):
                            try:
                                normalized_studies = [
                                    TrialStudy.model_validate(cached_studies[nid])
                                    for nid in cached_ncts
                                    if nid in cached_studies
                                ]
                                if len(normalized_studies) == len(cached_ncts):
                                    cache_hit = True
                                    logger.info(
                                        f"[Cache-Aside HIT] Serving {len(normalized_studies)} trials for '{request.condition}' from PostgreSQL."
                                    )
                            except Exception as ex:
                                logger.warning(f"Error deserializing cached study protocols: {ex}")
                                cache_hit = False

            # Cache Miss or Force Refresh
            if not cache_hit:
                logger.info(f"[Cache-Aside MISS] Querying ClinicalTrials.gov API v2 for condition: '{request.condition}'")
                try:
                    api_result = self.client.search_by_condition(
                        condition=request.condition,
                        statuses=statuses,
                        page_size=page_size,
                        page_token=request.page_token,
                        count_total=True,
                        auto_relax_on_empty=True,
                        geo_filter=request.geo_filter,
                    )
                    raw_studies = api_result.get("studies", [])
                    total_found = api_result.get("total_count", len(raw_studies))
                    next_token = api_result.get("next_page_token")
                    query_used = api_result.get("query_used", request.condition)
                    normalized_studies = [normalize_study(s) for s in raw_studies]


                    # Cache Population: Store in PostgreSQL for subsequent requests
                    if normalized_studies:
                        # 1. Store individual 14-section study protocols
                        self.cache.set_cached_studies([s.model_dump() for s in normalized_studies])
                        # 2. Store search query mapping and pagination token
                        self.cache.set_cached_query(
                            query_hash=q_hash,
                            condition_raw=request.condition,
                            page_size=page_size,
                            page_token=request.page_token,
                            nct_ids=[s.nct_id for s in normalized_studies],
                            total_in_registry=total_found,
                            next_page_token=next_token,
                        )
                except Exception as api_err:
                    # Edge Case 4: CT.gov outage/rate limit - Graceful Stale Fallback
                    logger.warning(f"CT.gov request failed ({api_err}). Checking for stale PostgreSQL cache fallback...")
                    stale_q = self.cache.get_cached_query(q_hash, allow_expired=True)
                    if stale_q:
                        stale_studies = self.cache.get_cached_studies(stale_q["nct_ids"], allow_expired=True)
                        if stale_studies:
                            normalized_studies = [
                                TrialStudy.model_validate(stale_studies[nid])
                                for nid in stale_q["nct_ids"]
                                if nid in stale_studies
                            ]
                            total_found = stale_q["total_in_registry"]
                            next_token = stale_q["next_page_token"]
                            cache_hit = True
                            logger.warning(
                                f"[Cache-Aside STALE FALLBACK] Served {len(normalized_studies)} trials from PostgreSQL during CT.gov outage."
                            )
                    if not normalized_studies:
                        raise api_err

        if not normalized_studies:
            logger.warning(f"No studies found for condition: '{request.condition}'")
            return ConditionMatchReport(
                searched_condition=request.condition,
                total_trials_in_registry=0,
                retrieved_trials_count=0,
                evaluated_trials_count=0,
                page_size=page_size,
                current_page_token=request.page_token,
                next_page_token=None,
                trials=[],
                cache_hit=cache_hit,
                execution_time_seconds=round(time.time() - start_time, 2),
            )

        # Cached protocols may predate Participation Criteria persistence.
        # Re-fetch those studies from ClinicalTrials.gov and update the cache.
        normalized_studies = self._hydrate_missing_participation_criteria(normalized_studies)

        # 2. Fast Demographic & Status Pre-filtering
        pre_filtered = []
        for study in normalized_studies:
            fast_res = evaluate_fast_filter(
                study=study,
                patient=request.patient,
                recruiting_only=request.recruiting_only,
            )
            pre_filtered.append((study, fast_res))

        # Sort so that studies passing fast filter come first
        pre_filtered.sort(key=lambda x: not x[1].passed)

        # 3. Level 2 Rule-Based Criteria Evaluation (100% Offline / Local)
        has_patient = bool(request.patient and request.patient.clinical_note)
        evaluated_trials: list[TrialMatchResult] = []
        rule_eval_count = 0
        active_matcher = self.matcher

        # Determine criteria evaluation limit (defaults to all candidate trials in the page)
        max_evals = request.max_criteria_evals if request.max_criteria_evals is not None else len(pre_filtered)

        for study, fast_res in pre_filtered:
            evaluations = []

            # Evaluate criteria if trial passed fast filter, patient note exists, and limit not exceeded
            if fast_res.passed and has_patient and rule_eval_count < max_evals:
                logger.info(f"Evaluating criteria for trial {study.nct_id} using offline rule-based engine...")
                evaluations = active_matcher.match_criteria(study=study, patient=request.patient)
                rule_eval_count += 1

            # Aggregate scores and verdicts
            trial_result = score_and_aggregate_trial(
                study=study,
                fast_filter=fast_res,
                evaluations=evaluations,
                has_patient_context=has_patient,
            )
            evaluated_trials.append(trial_result)

        # 4. Final Ranking: Sort by eligibility score descending
        evaluated_trials.sort(key=lambda t: t.eligibility_score, reverse=True)

        elapsed = round(time.time() - start_time, 2)
        logger.info(
            f"Matching completed in {elapsed}s (cache_hit={cache_hit}). Evaluated: {rule_eval_count}, Total retrieved: {len(evaluated_trials)}"
        )

        report = ConditionMatchReport(
            searched_condition=query_used,
            total_trials_in_registry=total_found,
            retrieved_trials_count=len(evaluated_trials),
            evaluated_trials_count=rule_eval_count,
            page_size=page_size,
            current_page_token=request.page_token,
            next_page_token=next_token,
            trials=evaluated_trials,
            cache_hit=cache_hit,
            execution_time_seconds=elapsed,
        )

        # Store in 30-Day Patient Match Cache
        if has_patient and m_hash and hasattr(self.cache, "set_cached_match"):
            try:
                self.cache.set_cached_match(
                    match_hash=m_hash,
                    condition_raw=request.condition,
                    patient_profile=request.patient.model_dump() if request.patient else None,
                    page_size=page_size,
                    page_token=request.page_token,
                    nct_ids=[t.nct_id for t in report.trials],
                    report_data=report.model_dump(),
                )
            except Exception as set_m_ex:
                logger.warning(f"Failed to cache match report in PostgreSQL: {set_m_ex}")

        return report


    def _hydrate_missing_participation_criteria(self, studies: list[TrialStudy]) -> list[TrialStudy]:
        """Fill empty inclusion/exclusion from the live CT.gov protocol and persist the update."""
        hydrated: list[TrialStudy] = []
        updates: list[dict] = []

        for study in studies:
            if study_has_participation_criteria(study):
                hydrated.append(study)
                continue

            try:
                raw_study = self.client.get_study(study.nct_id)
                updated = normalize_study(raw_study)
                if study_has_participation_criteria(updated):
                    logger.info(f"Hydrated Participation Criteria for {study.nct_id} from ClinicalTrials.gov")
                    hydrated.append(updated)
                    updates.append(updated.model_dump())
                    continue
                hydrated.append(updated)
            except Exception as err:
                logger.warning(f"Could not hydrate Participation Criteria for {study.nct_id}: {err}")
                hydrated.append(study)

        if updates:
            try:
                self.cache.set_cached_studies(updates)
            except Exception as cache_err:
                logger.warning(f"Failed to persist hydrated Participation Criteria: {cache_err}")

        return hydrated

    def get_study_details(self, nct_id: str, force_refresh: bool = False) -> TrialStudy:
        """
        Fetches and normalizes a single clinical trial by NCT ID,
        returning all 14 detailed protocol sections.
        Implements PostgreSQL Cache-Aside for sub-millisecond retrieval.
        """
        clean_id = (nct_id or "").strip().upper()

        # Cache-Aside Check
        if not force_refresh:
            cached_proto = self.cache.get_cached_study(clean_id)
            if cached_proto:
                cached_study = TrialStudy.model_validate(cached_proto)
                if study_has_participation_criteria(cached_study):
                    logger.info(f"[Cache-Aside HIT] Protocol for {clean_id} served from PostgreSQL in ~1ms.")
                    return cached_study
                logger.info(
                    f"[Cache-Aside STALE CRITERIA] Protocol for {clean_id} is missing Participation Criteria; refreshing from ClinicalTrials.gov."
                )

        # Cache Miss
        logger.info(f"[Cache-Aside MISS] Fetching protocol {clean_id} from ClinicalTrials.gov API v2.")
        try:
            raw_study = self.client.get_study(clean_id)
            study = normalize_study(raw_study)
            # Store in PostgreSQL cache
            self.cache.set_cached_study(study.model_dump())
            return study
        except Exception as err:
            # Graceful stale fallback on CT.gov error
            stale_proto = self.cache.get_cached_study(clean_id, allow_expired=True)
            if stale_proto:
                logger.warning(f"[Cache-Aside STALE FALLBACK] Protocol {clean_id} served from expired cache during CT.gov error.")
                return TrialStudy.model_validate(stale_proto)
            raise err

    def get_trial_questionnaire(
        self, nct_id: str, mode: str = "realtime", force_refresh: bool = False
    ) -> EligibilityQuestionnaireResponse:
        """
        Generates 5-7 patient-friendly eligibility questions.
        - mode="realtime" (default):
            1. Checks PostgreSQL Cache (Cache-Aside, 30 days)
            2. Rephrases in real-time via dedicated Groq LPU (qwen/qwen3.8-27b, ~250ms).
            3. Stores into PostgreSQL Cache.
        - mode="offline":
            Uses local rule-based template generator if explicitly requested.
        """
        study = self.get_study_details(nct_id, force_refresh=force_refresh)

        if mode == "offline":
            offline_resp = generate_offline_questions(study)
            offline_resp.engine = "OFFLINE"
            return offline_resp

        # 1. Check PostgreSQL Cache
        if not force_refresh:
            cached_data = self.cache.get_cached_questionnaire(nct_id)
            if cached_data:
                logger.info(f"[Cache-Aside HIT] Serving questionnaire for {nct_id} from PostgreSQL.")
                cached_resp = EligibilityQuestionnaireResponse.model_validate(cached_data)
                cached_resp.engine = "CACHE_HIT"
                return cached_resp

        # 2. Real-time generation (Groq LPU -> OpenAI -> Offline fallback)
        resp = generate_realtime_questions(study)

        # 3. Store in PostgreSQL Cache
        try:
            self.cache.set_cached_questionnaire(
                nct_id=nct_id,
                trial_title=resp.trial_title,
                engine=resp.engine,
                questionnaire_data=resp.model_dump(),
            )
        except Exception as cache_err:
            logger.warning(f"Failed to cache questionnaire for {nct_id}: {cache_err}")

        return resp

    def evaluate_trial_eligibility(
        self, request: EligibilityEvaluationRequest
    ) -> EligibilityEvaluationResponse:
        """
        Evaluates patient Yes/No/Not_Sure questionnaire responses against the study protocol rules.
        Re-uses the generated/cached questionnaire questions for accurate matching.
        """
        study = self.get_study_details(request.nct_id)
        questionnaire = self.get_trial_questionnaire(request.nct_id)
        answers_map = {ans.question_id: ans.answer for ans in request.answers}
        return evaluate_offline_questionnaire(study, questionnaire.questions, answers_map)

    def get_patient_study_summary(
        self, nct_id: str, force_refresh: bool = False
    ) -> PatientStudySummaryResponse:
        """
        Generates a comprehensive, patient-friendly plain-English summary of a study
        via dedicated Groq LPU inference, with 30-day PostgreSQL Cache-Aside storage.
        """
        study = self.get_study_details(nct_id, force_refresh=force_refresh)

        # 1. Check PostgreSQL Cache
        if not force_refresh:
            cached_data = self.cache.get_cached_summary(nct_id)
            if cached_data:
                logger.info(f"[Cache-Aside HIT] Serving patient study summary for {nct_id} from PostgreSQL.")
                cached_resp = PatientStudySummaryResponse.model_validate(cached_data)
                cached_resp.cached = True
                cached_resp.engine = "CACHE_HIT"
                return cached_resp

        # 2. Real-time Groq LPU generation
        resp = generate_patient_study_summary(study)

        # 3. Store in PostgreSQL Cache
        try:
            self.cache.set_cached_summary(
                nct_id=nct_id,
                trial_title=resp.trial_title,
                engine=resp.engine,
                summary_data=resp.model_dump(),
            )
        except Exception as cache_err:
            logger.warning(f"Failed to cache patient summary for {nct_id}: {cache_err}")

        return resp



