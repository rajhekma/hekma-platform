from fastapi import APIRouter, Depends, Query
from ..auth.patient_access import assert_patient_access
from ..auth.security import jwt_filter
from ..ehr_apis.get_patients.lambda_main import get_details as get_patients_details
from ..ehr_apis.get_headers.lambda_main import resource_type_handler as patient_header_handler
from ..ehr_apis.get_resource_type_detail.lambda_main import resource_type_handler as patient_detail_handler

router = APIRouter()


@router.get("/patientheader")
def patient_header(
    user=Depends(jwt_filter),
    hekmaMail: str | None = Query(None),
    patientId: str | None = Query(None),
    combinedFlag: str = Query("N")
):
    if patientId:
        assert_patient_access(user, patientId)

    event = {
        "params": {
            "querystring": {
                "hekmaMail": hekmaMail,
                "patientId": patientId,
                "combinedFlag": combinedFlag,
                "jwtUserId": (user or {}).get("userId"),
            }
        }
    }

    return patient_header_handler(event, None)


@router.get("/patient")
def get_patients(
    user=Depends(jwt_filter),
    from_: int = Query(0, alias="from"),
    size: int = Query(100),
    ids: str | None = Query(None),
    hekmaMail: str | None = Query(None),
    text_search: str | None = Query(None)
):

    jwt_user_id = (user or {}).get("userId")
    if jwt_user_id:
        patient_ids = [str(jwt_user_id)]
    else:
        patient_ids = ids.split(",") if ids else None

    return get_patients_details(
        start=from_,
        size=size,
        patient_ids=patient_ids,
        hekma_mail=None if jwt_user_id or patient_ids else hekmaMail,
        text_search=text_search
    )


@router.get("/patientdetail")
def patient_detail(
    user=Depends(jwt_filter),
    eventType: str = Query(...),
    from_: int = Query(0, alias="from"),
    size: int = Query(100),
    hekmaMail: str | None = Query(None),
    patientId: str | None = Query(None),
    combinedFlag: str = Query("N"),
    vital: str | None = Query(None),
    lab: str | None = Query(None),
    mobile: str | None = Query(None),
    src: str | None = Query(None)
):
    if patientId:
        assert_patient_access(user, patientId)

    event = {
        "params": {
            "querystring": {
                "eventType": eventType,
                "from": from_,
                "size": size,
                "hekmaMail": hekmaMail,
                "patientId": patientId,
                "jwtUserId": (user or {}).get("userId"),
                "combinedFlag": combinedFlag,
                "vital": vital,
                "lab": lab,
                "mobile": mobile,
                "src": src
            }
        }
    }

    return patient_detail_handler(event, None)