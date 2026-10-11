"""Internal dual-write API so GraphQL (hekma_api) can project manual rows to FHIR."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth.security import cache_reprocess_auth
from ..services.clinical_fhir.models import ClinicalSource, ProjectionCommand
from ..services.clinical_fhir.projector import ClinicalFhirProjector

router = APIRouter(prefix="/api/internal", tags=["Internal FHIR"])


class ClinicalFhirProjectBody(BaseModel):
    patientId: str
    module: str
    action: str = "upsert"
    source: str = "manual"
    mysqlRecordId: Optional[int] = None
    documentId: Optional[str] = None
    hekmaMail: Optional[str] = None
    record: Dict[str, Any] = Field(default_factory=dict)


def _get_projector() -> ClinicalFhirProjector:
    return ClinicalFhirProjector()


@router.post("/clinical-fhir/project")
def project_clinical_fhir(
    body: ClinicalFhirProjectBody,
    _auth=Depends(cache_reprocess_auth),
    projector: ClinicalFhirProjector = Depends(_get_projector),
):
    """Best-effort FHIR upsert/retire. Always 200 if auth ok so GraphQL save is not blocked."""
    try:
        source = ClinicalSource(body.source)
    except ValueError:
        source = ClinicalSource.MANUAL
    record = dict(body.record or {})
    if body.mysqlRecordId is not None and "id" not in record:
        record["id"] = body.mysqlRecordId
    result = projector.execute(
        ProjectionCommand(
            patient_id=body.patientId,
            module=body.module,
            source=source,
            record=record,
            mysql_record_id=body.mysqlRecordId,
            document_id=body.documentId,
            hekma_mail_id=body.hekmaMail,
            action=(body.action or "upsert").strip().lower(),
        )
    )
    if not result.ok and (result.extras or {}).get("catalogFieldKey"):
        raise HTTPException(status_code=400, detail=result.error)
    return {
        "status": "success" if result.ok else "skipped",
        "hekmaId": result.hekma_id,
        "fhirId": result.fhir_id,
        "resourceType": result.resource_type,
        "error": result.error,
    }
