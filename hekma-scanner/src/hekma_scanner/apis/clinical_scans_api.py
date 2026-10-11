import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from ..auth.patient_access import require_patient_access
from ..schemas.clinical_scan_schemas import SmartClinicalScanUrlInput
from ..services.clinical_scans.dependencies import get_smart_scan_service
from ..services.clinical_scans.exceptions import (
    ClinicalScanAlreadyExistsError,
    ClinicalScanDomainError,
    ClinicalScanNotFoundError,
    ExtractionAuthError,
    ExtractionConfigurationError,
    ExtractionRateLimitError,
    ExtractionServiceError,
    FileSizeExceededError,
    InvalidClinicalDocumentError,
    NoClinicalDataFoundError,
    PdfPageLimitExceededError,
    RecordAlreadyExistsError,
    UnsupportedClinicalModuleError,
)
from ..services.clinical_scans.smart_scan_service import SmartClinicalScanService

router = APIRouter(prefix="/api", tags=["Clinical Scans"])
logger = logging.getLogger(__name__)


def _api_error(status_code: int, error_code: int, code: str, message: str, **extra) -> HTTPException:
    detail = {"errorCode": error_code, "code": code, "message": message}
    detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)


def _map_domain_error(exc: ClinicalScanDomainError) -> HTTPException:
    if isinstance(exc, FileSizeExceededError):
        return _api_error(400, 1002, "FILE_SIZE_EXCEEDED", str(exc))
    if isinstance(exc, PdfPageLimitExceededError):
        return _api_error(400, 1003, "PDF_PAGE_LIMIT_EXCEEDED", str(exc))
    if isinstance(exc, NoClinicalDataFoundError):
        return _api_error(400, 1004, "NO_CLINICAL_DATA_FOUND", str(exc))
    if isinstance(exc, InvalidClinicalDocumentError):
        return _api_error(400, 1001, "INVALID_CLINICAL_DOCUMENT", str(exc))
    if isinstance(exc, UnsupportedClinicalModuleError):
        return _api_error(400, 1005, "UNSUPPORTED_CLINICAL_MODULE", str(exc))
    if isinstance(exc, ClinicalScanAlreadyExistsError):
        return _api_error(
            409,
            1020,
            "CLINICAL_SCAN_ALREADY_EXISTS",
            str(exc),
            existingScanId=exc.existing_scan_id,
        )
    if isinstance(exc, RecordAlreadyExistsError):
        return _api_error(
            409,
            1023,
            "RECORD_ALREADY_EXISTS",
            str(exc),
            existingRecordId=exc.existing_record_id,
        )
    if isinstance(exc, ClinicalScanNotFoundError):
        return _api_error(404, 1010, "NOT_FOUND", str(exc))
    if isinstance(exc, ExtractionRateLimitError):
        return _api_error(429, 1030, "EXTRACTION_RATE_LIMITED", str(exc))
    if isinstance(exc, ExtractionAuthError):
        return _api_error(
            503,
            1052,
            "SCAN_SERVICE_UNAVAILABLE",
            str(exc),
        )
    if isinstance(exc, ExtractionServiceError):
        return _api_error(503, 1053, "EXTRACTION_UNAVAILABLE", str(exc))
    if isinstance(exc, ExtractionConfigurationError):
        return _api_error(503, 1054, "EXTRACTION_NOT_CONFIGURED", str(exc))
    return _api_error(400, 1006, "INVALID_REQUEST", str(exc))


