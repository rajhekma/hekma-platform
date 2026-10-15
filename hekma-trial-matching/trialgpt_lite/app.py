"""
FastAPI Web Application & UI Server for TrialGPT Lite.
Serves interactive matching dashboard and REST API.
"""

import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from trialgpt_lite.service import TrialGPTLiteService
from trialgpt_lite.schemas.study import TrialStudy
from trialgpt_lite.schemas.request import MatchRequest, EligibilityEvaluationRequest
from trialgpt_lite.schemas.match_result import (
    ConditionMatchReport,
    EligibilityQuestionnaireResponse,
    EligibilityEvaluationResponse,
    PatientStudySummaryResponse,
)


import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger("trialgpt_lite.app")

service = TrialGPTLiteService()
from trialgpt_lite.monitor.service import RegistryMonitorService
monitor_service = RegistryMonitorService()

# Automatic background sync worker interval in seconds (default: every 2 hours)
SYNC_INTERVAL_SECONDS = int(os.getenv("REGISTRY_AUTO_SYNC_INTERVAL_SECONDS", "7200"))


async def background_registry_sync_loop():
    """
    Background worker that runs automatically in the background.
    Periodically fetches and saves daily snapshots from ClinicalTrials.gov without requiring manual actions.
    """
    logger.info("Starting automatic ClinicalTrials.gov registry background sync loop...")
    while True:
        try:
            # Run in threadpool so it doesn't block async event loop
            metrics = await asyncio.to_thread(monitor_service.get_metrics, force_refresh=True)
            logger.info(
                f"[Auto-Sync] ClinicalTrials.gov snapshot updated: "
                f"{metrics.get('total_recruiting')} recruiting | "
                f"+{metrics.get('newly_added', {}).get('last_24h')} new | "
                f"{metrics.get('updated_studies', {}).get('last_24h')} updated"
            )

            # Event-Driven Cache Invalidation: Invalidate cached studies updated in the last 24h
            try:
                updated_studies = await asyncio.to_thread(monitor_service.get_feed, feed_type="updated", days=1, limit=100)
                updated_ncts = [s["nct_id"] for s in updated_studies if "nct_id" in s]
                if updated_ncts:
                    inv_count = await asyncio.to_thread(service.cache.invalidate_studies, updated_ncts)
                    logger.info(f"[Auto-Sync] Invalidated {inv_count} updated protocols from PostgreSQL cache.")
                
                # Auto-prune expired queries and stale studies
                prune_res = await asyncio.to_thread(service.cache.prune_expired)
                logger.info(f"[Auto-Sync] Cache pruning completed: {prune_res}")
            except Exception as cache_err:
                logger.warning(f"[Auto-Sync] Non-critical cache maintenance warning: {cache_err}")
        except Exception as e:
            logger.error(f"[Auto-Sync] Error during scheduled registry sync: {e}")
        
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start background automatic sync task
    sync_task = asyncio.create_task(background_registry_sync_loop())
    yield
    # Shutdown: cancel task cleanly
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass


tags_metadata = [
    {
        "name": "Trial Matching & Search",
        "description": (
            "Primary clinical trial search and 100% offline rule-based patient matching. "
            "Returns 11 Primary Output Fields (NCT ID, Title, Condition, Recruitment status, Phase, "
            "Study type, Intervention, Age, Sex, Location, Match status/reasons) and 14 detailed "
            "protocol sections (Overview, Condition, Treatment, Eligibility, Age/Sex, Study Design, "
            "Phase, Enrollment, Sponsor, Locations, Timeline, Outcomes, Contact, ClinicalTrials.gov)."
        ),
    },
    {
        "name": "Registry Monitoring",
        "description": (
            "Monitor live study volume, daily newly added studies, and weekly updates for "
            "ClinicalTrials.gov studies with status=RECRUITING. Automatic background sync included."
        ),
    },
    {
        "name": "System Health",
        "description": "System health and diagnostic status.",
    },
]

app = FastAPI(
    title="TrialGPT Lite API",
    description=(
        "### Clinical Trial Matching & Live Registry Monitor\n\n"
        "- **100% Offline Rule-Based Matcher**: Zero external LLMs, zero API keys.\n"
        "- **11 Primary Output Fields**: NCT ID, Trial Title, Condition, Recruitment Status, Phase, Study Type, Intervention, Age, Sex, Location, Match Status/Reasons.\n"
        "- **14 Detailed Protocol Sections**: Overview, Condition, Treatment, Eligibility, Age/Sex, Study Design, Phase, Enrollment, Sponsor, Locations, Timeline, Outcomes, Contact, ClinicalTrials.gov link.\n"
        "- **Live Monitoring**: Real-time tracking of ClinicalTrials.gov `status=RECRUITING` data."
    ),
    version="1.0.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

# Enable CORS for external frontend integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/ui") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

ui_dir = Path(__file__).parent / "ui"

# Mount static UI files (css, js)
app.mount("/ui", StaticFiles(directory=str(ui_dir)), name="ui")


@app.get("/", include_in_schema=False)
async def serve_ui():
    """Serves the main interactive dashboard."""
    index_file = ui_dir / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="UI index.html not found.")
    return FileResponse(index_file)


