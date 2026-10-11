import json
import logging

from fastapi import APIRouter, Body, HTTPException, Query, Request

from ..fasten_health.fasten_handler import (
    FastenApiError,
    process_fasten_data,
    request_patient_export,
    revoke_vault_connections,
)
from ..fasten_health.webhook_verification import (
    FastenWebhookVerificationError,
    is_server_webhook_event,
    verify_fasten_webhook,
)

logger = logging.getLogger("fasten_ehr")
router = APIRouter()


@router.post("/fastenhealth/callback")
async def fasten_health_callback(
    request: Request,
    patientId: str = Query(None, alias="patientId"),
):
    raw_body = await request.body()
    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    event_type = data.get("type") or data.get("event_type")
    if is_server_webhook_event(event_type):
        try:
            verify_fasten_webhook(raw_body, dict(request.headers))
        except FastenWebhookVerificationError as exc:
            logger.warning("Fasten webhook signature verification failed: %s", exc)
            raise HTTPException(status_code=401, detail="Invalid webhook signature") from exc

    try:
        return process_fasten_data(data, patient_id=patientId)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/fastenhealth/initiate")
def initiate_export_endpoint(body: dict = Body(...)):
    conn_id = body.get("orgConnectionId") or body.get("org_connection_id")
    if not conn_id:
        raise HTTPException(status_code=400, detail="Missing orgConnectionId")

    tefca_ccda = (
        body.get("tefca_ccda")
        or body.get("tefcaCcda")
        or (body.get("fixtures") or {}).get("tefca_ccda")
    )

    try:
        return request_patient_export(conn_id, tefca_ccda_fixture=tefca_ccda)
    except FastenApiError as e:
        raise HTTPException(status_code=e.status_code or 502, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/fastenhealth/vault/revoke")
def revoke_vault_connections_endpoint(body: dict = Body(...)):
    email = body.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Missing email")

    try:
        return revoke_vault_connections(email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
