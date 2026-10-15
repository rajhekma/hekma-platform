from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth.security import jwt_filter
from services.patient_summary_validation_service import (
    get_validation_context,
    validate_patient_summary,
    list_patients,
)

router = APIRouter(
    prefix="/api/trial-match-validation",
    tags=["Trial Match Validation"],
)


class ValidateRequest(BaseModel):
    refresh_patient_360: bool = Field(
        False,
        description="Rebuild Patient 360 structured facts from MIMIC source tables before validating.",
    )
    use_llm: bool = Field(
        True,
        description="Run LLM semantic validation in addition to rule-based checks.",
    )
    persist: bool = Field(
        True,
        description="Store the latest validation result for the validation panel.",
    )


@router.get("/patients")
def list_validation_patients_api(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(jwt_filter),
):
    try:
        return list_patients(limit=limit, offset=offset)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patients/{patient_id}")
def get_validation_patient_api(
    patient_id: str,
    refresh_patient_360: bool = Query(False),
    user=Depends(jwt_filter),
):
    try:
        return get_validation_context(
            patient_id,
            refresh_patient_360=refresh_patient_360,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/patients/{patient_id}/validate")
def validate_patient_summary_api(
    patient_id: str,
    body: ValidateRequest | None = None,
    user=Depends(jwt_filter),
):
    body = body or ValidateRequest()
    try:
        return validate_patient_summary(
            patient_id,
            refresh_patient_360=body.refresh_patient_360,
            use_llm=body.use_llm,
            persist=body.persist,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
