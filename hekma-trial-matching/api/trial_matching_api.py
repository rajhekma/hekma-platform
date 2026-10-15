"""
Trial Matching & Search API Router for TrialGPT / Hekma AI.
Exposes the 100% offline rule-based clinical trial matching engine
with 30-day PostgreSQL Cache-Aside support, 30-mile geo-radius search,
and interactive offline eligibility questionnaires ("See if I'm Eligible").
Includes standardized frontend error localization envelope.
"""

from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from trialgpt_lite.service import TrialGPTLiteService
from trialgpt_lite.schemas.study import TrialStudy
from trialgpt_lite.schemas.request import MatchRequest, EligibilityEvaluationRequest
from trialgpt_lite.schemas.match_result import (
    ConditionMatchReport,
    EligibilityQuestionnaireResponse,
    EligibilityEvaluationResponse,
    PatientStudySummaryResponse,
)

router = APIRouter(tags=["Trial Matching & Search"])
service = TrialGPTLiteService()

# TrialGPT P2T uses GET /api/trials/regions — must not be treated as an NCT id.
_RESERVED_NCT_PATH_SEGMENTS = frozenset({"REGIONS", "REGION"})


# --- Standardized Error Envelope for Frontend Localization ---

class ErrorDetail(BaseModel):
    code: str = Field(..., description="Unique machine-readable error code (e.g. ERR_CONDITION_REQUIRED)")
    message: str = Field(..., description="Human-readable technical description")
    localized_key: str = Field(..., description="Frontend i18n translation key (e.g. errors.search.conditionRequired)")
    param: Optional[str] = Field(default=None, description="Request parameter associated with the error")
    status_code: int = Field(default=400, description="HTTP status code")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ErrorResponseEnvelope(BaseModel):
    success: bool = False
    error: ErrorDetail


def create_error_response(
    code: str,
    message: str,
    localized_key: str,
    status_code: int = 400,
    param: Optional[str] = None,
) -> JSONResponse:
    """Creates a uniform JSON error response for frontend i18n localization."""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "localized_key": localized_key,
                "param": param,
                "status_code": status_code,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        },
    )


# --- API Endpoints ---

@router.post(
    "/api/match",
    response_model=ConditionMatchReport,
    responses={
        400: {"model": ErrorResponseEnvelope, "description": "Validation error"},
        500: {"model": ErrorResponseEnvelope, "description": "Internal server error"},
    },
    summary="Match Clinical Trials (Top 10 Results + 30-Mile Proximity)",
)
def match_trials_api(request: MatchRequest):
    """
    Search ClinicalTrials.gov and evaluate patient eligibility against trial protocols.
    Supports streamlined search (Flow 1: Myself, Flow 2: Friend), 30-mile geo-radius proximity,
    and 30-day PostgreSQL Cache-Aside acceleration.
    
    ### Request Fields:
    - **condition**: Medical condition or disease name (required, e.g. 'breast cancer', 'type 2 diabetes').
    - **city_or_zip**: City, State, or US Zip Code for geographic proximity search (e.g. 'Boston, MA', '90210', 'New York'). Automatically geocoded.
    - **search_radius_miles**: Distance radius in miles around city or zip code (default: 30.0 miles).
    - **geo_filter**: Optional geographic filter object (`city_or_zip`, `latitude`, `longitude`, `radius_miles`).
    - **demographics**: Direct `age` and `sex` input (Flow 1: from profile, Flow 2: from user prompt).
    - **page_size**: Number of trials to return per page (default: 10).
    - **page_token**: Token for subsequent pages (`null` for Page 1).
    - **recruiting_only**: Whether to filter for active/recruiting studies (default: true).
    """
    # 1. Validation: Condition Required
    if not request.condition or not request.condition.strip():
        return create_error_response(
            code="ERR_CONDITION_REQUIRED",
            message="Condition query parameter is required.",
            localized_key="errors.search.conditionRequired",
            param="condition",
            status_code=400,
        )

    # 2. Validation: GeoFilter Coordinates & Radius
    if request.geo_filter:
        lat = request.geo_filter.latitude
        lon = request.geo_filter.longitude
        rad = request.geo_filter.radius_miles

        if lat is not None and lon is not None:
            if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                return create_error_response(
                    code="ERR_GEO_INVALID_COORDS",
                    message=f"Invalid geographic coordinates ({lat}, {lon}). Latitude must be [-90, 90] and longitude [-180, 180].",
                    localized_key="errors.location.invalidCoords",
                    param="geo_filter",
                    status_code=400,
                )

        if rad <= 0.0 or rad > 500.0:
            return create_error_response(
                code="ERR_GEO_RADIUS_INVALID",
                message=f"Search radius of {rad} miles is out of bounds. Must be between 1 and 500 miles.",
                localized_key="errors.location.invalidRadius",
                param="geo_filter.radius_miles",
                status_code=400,
            )

    # 3. Validation: Age Limits
    if request.demographics and request.demographics.age is not None:
        age = request.demographics.age
        if age < 0.0 or age > 125.0:
            return create_error_response(
                code="ERR_AGE_INVALID",
                message=f"Age value of {age} is invalid. Must be between 0 and 125.",
                localized_key="errors.search.ageInvalid",
                param="demographics.age",
                status_code=400,
            )

    try:
        return service.search_and_match(request)
    except Exception as e:
        return create_error_response(
            code="ERR_INTERNAL_SERVER_ERROR",
            message=str(e),
            localized_key="errors.system.internalError",
            status_code=500,
        )