def _dump_model(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(by_alias=True, exclude_unset=True)
    return model.dict(by_alias=True, exclude_unset=True)




# ── Example Response Objects for Swagger UI Documentation ─────────────────────

_EX_SMART_SCAN_RESPONSE = {
    "mode": "parallel",
    "detectedModules": ["lab_reports", "diagnosis", "allergies"],
    "savedModules": ["lab_reports", "diagnosis", "allergies"],
    "extractedData": {
        "doctor_name": "Dr. L. Thompson",
        "clinic": "Metropolitan Clinical Services",
        "patient_name": "Sarah Chen",
        "date": "2023-10-03",
        "allergies": [
            {
                "substance": "Penicillin G",
                "criticality": "high",
                "category": "medication",
                "severity": "severe",
                "verificationStatus": "confirmed",
                "reaction": "Hives, Swelling",
                "onsetDate": "",
                "notes": "ICD-10: Z88.0",
                "confidence": 0.95
            }
        ],
        "lab_results": [
            {
                "testName": "Hemoglobin A1c",
                "testCode": "4548-4",
                "category": "Chemistry",
                "testValue": "6.8",
                "unit": "%",
                "referenceRange": "4.0 - 5.6",
                "interpretation": "HIGH",
                "specimen": "Whole Blood",
                "performer": "Dr. L. Thompson",
                "resultDate": "2023-10-03",
                "notes": "Fasting sample.",
                "confidence": 0.95
            }
        ],
        "conditions": [
            {
                "conditionName": "Essential Hypertension",
                "code": "I10",
                "clinicalStatus": "ACTIVE",
                "verificationStatus": "CONFIRMED",
                "category": "Chronic",
                "severity": "MODERATE",
                "startDate": "2021-05-12",
                "recordedBy": "Dr. L. Thompson",
                "notes": "Blood pressure elevated.",
                "confidence": 0.95
            }
        ],
        "vitals": [],
        "immunizations": [],
        "procedures": [],
        "overall_confidence": 0.95
    },
    "results": {
        "allergies": {
            "scan": {
                "id": 5,
                "patient_id": "203022",
                "module": "allergies",
                "document_date": "2023-10-03",
                "created_at": "2026-07-30T07:31:41Z"
            },
            "recordsCreated": 1
        }
    }
}

_EX_SCAN_ROW = {
    "id": 5,
    "patient_id": "203022",
    "patientId": "203022",
    "module": "allergies",
    "image_path": "upload://scan_document.pdf",
    "imageUrl": "upload://scan_document.pdf",
    "document_date": "2023-10-03",
    "documentDate": "2023-10-03",
    "provider_name": "Dr. L. Thompson",
    "providerName": "Dr. L. Thompson",
    "content_hash": "9bbb0515b62c35bb667ffe07818190166140892da5f2b975a1256e98988dc0b5",
    "contentHash": "9bbb0515b62c35bb667ffe07818190166140892da5f2b975a1256e98988dc0b5",
    "created_at": "2026-07-30T07:31:41",
    "createdAt": "2026-07-30T07:31:41",
    "scannedAt": 1753860701000,
    "extracted_data": _EX_SMART_SCAN_RESPONSE["extractedData"],
    "extractedData": _EX_SMART_SCAN_RESPONSE["extractedData"],
}


@router.get(
    "/patients/{patient_id}/clinical-scans",
    summary="List Clinical Scans",
    responses={
        200: {
            "description": "List of clinical document scan metadata records for patient.",
            "content": {"application/json": {"example": {"scans": [_EX_SCAN_ROW]}}},
        }
    },
)
def list_clinical_scans_api(
    patient_id: str,
    module: Optional[str] = Query(None),
    user=Depends(require_patient_access),
    service: SmartClinicalScanService = Depends(get_smart_scan_service),
):
    try:
        return {"scans": service.list_for_patient(patient_id, module)}
    except ClinicalScanDomainError as exc:
        raise _map_domain_error(exc) from exc


@router.get(
    "/patients/{patient_id}/clinical-scans/{scan_id}",
    summary="Get Clinical Scan",
    responses={
        200: {
            "description": "Single clinical scan record with full extracted JSON payload.",
            "content": {"application/json": {"example": {"scan": _EX_SCAN_ROW}}},
        }
    },
)
def get_clinical_scan_api(
    patient_id: str,
    scan_id: int,
    user=Depends(require_patient_access),
    service: SmartClinicalScanService = Depends(get_smart_scan_service),
):
    try:
        scan = service.get_for_patient(patient_id, scan_id)
        if not scan:
            raise ClinicalScanNotFoundError(f"Clinical scan {scan_id} not found for patient {patient_id}")
        return {"scan": scan}
    except ClinicalScanDomainError as exc:
        raise _map_domain_error(exc) from exc


# ── Smart Scan — Upload ───────────────────────────────────────────────────────

@router.post(
    "/patients/{patient_id}/clinical-scans/smart",
    summary="Smart Scan Upload — Auto-detect all clinical modules",
    responses={
        200: {
            "description": "Smart document scan extraction and persistence results.",
            "content": {"application/json": {"example": _EX_SMART_SCAN_RESPONSE}},
        }
    },
)
async def smart_scan_upload_api(
    patient_id: str,
    file: Optional[UploadFile] = File(None),
    persistRecords: bool = Form(False),
    forceSave: bool = Form(
        False,
        description="Bypass duplicate blocking and upsert existing scan/records.",
    ),
    extractedData: Optional[str] = Form(
        None,
        description="Optional JSON string of pre-extracted data (Option A) to skip calling OpenAI on save.",
    ),
    modules: Optional[str] = Form(
        None,
        description="Comma-separated module names to save, e.g. 'lab_reports,vital_signs,medications'. "
                    "Omit to save all detected modules.",
    ),
    autoSchedule: bool = Form(
        False,
        description="Fall back to frequency-default reminder slots when the document "
                    "does not say when to take a dose. Off by default so no slot is invented.",
    ),
    user=Depends(require_patient_access),
    service: SmartClinicalScanService = Depends(get_smart_scan_service),
):
    """
    Upload any clinical document — image or PDF.
    Auto-detects and extracts ALL modules in a single OpenAI call.
    """
    try:
        content = await file.read() if file else b""
        parsed_extracted: Optional[Dict[str, Any]] = None
        if extractedData and extractedData.strip() and extractedData.strip().lower() not in ("string", "null"):
            try:
                parsed_extracted = json.loads(extractedData)
            except Exception:
                pass

        raw_modules = (modules or "").strip()
        if raw_modules and raw_modules.lower() not in ("string", "null"):
            module_list: Optional[List[str]] = [
                m.strip() for m in raw_modules.split(",")
                if m.strip() and m.strip().lower() not in ("string", "null")
            ]
            if not module_list:
                module_list = None
        else:
            module_list = None
        filename = (file.filename if file else None) or "scan.jpg"
        content_type = (file.content_type if file else None) or "image/jpeg"
        logger.info(
            "Smart scan upload start patient_id=%s persist=%s forceSave=%s filename=%s "
            "contentType=%s bytes=%s has_extractedData=%s modules=%s",
            patient_id,
            persistRecords,
            forceSave,
            filename,
            content_type,
            len(content),
            bool(parsed_extracted),
            module_list,
        )
        result = service.register_from_upload(
            patient_id,
            content,
            filename,
            {
                "persistRecords": persistRecords,
                "forceSave":      forceSave,
                "extractedData":  parsed_extracted,
                "modules":        module_list,
                "autoSchedule":   autoSchedule,
                "contentType":    content_type,
                "imageUrl":       f"upload://{filename}",
            },
        )
        logger.info(
            "Smart scan upload ok patient_id=%s detected=%s",
            patient_id,
            result.get("detectedModules"),
        )
        return result
    except ClinicalScanDomainError as exc:
        logger.info(
            "Smart scan upload domain_error patient_id=%s code=%s message=%s",
            patient_id,
            type(exc).__name__,
            str(exc),
        )
        raise _map_domain_error(exc) from exc
    except Exception as exc:
        logger.exception("Smart scan upload failed for patient_id=%s", patient_id)
        raise _api_error(
            500,
            1050,
            "SMART_SCAN_FAILED",
            "Something went wrong during smart scan. Please try again.",
        ) from exc


# ── Smart Scan — URL ─────────────────────────────────────────────────────────

@router.post(
    "/patients/{patient_id}/clinical-scans/smart/url",
    summary="Smart Scan URL — Auto-detect all clinical modules",
    responses={
        200: {
            "description": "Smart document scan extraction and persistence results from URL.",
            "content": {"application/json": {"example": _EX_SMART_SCAN_RESPONSE}},
        }
    },
)
def smart_scan_url_api(
    patient_id: str,
    body: SmartClinicalScanUrlInput,
    user=Depends(require_patient_access),
    service: SmartClinicalScanService = Depends(get_smart_scan_service),
):
    """
    Scan a document from a URL.
    Auto-detects and extracts ALL modules in a single OpenAI call.
    """
    try:
        logger.info(
            "Smart scan URL start patient_id=%s persist=%s",
            patient_id,
            getattr(body, "persistRecords", False),
        )
        result = service.register_from_url(patient_id, _dump_model(body))
        logger.info(
            "Smart scan URL ok patient_id=%s detected=%s",
            patient_id,
            result.get("detectedModules"),
        )
        return result
    except ClinicalScanDomainError as exc:
        logger.info(
            "Smart scan URL domain_error patient_id=%s code=%s message=%s",
            patient_id,
            type(exc).__name__,
            str(exc),
        )
        raise _map_domain_error(exc) from exc
    except Exception as exc:
        logger.exception("Smart scan URL failed for patient_id=%s", patient_id)
        raise _api_error(
            500,
            1050,
            "SMART_SCAN_FAILED",
            "Something went wrong during smart scan. Please try again.",
        ) from exc


# ── Delete Clinical Scan ──────────────────────────────────────────────────────

@router.delete(
    "/patients/{patient_id}/clinical-scans/{scan_id}",
    summary="Delete Clinical Scan",
    responses={
        200: {
            "description": "Soft-delete confirmation.",
            "content": {"application/json": {"example": {"deleted": True, "scanId": 5}}},
        }
    },
)
def delete_clinical_scan_api(
    patient_id: str,
    scan_id: int,
    user=Depends(require_patient_access),
    service: SmartClinicalScanService = Depends(get_smart_scan_service),
):
    """Soft-delete the scan and the clinical rows saved from that document."""
    try:
        deleted = service.delete_for_patient(patient_id, scan_id)
        if not deleted:
            raise ClinicalScanNotFoundError(
                f"Clinical scan {scan_id} not found for patient {patient_id}"
            )
        return {"deleted": True, "scanId": scan_id}
    except ClinicalScanDomainError as exc:
        raise _map_domain_error(exc) from exc