@app.get("/api/health", tags=["System Health"], summary="Service Health Check")
async def health_check():
    """Health check endpoint confirming engine, CTGov API connectivity, and PostgreSQL Cache status."""
    cache_stats = service.cache.get_stats()
    return {
        "status": "online",
        "engine": "TrialGPT Lite (100% Offline Heuristic)",
        "api_source": "ClinicalTrials.gov API v2",
        "cache": cache_stats,
    }


@app.get("/api/cache/stats", tags=["System Health"], summary="PostgreSQL Cache-Aside Diagnostics")
async def get_cache_diagnostics():
    """Returns real-time PostgreSQL Cache-Aside metrics (cached queries, studies, hit counts)."""
    return service.cache.get_stats()



@app.post(
    "/api/match",
    response_model=ConditionMatchReport,
    tags=["Trial Matching & Search"],
    summary="Match Clinical Trials (Top 10 Results + Pagination Support)",
)
async def match_trials(request: MatchRequest):
    """
    Search ClinicalTrials.gov and evaluate patient eligibility against trial protocols.
    
    ### Search & Geographic Proximity (Geo Proximity):
    - **condition**: Target disease or medical condition (e.g. `Non-Small Cell Lung Cancer`).
    - **city_or_zip**: City & State (e.g., `Boston, MA`) or 5-digit US Zip Code (e.g., `90210`). Automatically geocoded to GPS coordinates on the backend.
    - **search_radius_miles**: Proximity search radius around the specified location in miles (default: `30.0`).
    - **geo_filter**: Optional explicit GPS coordinates filter object (`city_or_zip`, `latitude`, `longitude`, `radius_miles`).

    ### Pagination Behavior:
    - **Single Match / Default Page**: Returns the **top 10 results** (`page_size=10`).
    - **Subsequent Pages**: Use `next_page_token` received in the response and pass it as `page_token` in the next request body to fetch the next 10 results.
    - When `next_page_token` is `null`, there are no further studies.
    
    ### Primary Output Fields in Each Trial:
    1. **NCT ID**: ClinicalTrials.gov identifier with direct URL
    2. **Trial title**: Full study title
    3. **Condition**: Targeted medical conditions / diseases
    4. **Recruitment status**: Overall study recruitment status (e.g. RECRUITING)
    5. **Phase**: Trial phase (PHASE1, PHASE2, PHASE3, PHASE4, etc.)
    6. **Study type**: Study type (INTERVENTIONAL, OBSERVATIONAL)
    7. **Intervention**: Drug, biological, or behavioral interventions
    8. **Age**: Eligibility age bounds (e.g. '≥ 18 Years', 'All Ages')
    9. **Sex**: Gender restrictions (e.g. 'All / Both', 'Female Only')
    10. **Location**: Primary facility, city, state, country summary
    11. **Match status/reasons**: Overall verdict (`ELIGIBLE`, `LIKELY_ELIGIBLE`, `INELIGIBLE`, `ACTIVE`) with detailed evidence justification

    ### 14 Detailed Protocol Sections (under 'trials[i]'):
    - **Overview**: Brief study summary
    - **Condition**: Disease list
    - **Treatment**: Detailed interventions (type, name, description)
    - **Eligibility**: Criteria evaluations with sentence citations and inclusion/exclusion verdicts
    - **Age/Sex**: Demographics criteria (min/max age, sex, healthy volunteers)
    - **Study Design**: Allocation, intervention model, masking, primary purpose
    - **Phase**: Study phase
    - **Enrollment**: Planned participant count and enrollment type
    - **Sponsor**: Lead sponsor & collaborating organizations
    - **Locations**: Complete list of research facilities, cities, states, and countries
    - **Timeline**: Start date, primary completion date, study completion date, posted dates
    - **Outcomes**: Primary and secondary outcome measures with time frames
    - **Contact**: Central contacts (phone, email) & Principal Investigators
    - **ClinicalTrials.gov**: Direct web link
    """
    try:
        report = service.search_and_match(request)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/api/trials/{nct_id}",
    response_model=TrialStudy,
    tags=["Trial Matching & Search"],
    summary="Get Single Trial Protocol Details (14 Sections)",
)
async def get_trial_details(nct_id: str, force_refresh: bool = False):
    """
    Fetches the complete 14-section protocol for a single clinical trial by its NCT ID.
    Leverages PostgreSQL Cache-Aside for sub-millisecond protocol loading.
    
    ### Parameters:
    - **nct_id**: ClinicalTrials.gov identifier (e.g. `NCT05801029`)
    - **force_refresh**: Bypass PostgreSQL cache and fetch fresh from ClinicalTrials.gov API v2.
    
    ### Returns All 14 Sections:
    1. Overview (Brief summary)
    2. Condition (Disease list)
    3. Treatment (Detailed interventions with types and descriptions)
    4. Eligibility (Inclusion and exclusion criteria)
    5. Age/Sex (Eligibility demographics)
    6. Study Design (Allocation, intervention model, masking, primary purpose)
    7. Phase (Phase classification and study type)
    8. Enrollment (Planned participant enrollment)
    9. Sponsor (Lead sponsor and collaborators)
    10. Locations (Facilities, cities, states, countries, and site statuses)
    11. Timeline (Start date, completion date, first posted, last update)
    12. Outcomes (Primary and secondary outcome measures)
    13. Contact (Central contacts and Principal Investigators)
    14. ClinicalTrials.gov (NCT web URL)
    """
    try:
        return service.get_study_details(nct_id, force_refresh=force_refresh)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Trial '{nct_id}' not found: {str(e)}")