@router.get(
    "/api/trials/{nct_id}/questionnaire",
    response_model=EligibilityQuestionnaireResponse,
    responses={
        400: {"model": ErrorResponseEnvelope, "description": "Invalid NCT ID"},
        404: {"model": ErrorResponseEnvelope, "description": "Trial not found"},
        500: {"model": ErrorResponseEnvelope, "description": "Questionnaire generation failed"},
    },
    summary="Get Eligibility Questionnaire (See If I'm Eligible)",
)
def get_trial_questionnaire_api(
    nct_id: str,
    mode: str = Query(default="realtime", description="Questionnaire mode: 'realtime' (Groq LPU) or 'offline' (heuristic rules)"),
    force_refresh: bool = Query(default=False, description="Bypass cache and force re-query from ClinicalTrials.gov"),
):
    """
    Generates a 5 to 7 question patient-friendly eligibility screener.
    - **mode='realtime' (default)**: Rephrases criteria using ultra-fast Groq LPU inference (~250ms),
      cached in PostgreSQL for 30 days.
    - **mode='offline'**: Uses the local heuristic rule-based template generator (zero network calls).
    - **force_refresh**: Bypasses the 30-day PostgreSQL questionnaire cache.
    """
    clean_id = (nct_id or "").strip().upper()
    if not clean_id.startswith("NCT"):
        return create_error_response(
            code="ERR_NCT_ID_INVALID",
            message=f"Invalid ClinicalTrials.gov identifier '{clean_id}'. Must start with 'NCT'.",
            localized_key="errors.trial.invalidNctId",
            param="nct_id",
            status_code=400,
        )

    try:
        return service.get_trial_questionnaire(clean_id, mode=mode, force_refresh=force_refresh)
    except Exception as e:
        err_msg = str(e)
        if "not found" in err_msg.lower():
            return create_error_response(
                code="ERR_TRIAL_NOT_FOUND",
                message=f"Trial '{clean_id}' was not found: {err_msg}",
                localized_key="errors.trial.notFound",
                param="nct_id",
                status_code=404,
            )
        return create_error_response(
            code="ERR_QUESTIONNAIRE_GENERATION_FAILED",
            message=f"Questionnaire generation failed for trial '{clean_id}': {err_msg}",
            localized_key="errors.trial.questionnaireFailed",
            param="nct_id",
            status_code=500,
        )


@router.get(
    "/api/trials/{nct_id}/patient-summary",
    response_model=PatientStudySummaryResponse,
    responses={
        400: {"model": ErrorResponseEnvelope, "description": "Invalid NCT ID"},
        404: {"model": ErrorResponseEnvelope, "description": "Trial not found"},
        500: {"model": ErrorResponseEnvelope, "description": "Internal server error"},
    },
    summary="Get Plain-English Patient Study Summary (Groq LPU Translation & Medical Glossary)",
)
def get_patient_study_summary_api(
    nct_id: str,
    force_refresh: bool = Query(
        default=False,
        description="Bypass PostgreSQL cache and force re-generation via Groq LPU",
    ),
):
    """
    Translates complex ClinicalTrials.gov protocol text into a compassionate,
    6th-8th grade plain-English summary powered by Groq LPU.

    Includes:
    - **plain_title**: A friendly 1-sentence title anyone can understand.
    - **what_this_study_is_about**: Clear explanation of study goals.
    - **treatment_and_how_it_works**: Everyday explanation of medications/procedures.
    - **what_participation_involves**: Clinic visit schedule, tests, and duration.
    - **who_can_join_overview**: High-level eligibility profile.
    - **complex_terms_explained**: Mini-glossary translating scientific or medical jargon.
    """
    clean_id = (nct_id or "").strip().upper()
    if not clean_id.startswith("NCT"):
        return create_error_response(
            code="ERR_NCT_ID_INVALID",
            message=f"Invalid ClinicalTrials.gov identifier '{clean_id}'. Must start with 'NCT'.",
            localized_key="errors.trial.invalidNctId",
            param="nct_id",
            status_code=400,
        )

    try:
        return service.get_patient_study_summary(clean_id, force_refresh=force_refresh)
    except Exception as e:
        return create_error_response(
            code="ERR_TRIAL_NOT_FOUND",
            message=f"Study summary unavailable for '{clean_id}': {str(e)}",
            localized_key="errors.trial.notFound",
            param="nct_id",
            status_code=404,
        )


