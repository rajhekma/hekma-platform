from fastapi import APIRouter
from services.summary_resfresh_service import refresh_summaries

router = APIRouter()


@router.post("/batch/refresh-patient-summaries")
def refresh_patient_summaries():
    return refresh_summaries()
