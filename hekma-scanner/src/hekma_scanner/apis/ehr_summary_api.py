"""
EHR Summary API
===============
Endpoints:
  POST /api/patients/ehr-summary
  POST /api/patients/ehr-summary/download
  DELETE /api/patients/{patient_id}/ehr-summary/cache
  GET /api/patients/ehr-summary/cache-stats

Log levels used
---------------
INFO  — every inbound request, outcome (HIT/MISS), total wall time
DEBUG — request body details, response size
ERROR — exceptions caught at the API boundary
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response

from ..auth.patient_access import (
    assert_summary_access,
    require_patient_access,
    require_staff,
)
from ..auth.security import jwt_filter
from ..fasten_health.ehr_summary_cache_repo import (
    get_cache_stats,
    invalidate_cached_summary,
)
from ..fasten_health.ehr_summary_html_renderer import render_html
from ..fasten_health.ehr_summary_service import EHRSummaryService
from ..schemas.ehr_summary_schemas import EHRSummaryRequest, EHRSummaryResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patients", tags=["EHR Summary"])

_service: EHRSummaryService | None = None


def _get_service() -> EHRSummaryService:
    global _service
    if _service is None:
        _service = EHRSummaryService()
    return _service


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_summary(
    request: EHRSummaryRequest,
    force_refresh: bool = False,
    include_records: bool = False,
    cache_only: bool = False,
    req_id: str = "",
) -> EHRSummaryResponse:
    if not request.patient_id and not request.email:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of 'patient_id' or 'email'.",
        )
    try:
        return _get_service().generate(
            patient_id=request.patient_id,
            email=request.email,
            force_refresh=force_refresh,
            include_records=include_records,
            cache_only=cache_only,
            req_id=req_id,
        )
    except LookupError as exc:
        msg = str(exc)
        if "No cached EHR summary" in msg:
            logger.warning("req_id=%s | cache required but missing | detail=%s", req_id, msg)
            raise HTTPException(status_code=404, detail=msg)
        logger.warning("req_id=%s | patient not found | detail=%s", req_id, msg)
        raise HTTPException(status_code=404, detail=msg)
    except ValueError as exc:
        logger.warning("req_id=%s | bad request | detail=%s", req_id, exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("req_id=%s | unhandled error | detail=%s", req_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


def _cache_headers(summary: EHRSummaryResponse) -> dict:
    headers: dict = {"X-Cache": "HIT" if summary.cache_hit else "MISS"}
    if summary.cache_hit and summary.cache_expires_at:
        headers["X-Cache-Expires"] = summary.cache_expires_at
    usage = summary.openai_usage
    headers["X-OpenAI-Total-Tokens"] = str(usage.total_tokens)
    headers["X-OpenAI-LLM-Calls"] = str(usage.llm_calls)
    return headers


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/ehr-summary",
    response_model=EHRSummaryResponse,
    summary="Get AI clinical summary (cached)",
    description=(
        "Returns an AI-condensed, chronological EHR clinical summary.\n\n"
        "**Cache:** results stored in PostgreSQL for `EHR_SUMMARY_CACHE_TTL_HOURS` "
        "(default 24 h). Pass `?force_refresh=true` to bypass.\n\n"
        "**Response headers:** `X-Cache: HIT|MISS`, `X-Cache-Expires` (on HIT), "
        "`X-OpenAI-Total-Tokens`, `X-OpenAI-LLM-Calls`, "
        "`X-Request-ID` (trace ID for this call).\n\n"
        "**Cache-first:** always serves PostgreSQL cache when available unless "
        "`force_refresh=true`. Token usage in `openai_usage` is **0 on cache HIT**.\n\n"
        "**Data integrity:** original records are never modified.\n\n"
        "**Performance tip:** use `include_records=false` (default) for fast responses. "
        "Set `include_records=true` only when you need the full FHIR `original_record` per event."
    ),
)
def get_ehr_summary(
    request: EHRSummaryRequest = Body(...),
    force_refresh: bool = Query(False, description="Bypass cache and regenerate summary"),
    include_records: bool = Query(False, description="Include original_record FHIR data per event (larger/slower response)"),
    user=Depends(jwt_filter),
) -> Response:
    assert_summary_access(user, request.patient_id, request.email)
    req_id = str(uuid.uuid4())[:8]
    t0 = time.perf_counter()

    logger.info(
        "EHR summary request | req_id=%s | patient_id=%s | email=%s | force_refresh=%s | include_records=%s | endpoint=ehr-summary",
        req_id, request.patient_id, request.email, force_refresh, include_records,
    )

    summary = _build_summary(request, force_refresh=force_refresh, include_records=include_records, req_id=req_id)
    payload = summary.model_dump(mode="json")
    body = json.dumps(payload, default=str)
    elapsed = time.perf_counter() - t0

    logger.info(
        "EHR summary response | req_id=%s | patient_id=%s | cache=%s | records=%d | "
        "openai_tokens=%d | llm_calls=%d | elapsed=%.2fs | response_bytes=%d",
        req_id,
        summary.patient.patient_id,
        "HIT" if summary.cache_hit else "MISS",
        summary.total_records_processed,
        summary.openai_usage.total_tokens,
        summary.openai_usage.llm_calls,
        elapsed,
        len(body),
    )

    return Response(
        content=body,
        media_type="application/json",
        headers={**_cache_headers(summary), "X-Request-ID": req_id},
    )


@router.post(
    "/ehr-summary/download",
    summary="Download AI clinical summary as a structured JSON file",
    description=(
        "Same as `/ehr-summary` but streams the result as an `application/json` attachment.\n\n"
        "Pass `?force_refresh=true` to regenerate instead of serving from cache."
    ),
)
def download_ehr_summary(
    request: EHRSummaryRequest = Body(...),
    force_refresh: bool = Query(False, description="Bypass cache and regenerate summary"),
    include_records: bool = Query(True, description="Include original_record FHIR data per event (default true for downloads)"),
    user=Depends(jwt_filter),
) -> Response:
    assert_summary_access(user, request.patient_id, request.email)
    req_id = str(uuid.uuid4())[:8]
    t0 = time.perf_counter()

    logger.info(
        "EHR summary download request | req_id=%s | patient_id=%s | email=%s | force_refresh=%s | include_records=%s",
        req_id, request.patient_id, request.email, force_refresh, include_records,
    )

    summary = _build_summary(request, force_refresh=force_refresh, include_records=include_records, req_id=req_id)

    patient_slug = (
        (summary.patient.name or summary.patient.patient_id)
        .replace(" ", "_")
        .lower()
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"ehr_summary_{patient_slug}_{timestamp}.json"
    payload = summary.model_dump(mode="json")
    body = json.dumps(payload, indent=2, default=str)
    elapsed = time.perf_counter() - t0

    logger.info(
        "EHR summary download response | req_id=%s | patient_id=%s | cache=%s | records=%d | elapsed=%.2fs | filename=%s",
        req_id,
        summary.patient.patient_id,
        "HIT" if summary.cache_hit else "MISS",
        summary.total_records_processed,
        elapsed,
        filename,
    )

    return Response(
        content=body,
        media_type="application/json",
        headers={
            **_cache_headers(summary),
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Patient-ID": summary.patient.patient_id,
            "X-Generated-At": summary.generated_at,
            "X-Total-Records": str(summary.total_records_processed),
            "X-Request-ID": req_id,
        },
    )


@router.post(
    "/ehr-summary/download-pdf",
    summary="Download EHR summary as a print-ready HTML/PDF",
    description=(
        "Returns a styled A4 HTML document populated with the patient's real EHR data. "
        "Open the file in any browser and use **File → Print → Save as PDF** to produce the final PDF.\n\n"
        "The document includes: patient info, health timeline, diagnoses, allergies, medications, "
        "encounters, lab results, vital signs, imaging, clinical notes, and a data integrity notice.\n\n"
        "Uses cached data when available (cache-first unless `force_refresh=true`); "
        "on cache MISS generates a fresh summary (same as `/ehr-summary`). "
        "Pass `?cache_only=true` to require cache and fail fast when none exists. "
        "Pass `?force_refresh=true` to bypass cache and regenerate from source data."
    ),
)
def download_ehr_summary_pdf(
    request: EHRSummaryRequest = Body(...),
    force_refresh: bool = Query(False, description="Bypass cache and regenerate summary"),
    cache_only: bool = Query(
        False,
        description="If true, return 404 when no cached summary exists (do not generate)",
    ),
    user=Depends(jwt_filter),
) -> Response:
    assert_summary_access(user, request.patient_id, request.email)
    req_id = str(uuid.uuid4())[:8]
    t0 = time.perf_counter()
    logger.info(
        "EHR PDF download request | req_id=%s | patient_id=%s | email=%s | force_refresh=%s | cache_only=%s",
        req_id, request.patient_id, request.email, force_refresh, cache_only,
    )

    # Use cache when available; generate on MISS unless cache_only=true.
    summary = _build_summary(
        request,
        force_refresh=force_refresh,
        include_records=True,
        cache_only=cache_only and not force_refresh,
        req_id=req_id,
    )

    html_content = render_html(summary)
    patient_slug = (
        (summary.patient.name or summary.patient.patient_id)
        .replace(" ", "_")
        .lower()
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"ehr_summary_{patient_slug}_{timestamp}.html"
    elapsed = time.perf_counter() - t0

    logger.info(
        "EHR PDF download response | req_id=%s | patient_id=%s | cache=%s | elapsed=%.2fs | filename=%s",
        req_id, summary.patient.patient_id,
        "HIT" if summary.cache_hit else "MISS", elapsed, filename,
    )

    return Response(
        content=html_content,
        media_type="text/html",
        headers={
            **_cache_headers(summary),
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Patient-ID": summary.patient.patient_id,
            "X-Request-ID": req_id,
        },
    )


@router.delete(
    "/{patient_id}/ehr-summary/cache",
    summary="Invalidate cached EHR summary for a patient",
    description="Deletes the cached summary. Next request regenerates from source data.",
)
def invalidate_summary_cache(
    patient_id: str,
    user=Depends(require_patient_access),
) -> dict:
    logger.info("Cache invalidation requested | patient_id=%s", patient_id)
    deleted = invalidate_cached_summary(patient_id)
    logger.info(
        "Cache invalidation result | patient_id=%s | deleted=%s",
        patient_id, deleted,
    )
    return {
        "patient_id": patient_id,
        "cache_invalidated": deleted,
        "message": (
            "Cache cleared — next request will regenerate from source data."
            if deleted
            else "No active cache entry found for this patient."
        ),
    }


@router.get(
    "/ehr-summary/cache-stats",
    summary="EHR summary cache health metrics",
    description="Returns total, live, and stale entry counts across all patients.",
)
def cache_stats(user=Depends(require_staff)) -> dict:
    logger.debug("Cache stats requested")
    stats = get_cache_stats()
    logger.debug("Cache stats | %s", stats)
    return {
        "cache_ttl_hours": int(__import__("os").getenv("EHR_SUMMARY_CACHE_TTL_HOURS", "24")),
        **{k: str(v) if hasattr(v, "isoformat") else v for k, v in stats.items()},
    }
