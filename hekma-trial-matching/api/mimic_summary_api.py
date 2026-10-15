from fastapi import APIRouter, Query
from services.mimic_summary_service import process_mimic_summaries

router = APIRouter()

@router.post("/mimic/summaries")
def run(patient_id: str | None = Query(None)):
    return process_mimic_summaries(patient_id)