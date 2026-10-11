from fastapi import APIRouter, Body, Depends, HTTPException, Query

from ..auth.patient_access import assert_patient_access
from ..auth.security import jwt_filter
from ..healthkit_apis.get_health_data import resource_type_handler_healthkit
from ..healthkit_apis.post_health_data import resource_type_handler_healthkit_post

router = APIRouter(tags=["HealthKit"])


@router.get("/healthkit")
def healthkit_get(
    id: str = Query(..., alias="id"),
    sort_field: str = "timestamp",
    sort_order: str = "asc",
    page: int = 1,
    size: int = 1000,
    from_timestamp: str | None = Query(None),
    to_timestamp: str | None = Query(None),
    user=Depends(jwt_filter),
):
    assert_patient_access(user, id)
    return resource_type_handler_healthkit(
        doc_id=id,
        sort_field=sort_field,
        sort_order=sort_order,
        page=page,
        size=size,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )


@router.post("/healthkit")
def post_healthkit(body: dict = Body(...), user=Depends(jwt_filter)):
    source_id = body.get("id")
    if not source_id:
        raise HTTPException(status_code=400, detail="Both 'id' and 'timestamp' are required")
    assert_patient_access(user, str(source_id))
    return resource_type_handler_healthkit_post(body)
