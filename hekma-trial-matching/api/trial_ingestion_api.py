from fastapi import APIRouter, HTTPException
from services.trial_ingestion_services import ingest_trials

router = APIRouter()


@router.post("/api/trials/ingest")
def ingest_trial_api(payload: dict):

    try:
        return ingest_trials(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))