@app.get(
    "/api/trials/{nct_id}/questionnaire",
    response_model=EligibilityQuestionnaireResponse,
    tags=["Trial Matching & Search"],
    summary="Get Eligibility Questionnaire (See If I'm Eligible)",
)
async def get_trial_questionnaire(
    nct_id: str,
    mode: str = "realtime",
    force_refresh: bool = False,
):
    """
    Generates 5 to 7 patient-friendly eligibility questions in 6th-8th grade English.
    - **mode='realtime' (default)**: Rephrases criteria using ultra-fast Groq LPU inference (~250ms),
      with automatic failover to OpenAI / Offline rule generator, cached in PostgreSQL for 30 days.
    - **mode='offline'**: Uses the local heuristic rule-based template generator.
    - **force_refresh**: Bypasses the 30-day PostgreSQL questionnaire cache.
    """
    try:
        return service.get_trial_questionnaire(nct_id, mode=mode, force_refresh=force_refresh)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Trial '{nct_id}' questionnaire unavailable: {str(e)}")


@app.get(
    "/api/trials/{nct_id}/patient-summary",
    response_model=PatientStudySummaryResponse,
    tags=["Trial Matching & Search"],
    summary="Get Plain-English Patient Study Summary (Groq LPU Translation & Medical Glossary)",
)
async def get_patient_study_summary(
    nct_id: str,
    force_refresh: bool = False,
):
    """
    Translates complex ClinicalTrials.gov protocol text into a compassionate, 
    6th-8th grade plain-English summary powered by Groq LPU with ~250ms latency.
    
    Includes:
    - **plain_title**: A friendly 1-sentence title anyone can understand.
    - **what_this_study_is_about**: Clear explanation of study goals.
    - **treatment_and_how_it_works**: Everyday explanation of medications/procedures (e.g. lebrikizumab).
    - **what_participation_involves**: Clinic visit schedule, tests, and duration.
    - **who_can_join_overview**: High-level eligibility profile.
    - **complex_terms_explained**: Mini-glossary translating every scientific, pharmaceutical, or medical jargon term.
    """
    try:
        return service.get_patient_study_summary(nct_id, force_refresh=force_refresh)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Study summary unavailable for '{nct_id}': {str(e)}")



@app.post(
    "/api/trials/{nct_id}/evaluate-eligibility",
    response_model=EligibilityEvaluationResponse,
    tags=["Trial Matching & Search"],
    summary="Evaluate Patient Answers (Instant 100% Offline Verdict & Doctor Checklist)",
)
async def evaluate_trial_eligibility(nct_id: str, payload: EligibilityEvaluationRequest):
    """Evaluates patient Yes/No/Not_Sure questionnaire responses 100% offline in < 1ms."""
    try:
        payload.nct_id = nct_id
        return service.evaluate_trial_eligibility(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/registry/metrics", tags=["Registry Monitoring"], summary="Live Registry Metrics")

async def get_registry_metrics(force_refresh: bool = False):
    """
    Returns live statistics on ClinicalTrials.gov studies with status=RECRUITING:
    - **Total recruiting volume**
    - **Newly added studies** (last 24 hours, last 7 days, daily average)
    - **Updated studies** (last 24 hours, last 7 days, daily average)
    - **NLM update schedule and timestamp**
    """
    try:
        return monitor_service.get_metrics(force_refresh=force_refresh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/registry/feed", tags=["Registry Monitoring"], summary="Live Registry Studies Feed")
async def get_registry_feed(
    type: str = "new",
    days: int = 7,
    limit: int = 25,
):
    """
    Returns a live feed of recruiting trials that are:
    - **'new'**: newly posted to the registry within the date range
    - **'updated'**: protocol amendments or status updates within the date range
    """
    if type not in ["new", "updated"]:
        raise HTTPException(status_code=400, detail="type parameter must be 'new' or 'updated'")
    try:
        return monitor_service.get_feed(feed_type=type, days=days, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/registry/history", tags=["Registry Monitoring"], summary="Historical Snapshots Trend")
async def get_registry_history(limit_days: int = 30):
    """Returns persistent daily snapshots from SQLite for trend graphs and audit logging."""
    try:
        return monitor_service.get_trend_history(limit_days=limit_days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def start():
    """Entry point to launch the UI server."""
    import uvicorn
    port = int(os.getenv("PORT", "8050"))
    print(f"\n=======================================================")
    print(f"🚀 TrialGPT Lite Web UI is running at: http://localhost:{port}")
    print(f"=======================================================\n")
    uvicorn.run("trialgpt_lite.app:app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    start()