@router.post(
    "/api/trials/{nct_id}/evaluate-eligibility",
    response_model=EligibilityEvaluationResponse,
    responses={
        400: {"model": ErrorResponseEnvelope, "description": "Invalid answer submission"},
        404: {"model": ErrorResponseEnvelope, "description": "Trial not found"},
        500: {"model": ErrorResponseEnvelope, "description": "Internal server error"},
    },
    summary="Evaluate Patient Answers (Instant 100% Offline Verdict & Doctor Checklist)",
)
def evaluate_trial_eligibility_api(
    nct_id: str,
    payload: EligibilityEvaluationRequest,
):
    """
    Evaluates patient questionnaire answers against study protocol rules in < 1ms.
    
    ### Verdict Outcomes:
    - **ELIGIBLE**: All required criteria met, zero exclusions triggered.
    - **INELIGIBLE**: Violates an exclusion or fails an essential inclusion criterion (shows exact reason).
    - **LIKELY_ELIGIBLE**: General criteria met, but some lab/genetic questions were answered 'NOT_SURE'.
    
    ### Returns:
    - Overall verdict and match score (0.0 to 1.0).
    - Itemized criterion evaluation with patient-friendly justifications.
    - Doctor discussion checklist for the patient's next clinical visit.
    """
    clean_id = (nct_id or "").strip().upper()
    if not payload.answers:
        return create_error_response(
            code="ERR_ANSWERS_EMPTY",
            message="No questionnaire answers were provided. Please answer at least one question.",
            localized_key="errors.questionnaire.emptyAnswers",
            param="answers",
            status_code=400,
        )

    # Validate answer choices
    valid_choices = {"YES", "NO", "NOT_SURE"}
    for ans in payload.answers:
        choice = (ans.answer or "").strip().upper()
        if choice not in valid_choices:
            return create_error_response(
                code="ERR_ANSWERS_INVALID_OPTION",
                message=f"Answer '{ans.answer}' for question '{ans.question_id}' is invalid. Allowed choices: YES, NO, NOT_SURE.",
                localized_key="errors.questionnaire.invalidOption",
                param=f"answers[{ans.question_id}]",
                status_code=400,
            )

    # Ensure NCT ID matches
    payload.nct_id = clean_id

    try:
        return service.evaluate_trial_eligibility(payload)
    except Exception as e:
        return create_error_response(
            code="ERR_TRIAL_NOT_FOUND",
            message=f"Trial '{clean_id}' was not found: {str(e)}",
            localized_key="errors.trial.notFound",
            param="nct_id",
            status_code=404,
        )


@router.get(
    "/api/trials/{nct_id}",
    response_model=TrialStudy,
    responses={
        404: {"model": ErrorResponseEnvelope, "description": "Trial not found"},
    },
    summary="Get Single Trial Protocol Details (14 Sections)",
)
def get_trial_details_api(
    nct_id: str,
    force_refresh: bool = Query(default=False, description="Bypass PostgreSQL cache and force re-query from ClinicalTrials.gov API v2"),
):
    """
    Fetches the complete 14-section protocol for a single clinical trial by its NCT ID.
    Leverages PostgreSQL Cache-Aside with 30-day retention for sub-millisecond protocol loading.
    """
    clean_id = (nct_id or "").strip().upper()
    if clean_id in _RESERVED_NCT_PATH_SEGMENTS:
        return create_error_response(
            code="ERR_ROUTE_CONFLICT",
            message=(
                f"'{clean_id}' is not an NCT id. Use GET /api/trials/regions?disease=... "
                "for P2T location lookup."
            ),
            localized_key="errors.trial.invalidNctId",
            param="nct_id",
            status_code=404,
        )
    try:
        return service.get_study_details(clean_id, force_refresh=force_refresh)
    except Exception as e:
        return create_error_response(
            code="ERR_TRIAL_NOT_FOUND",
            message=f"Trial '{clean_id}' not found: {str(e)}",
            localized_key="errors.trial.notFound",
            param="nct_id",
            status_code=404,
        )


@router.get(
    "/api/cache/stats",
    summary="PostgreSQL Cache-Aside Diagnostics (30-Day Retention)",
)
def get_cache_stats_api():
    """Returns real-time PostgreSQL Cache-Aside metrics (cached queries, patient matches, studies, hit counts)."""
    return service.cache.get_stats()
