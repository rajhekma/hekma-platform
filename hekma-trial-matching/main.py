
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, BackgroundTasks, HTTPException,Depends,Request, Query, Response
from pydantic import BaseModel
import os
import json
import uuid
from typing import Union, List, Optional, Literal


# Core
from core.job_helpers import generate_job_id

# Workflows
from workflows.patient_to_trials import run_patient_workflow
from workflows.trial_to_patients import (
    run_trial_to_patients_workflow,
    run_trial_to_patients_workflow_db,
)

from api.batch_summary_api import router as batch_router

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

from api.trial_ingestion_api import router as trial_router
from api.patient_filter_api import router as trial_filters_router
from api.mimic_summary_api import router as mimic_summary_router

from repositories.matching_jobs_repo import create_job
from core.response_builders import build_job_results_response
from core.inference_builders import build_nct_inference_response
from core.inference_builders import build_patient_inference_response
from repositories.matching_jobs_repo import get_job_status
from repositories.matching_jobs_repo import get_jobs_by_query
from repositories.trialgpt_corpus_repo import (
    fetch_all_corpus_locations,
    fetch_locations_by_diseases,
)
from config.trial_gpt_ehr_config import is_trialmatch_standalone_mode
from config.cors_config import resolve_cors_allowlist
from fastapi.middleware.cors import CORSMiddleware
from repositories.mysql_repo import get_subject_id_by_patient_id
from repositories.matching_jobs_repo import find_completed_job_by_parameters
from repositories.trialgpt_corpus_repo import fetch_location_details_by_regions
from services.trial_gpt_ehr_ingest_service import (
    TrialGptEhrIngestError,
    ensure_trial_gpt_ehr_for_p2t,
)
from services.ai_usage import llm_usage_scope
from services.trial_gpt_ehr_read_service import (
    get_patient_ehr_status,
    get_patient_ingest_progress,
    load_patient_diseases_for_ui,
    load_patient_summary_for_ui,
)
from utils.disease_mapping import map_disease_to_ui

from api.patient_annotation_api import router as annotation_router
from api.patient_summary_validation_api import router as patient_summary_validation_router
from api.qdrant_admin_api import router as qdrant_admin_router
from api.trial_gpt_ehr_internal_api import router as trial_gpt_ehr_internal_router
from api.trial_matching_api import router as trial_matching_router





from auth.security import jwt_filter

import nltk

try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt")





app = FastAPI(title="TrialGPT API")



