from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from auth.security import jwt_filter

from typing import Optional, Dict, Any, List, Union

from services.patient_annotation_services import (
    upload_patient,
    list_patients,
    get_patient,
    update_comments,
    get_final_json,
    get_all_patients
)

router = APIRouter(
    prefix="/api/annotations",
    tags=["Patient Annotations"]
)

# ---------------- MODELS ----------------

class UploadRequest(BaseModel):
    data: Union[Dict[str, Any], List[Dict[str, Any]]]

class CommentRequest(BaseModel):
    trial_index: int
    type: str  # "trial_fields" | "inclusion" | "exclusion"
    item_index: Optional[int] = None
    fields: Dict[str, Dict[str, Any]]


# ---------------- APIs ----------------

@router.post("/patients/upload")
def upload_patient_api(req: UploadRequest):
    try:
        return upload_patient(req.data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patients")
def list_patients_api():
    try:
        return list_patients()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patients/{pid}")
def get_patient_api(pid: str):
    try:
        return get_patient(pid)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/patients/{pid}/comments")
def update_comments_api(pid: str, req: CommentRequest):
    try:
        payload = req.dict()

        # Basic validation (important)
        if payload["type"] in ["inclusion", "exclusion"] and payload.get("item_index") is None:
            raise HTTPException(
                status_code=400,
                detail="item_index is required for inclusion/exclusion"
            )

        return update_comments(pid, payload)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/patients/{pid}/final-json")
def get_final_json_api(pid: str):
    try:
        return get_final_json(pid)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    


@router.get("/patients/final-json/all")
def get_all_final_json():
    try:
        rows = get_all_patients()
        result = []

        for r in rows:
            pid = r["patient_id"]
            result.append(get_final_json(pid))

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))