"""Internal API for lambda/hekma backend to trigger trial_gpt_ehr ingest."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from auth.internal_auth import internal_service_auth
from services.trial_gpt_ehr_ingest_service import TrialGptEhrIngestError
from services.trial_gpt_ehr_trigger_service import trigger_trial_gpt_ehr_ingest

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/internal/trial-gpt-ehr",
    tags=["Internal trial_gpt_ehr"],
)


class TrialGptEhrIngestRequest(BaseModel):
    patient_id: str = Field(..., description="MySQL Patient.patientId")
    trigger: str = Field(
        default="fasten_export",
        description="Caller label for logs (e.g. fasten_ehi_export_success)",
    )
    force: bool = Field(
        default=True,
        description="Re-ingest when Fasten data was re-exported (patient updated)",
    )


@router.post("/ingest")
def internal_trigger_trial_gpt_ehr_ingest(
    req: TrialGptEhrIngestRequest,
    response: Response,
    _auth=Depends(internal_service_auth),
):
    """
    Queue trial_gpt_ehr ingest after Fasten export lands in fastenhealth_* tables.

    Called by hekma_data_pipleline (lambda_api) — not for browser clients.
    """
    logger.info(
        "trial_gpt_ehr internal ingest request | patient_id=%s | trigger=%s | force=%s",
        req.patient_id,
        req.trigger,
        req.force,
    )
    try:
        result = trigger_trial_gpt_ehr_ingest(
            req.patient_id,
            trigger=req.trigger,
            force=req.force,
        )
    except TrialGptEhrIngestError as exc:
        logger.warning(
            "trial_gpt_ehr internal ingest rejected | patient_id=%s | status=%s | detail=%s",
            req.patient_id,
            exc.status_code,
            exc,
        )
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    logger.info(
        "trial_gpt_ehr internal ingest response | patient_id=%s | status=%s | ehr_status=%s",
        req.patient_id,
        result.get("status"),
        result.get("ehr_status"),
    )
    if result.get("status") == "accepted":
        response.status_code = 202
        response.headers["Retry-After"] = "15"
    return result