_cors_origins, _cors_origin_regex = resolve_cors_allowlist()
logger.info(
    "CORS | exact_origins=%s | hekma_regex=%s",
    len(_cors_origins),
    "enabled" if _cors_origin_regex else "disabled",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



from utils.llm_config import (
    DEFAULT_WORKFLOW_LLM_SERVICE,
    DEFAULT_WORKFLOW_MODEL,
    resolve_workflow_llm_service,
    resolve_workflow_model,
)

DATASET_DIR = "dataset"
DEFAULT_CORPUS = "sigir"
DEFAULT_MODEL = DEFAULT_WORKFLOW_MODEL
DEFAULT_LLM_SERVICE = DEFAULT_WORKFLOW_LLM_SERVICE

# Request Models



class PatientToTrialsRequest(BaseModel):
    patient_id: str
    selected_disease: Union[str, List[str]]
    selected_region: Union[str, List[str]]
    corpus: Optional[str] = None
    model: Optional[str] = None
    llm_service: Optional[str] = None
    retrieval_mode: Literal["legacy", "rag"] = "rag"
    debug: bool = False
    force_rerun: bool = False


class TrialToPatientsRequest(BaseModel):
    nct_id: str
    site_id: str
    prospective_patient_count: int
    corpus: Optional[str] = DEFAULT_CORPUS
    model: Optional[str] = None
    llm_service: Optional[str] = None
    retrieval_mode: Literal["legacy", "rag"] = "rag"
    debug: bool = False
    force_rerun: bool = False

# Background Runner




app.include_router(batch_router)

app.include_router(trial_router)

app.include_router(annotation_router)
app.include_router(mimic_summary_router)
app.include_router(patient_summary_validation_router)
app.include_router(qdrant_admin_router)
app.include_router(trial_gpt_ehr_internal_router)
# trial_matching_router is registered after GET /api/trials/regions (see below) so
# /api/trials/regions is not captured by /api/trials/{nct_id}.
#app.include_router(trial_filters_router)



@app.on_event("startup")
def _startup_bootstrap():
    """Ensure DB schema and optional Qdrant auto-ingest on pod start."""
    from repositories.trialgpt_schema_bootstrap import ensure_trialgpt_schema
    from services.qdrant_auto_ingest_service import maybe_start_background_ingest
    from services.trialgpt_corpus_seed_service import maybe_seed_trialgpt_corpus_from_dev

    try:
        ensure_trialgpt_schema()
    except Exception:
        logger.exception("TrialGPT table bootstrap failed on startup")
        raise

    # One-shot only. Later calls in this process and later boots with a
    # seed marker or COUNT(*)==2508 do not copy again.
    maybe_seed_trialgpt_corpus_from_dev()

    maybe_start_background_ingest()





# Health

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/schema")
def health_schema():
    """Show which TrialGPT tables exist. Safe to call after deploy; no PHI."""
    from repositories.trialgpt_schema_bootstrap import schema_status

    return schema_status()


# JOB-BASED APIs



@app.post("/api/patient-to-trials/start")
def start_patient_to_trials(
    req: PatientToTrialsRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user = Depends(jwt_filter)
):
    requested_user_id = user["userId"]

    user_type_raw = request.headers.get("logged-in-user-type")

    if not user_type_raw:
        raise HTTPException(status_code=400, detail="User type header missing")

    role_map = {
        "Patient": "PATIENT",
        "Sponsor": "SPONSOR",
        "Site": "SITE",
    }

    user_type = role_map.get(user_type_raw, user_type_raw.upper())

    subject_id = get_subject_id_by_patient_id(req.patient_id)

    if not subject_id:
        raise HTTPException(status_code=404, detail="Subject ID not found for given patient")

    job_parameters = req.dict()

    # Cache first: identical matching inputs should not re-run LLM / RAG.
    # force_rerun is ignored in the fingerprint so false can reuse a true run.
    if not req.force_rerun:
        existing_job_id = find_completed_job_by_parameters(
            query_id=subject_id,
            flow_type="P2T",
            parameters=job_parameters,
        )
        if existing_job_id:
            return {
                "job_id": existing_job_id,
                "flow_type": "P2T",
                "status": "COMPLETED",
                "cached": True,
                "message": "Returning cached result for identical request",
            }

    # Gate: always ingest Fasten → trial_gpt_ehr before a fresh P2T run.
    try:
        with llm_usage_scope(
            patient_id=str(req.patient_id),
            product="trial_match",
            feature="trial_match.ehr_ingest",
            source_service="hekma-trialgpt",
        ):
            ingest_result = ensure_trial_gpt_ehr_for_p2t(req.patient_id)
        logging.getLogger(__name__).info(
            "trial_gpt_ehr gate | patient_id=%s | status=%s | modes=%s",
            req.patient_id,
            ingest_result.status,
            ingest_result.modes_written,
        )
    except TrialGptEhrIngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    job_id = generate_job_id()

    # Create job in DB
    create_job(
        job_id=job_id,
        flow_type="P2T",
        requested_user_id=requested_user_id,
        user_type=user_type,
        query_id=subject_id,
        parameters=job_parameters,
    )
    #selected_region_details = fetch_location_details_by_regions(req.selected_region)
    # Start internal workflow immediately in background
    corpus = req.corpus or DEFAULT_CORPUS
    model = resolve_workflow_model(req.model)
    llm_service = resolve_workflow_llm_service(req.llm_service)

    background_tasks.add_task(
        run_patient_workflow,
        job_id,
        {
            "patient_id": subject_id,
            "hekma_patient_id": str(req.patient_id),
            "selected_disease": req.selected_disease,
            "selected_region": req.selected_region,
            "retrieval_mode": req.retrieval_mode,
            "debug": req.debug,
            #"selected_region_details": selected_region_details
        },
        corpus,
        model,
        llm_service,
    )
    return {
        "job_id": job_id,
        "flow_type": "P2T",
        "status": "STARTED",
        "cached": False,
    }




@app.get("/api/jobs/{job_id}/status")
def get_job_status_public(job_id: str, user = Depends(jwt_filter)):

    job = get_job_status(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job["job_id"],
        "flow_type": job["flow_type"],
        "status": job["status"],
        "compose_status": job["compose_status"],
        "retrieve_status": job["retrieve_status"],
        "evaluate_status": job["evaluate_status"],
        "rank_status": job["rank_status"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "completed_at": job["completed_at"],
        "error": job["error"],
        "error_stage": job["error_stage"],
    }

@app.get("/api/jobs/{job_id}/results")
def get_results(job_id: str, user = Depends(jwt_filter)):

    try:
        job = get_job_status(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        flow_type = job.get("flow_type") or "P2T"
        result = build_job_results_response(job_id, flow_type=flow_type, job=job)
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs/{job_id}/nct-inference")
def get_nct_inference(job_id: str, nct_id: str):

    try:
        return build_nct_inference_response(job_id, nct_id)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trial-to-patients/start")
def start_trial_to_patients(
    req: TrialToPatientsRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user = Depends(jwt_filter)
):
    requested_user_id = user["userId"]

    user_type_raw = request.headers.get("logged-in-user-type")

    if not user_type_raw:
        raise HTTPException(status_code=400, detail="User type header missing")

    role_map = {
        "Patient": "PATIENT",
        "Sponsor": "SPONSOR",
        "Site": "SITE",
        "Administrator": "ADMIN"
    }

    user_type = role_map.get(user_type_raw, user_type_raw.upper())

    job_parameters = req.dict()

    # Response cache: reuse the most recent COMPLETED job with identical parameters
    # instead of re-running retrieval + LLM matching/aggregation. Callers can force a
    # fresh run (e.g. after trial/patient data changes) with force_rerun=true.
    existing_job_id = None
    if not req.force_rerun:
        existing_job_id = find_completed_job_by_parameters(
            query_id=req.nct_id,
            flow_type="T2P",
            parameters=job_parameters,
        )

    if existing_job_id:
        return {
            "job_id": existing_job_id,
            "flow_type": "T2P",
            "status": "COMPLETED",
            "cached": True,
            "message": "Returning cached result for identical request",
        }

    job_id = generate_job_id()

    create_job(
        job_id=job_id,
        flow_type="T2P",
        requested_user_id=requested_user_id,
        user_type=user_type,
        query_id=req.nct_id,
        parameters=job_parameters,
    )

    
    background_tasks.add_task(
        run_trial_to_patients_workflow_db,
        job_id,
    )

    return {
        "job_id": job_id,
        "flow_type": "T2P",
        "status": "STARTED",
        "cached": False,
        "message": "Patient retrieval initiated"
    }


@app.get("/api/jobs/{job_id}/patient-inference")
def get_patient_inference(job_id: str, patient_id: str,user = Depends(jwt_filter)):


    # Keep API contract unchanged: patient_id query param can be either
    # external patientId (legacy client behavior) or subject UUID (T2P results).
    subject_id = None
    try:
        uuid.UUID(str(patient_id))
        subject_id = patient_id
    except (ValueError, TypeError):
        subject_id = get_subject_id_by_patient_id(patient_id)

    if not subject_id:
        raise HTTPException(404, "Subject ID not found")


    try:
        return build_patient_inference_response(job_id, subject_id)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/api/trials/regions")
def get_regions(
    disease: Union[str, List[str]] = Query(...),
    user=Depends(jwt_filter),
):
    try:
        regions = fetch_locations_by_diseases(disease)
    except Exception as exc:
        logger.exception("fetch_locations_by_diseases failed | disease=%s", disease)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    match_mode = "disease"
    if not regions:
        if is_trialmatch_standalone_mode():
            regions = fetch_all_corpus_locations()
            if regions:
                match_mode = "all_corpus"
    return {"regions": regions, "match_mode": match_mode}


app.include_router(trial_matching_router)


def _build_diseases_payload(diseases: list, icd_entries: list) -> list:
    """Map condition names to UI payload; attach ICD-10 when Fasten/LLM has it."""
    by_name: dict = {}
    for entry in icd_entries or []:
        name = (entry or {}).get("official_name")
        if not name:
            continue
        by_name[str(name).lower()] = entry
    if diseases:
        payload = []
        for name in diseases:
            entry = by_name.get(str(name).lower()) or {}
            payload.append(
                {
                    "name": name,
                    "icd10_code": entry.get("icd10_code"),
                    "input": entry.get("input") or name,
                    "ui_label": map_disease_to_ui(entry.get("official_name") or name),
                }
            )
        return payload
    return [
        {
            "name": entry.get("official_name"),
            "icd10_code": entry.get("icd10_code"),
            "input": entry.get("input"),
            "ui_label": map_disease_to_ui(entry.get("official_name", "")),
        }
        for entry in (icd_entries or [])
        if entry.get("official_name")
    ]


@app.get("/api/patient/{patient_id}/ehr-status")
def get_patient_ehr_status_api(patient_id: str, user=Depends(jwt_filter)):
    """Poll trial_gpt_ehr ingest progress (LLM summary can take 1–2 minutes)."""
    subject_id = get_subject_id_by_patient_id(patient_id)
    if not subject_id:
        raise HTTPException(404, "Subject ID not found")
    try:
        return get_patient_ehr_status(patient_id)
    except TrialGptEhrIngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/api/patient/{patient_id}/ehr-ingest-progress")
def get_patient_ehr_ingest_progress_api(patient_id: str, user=Depends(jwt_filter)):
    """
    Detailed ingest progress for Trial Match UI (stage, percent, ETA).

    Prefer this over /diseases while ehr_status is preparing.
    Auto-retries failed or missing ingest when Fasten data is present.
    """
    subject_id = get_subject_id_by_patient_id(patient_id)
    if not subject_id:
        raise HTTPException(404, "Subject ID not found")
    try:
        return get_patient_ingest_progress(patient_id)
    except TrialGptEhrIngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/api/patient/{patient_id}/diseases")
def get_patient_diseases_api(
    patient_id: str,
    response: Response,
    wait: bool = Query(
        False,
        description="If true, block until Fasten→trial_gpt_ehr ingest completes (slow; for Postman).",
    ),
    user=Depends(jwt_filter),
):
    """Return conditions from fastenhealth_condition (EHR, manual, and scan)."""
    subject_id = get_subject_id_by_patient_id(patient_id)

    if not subject_id:
        raise HTTPException(404, "Subject ID not found")

    try:
        prep = load_patient_diseases_for_ui(
            patient_id=patient_id,
            subject_id=subject_id,
            sync=wait,
        )
    except TrialGptEhrIngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    ehr_status = prep.get("ehr_status", "ready")
    diseases = prep.get("diseases") or []
    icd_entries = prep.get("icd_entries") or []
    ingest_result = prep.get("ingest_result")

    if ehr_status == "preparing":
        response.headers["Retry-After"] = "15"
        progress = prep.get("progress") or {}
        payload = {
            "patient_id": patient_id,
            "source": "fastenhealth_condition",
            "ehr_status": "preparing",
            "diseases": [],
            "message": progress.get(
                "message",
                "Building your health profile from EHR data. Retry in 15–30 seconds.",
            ),
            "retry_after_seconds": progress.get("retry_after_seconds", 15),
            "retry_cooldown_seconds_remaining": progress.get(
                "retry_cooldown_seconds_remaining"
            ),
            "stage": progress.get("stage"),
            "progress_percent": progress.get("progress_percent"),
            "estimated_seconds_remaining": progress.get("estimated_seconds_remaining"),
            "fasten_ready": progress.get("fasten_ready"),
            "retry_scheduled": progress.get("retry_scheduled"),
            "error": progress.get("error"),
            "error_display": progress.get("error_display"),
        }
        return payload

    if not diseases:
        raise HTTPException(
            status_code=404,
            detail="No diseases found in Fasten condition records for this patient",
        )

    payload = _build_diseases_payload(diseases, icd_entries)
    result = {
        "patient_id": patient_id,
        "diseases": payload,
        "source": prep.get("disease_source") or "fastenhealth_condition",
        "ehr_status": "ready",
    }
    if prep.get("cached"):
        result["cached"] = True
    if ingest_result is not None:
        result["ingest_status"] = ingest_result.status
    return result





# @app.get("/api/patient/{patient_id}/diseases")
# def get_patient_diseases_api(patient_id: str,user = Depends(jwt_filter)):

#     subject_id = get_subject_id_by_patient_id(patient_id)

#     if not subject_id:
#         raise HTTPException(404, "Subject ID not found")

#     diseases = get_patient_diseases(subject_id)

#     if not diseases:
#         raise HTTPException(status_code=404, detail="No diseases found")

#     return {
#         "patient_id": patient_id,
#         "diseases": diseases
#     }



@app.get("/api/jobs")
def get_jobs(
    patient_id: str | None = Query(None),
    nct_id: str | None = Query(None),
    user = Depends(jwt_filter)
):

    requested_user_id = user["userId"]

    if patient_id and nct_id:
        raise HTTPException(
            status_code=400,
            detail="Pass either patient_id or nct_id, not both."
        )

    if not patient_id and not nct_id:
        raise HTTPException(
            status_code=400,
            detail="Either patient_id or nct_id is required."
        )

    if patient_id:
        subject_id = get_subject_id_by_patient_id(patient_id)

        if not subject_id:
            raise HTTPException(
                status_code=404,
                detail="Subject ID not found for given patient"
            )
        
        rows = get_jobs_by_query(
            query_id=subject_id,
            flow_type="P2T",
            #requested_user_id=requested_user_id
        )
    else:
        rows = get_jobs_by_query(
            query_id=nct_id,
            flow_type="T2P",
            #requested_user_id=requested_user_id
        )

    jobs = []

    for row in rows:
        jobs.append({
        "job_id": row["job_id"],
        "flow_type": row["flow_type"],
        #"requested_user_id": row["requested_user_id"],
        "user_type": row["user_type"],
        "parameters": row["parameters"] if isinstance(row["parameters"], dict) else json.loads(row["parameters"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],        
        })

    return jobs



@app.get("/api/patient/{patient_id}/summary")
def get_patient_summary_api(
    patient_id: str,
    response: Response,
    wait: bool = Query(False, description="Block until ingest completes (slow)."),
    user=Depends(jwt_filter),
):
    """Return patient summary_text from trial_gpt_ehr."""
    subject_id = get_subject_id_by_patient_id(patient_id)

    if not subject_id:
        raise HTTPException(
            status_code=404,
            detail="Subject ID not found for given patient"
        )

    try:
        prep = load_patient_summary_for_ui(
            patient_id=patient_id,
            subject_id=subject_id,
            sync=wait,
        )
    except TrialGptEhrIngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if prep.get("ehr_status") == "preparing":
        response.headers["Retry-After"] = "15"
        return {
            "patient_id": patient_id,
            "source": "trial_gpt_ehr",
            "ehr_status": "preparing",
            "summary": None,
            "message": "Building your health profile from EHR data.",
            "retry_after_seconds": 15,
        }

    summary = prep.get("summary")
    ingest_result = prep.get("ingest_result")

    if not summary:
        raise HTTPException(
            status_code=404,
            detail="Patient summary not found in trial_gpt_ehr"
        )

    result = {
        "patient_id": patient_id,
        "summary": summary,
        "source": "trial_gpt_ehr",
        "ehr_status": "ready",
    }
    if prep.get("cached"):
        result["cached"] = True
    if ingest_result is not None:
        result["ingest_status"] = ingest_result.status
    return result



@app.get("/api/patient/{patient_id}/jobs-with-results")
def get_patient_jobs_with_results(
    patient_id: str,
    user=Depends(jwt_filter)
):

    subject_id = get_subject_id_by_patient_id(patient_id)

    if not subject_id:
        raise HTTPException(
            status_code=404,
            detail="Subject ID not found"
        )

    rows = get_jobs_by_query(
        query_id=subject_id,
        flow_type="P2T"
    )

    jobs = []

    for row in rows:

        job_data = {
            "job_id": row["job_id"],
            "flow_type": row["flow_type"],
            "user_type": row["user_type"],
            "parameters": row["parameters"]
                if isinstance(row["parameters"], dict)
                else json.loads(row["parameters"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"]
        }

        if row["status"] == "COMPLETED":
            try:
                results = build_job_results_response(
                    row["job_id"],
                    flow_type=row.get("flow_type") or "P2T",
                )
                job_data["results"] = results
            except Exception:
                job_data["results"] = None

        jobs.append(job_data)

    return {
        "patient_id": patient_id,
        "jobs": jobs
    }
