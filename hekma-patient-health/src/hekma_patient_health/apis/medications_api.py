import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from ..auth.patient_access import STAFF_ROLES, require_patient_access
from ..auth.security import jwt_filter
from ..schemas.compliance_schemas import CompliancePeriod
from ..schemas.medication_schemas import (
    BulkMedicationInput,
    DailyCountTakenInput,
    DailyCountTargetInput,
    DailyCountUndoInput,
    DeviceTokenInput,
    DoseProgressUpdate,
    MedicationInput,
    PrescriptionScanInput,
    ReminderNotifyInput,
    ScheduleMedicationInput,
    SyncDoseLogInput,
)
from ..services.medications.dependencies import (
    get_compliance_service,
    get_daily_count_service,
    get_dose_history_service,
    get_medication_service,
    get_notification_service,
    get_prescription_service,
    get_today_medication_service,
)
from ..services.medications.compliance_service import MedicationComplianceService
from ..services.medications.daily_count_service import MedicationDailyCountService
from ..services.medications.dose_history_service import DoseHistoryService
from ..services.medications.exceptions import (
    ExtractionAuthError,
    ExtractionConfigurationError,
    ExtractionRateLimitError,
    ExtractionServiceError,
    DailyCountLimitError,
    DailyCountNotConfiguredError,
    InvalidDoseProgressError,
    InvalidPrescriptionError,
    InvalidReminderScheduleError,
    MedicationDomainError,
    MedicationNotFoundError,
    PrescriptionAlreadyExistsError,
)
from ..services.medications.medication_service import MedicationService
from ..services.medications.notification_service import MedicationNotificationService
from ..services.medications.prescription_service import PrescriptionService
from ..services.medications.today_service import TodayMedicationService
from ..utils.serialization import medication_response, medications_response

router = APIRouter(prefix="/api", tags=["Medications"])
logger = logging.getLogger(__name__)


def _query_int(value: str, default: int) -> int:
    """Parse query ints; strips accidental whitespace/newlines from API clients."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _api_error(status_code: int, code: str, message: str, **extra) -> HTTPException:
    detail = {"code": code, "message": message}
    if extra:
        detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)


def _duplicate_prescription_response(exc: PrescriptionAlreadyExistsError) -> JSONResponse:
    msg = str(exc)
    return JSONResponse(
        status_code=409,
        content={
            "detail": msg,
            "code": "PRESCRIPTION_ALREADY_EXISTS",
            "message": msg,
            "existingPrescriptionId": exc.existing_prescription_id,
        },
    )


def _map_domain_error(exc: MedicationDomainError) -> HTTPException:
    if isinstance(exc, MedicationNotFoundError):
        return _api_error(404, "MEDICATION_NOT_FOUND", str(exc))
    if isinstance(exc, PrescriptionAlreadyExistsError):
        return _api_error(
            409,
            "PRESCRIPTION_ALREADY_EXISTS",
            str(exc),
            existingPrescriptionId=exc.existing_prescription_id,
        )
    if isinstance(exc, ExtractionRateLimitError):
        return _api_error(429, "EXTRACTION_RATE_LIMITED", str(exc))
    if isinstance(exc, ExtractionAuthError):
        return _api_error(503, "SCAN_SERVICE_UNAVAILABLE", str(exc))
    if isinstance(exc, ExtractionServiceError):
        return _api_error(503, "EXTRACTION_UNAVAILABLE", str(exc))
    if isinstance(exc, ExtractionConfigurationError):
        return _api_error(503, "EXTRACTION_NOT_CONFIGURED", str(exc))
    if isinstance(exc, DailyCountLimitError):
        return _api_error(409, "DAILY_COUNT_LIMIT", str(exc))
    if isinstance(exc, DailyCountNotConfiguredError):
        return _api_error(400, "DAILY_COUNT_NOT_CONFIGURED", str(exc))
    if isinstance(
        exc,
        (
            InvalidPrescriptionError,
            InvalidDoseProgressError,
            InvalidReminderScheduleError,
        ),
    ):
        return _api_error(400, "INVALID_REQUEST", str(exc))
    return _api_error(400, "INVALID_REQUEST", str(exc))


# --- Static medication routes (must be registered before /{medication_id}) ---

@router.get("/medications/compliance/dashboard")
def get_compliance_dashboard_api(
    period: CompliancePeriod = Query("7d", description="7d | 1m | 6m | 1y"),
    page: str = Query("1"),
    limit: str = Query("20"),
    search: Optional[str] = Query(None, description="Filter patients/medications by name"),
    timezone: Optional[str] = Query(
        None,
        description="Optional IANA timezone override. Patient APIs otherwise use patient.timezone, then medication_dose_config.json defaultTimezone.",
    ),
    user=Depends(jwt_filter),
    service: MedicationComplianceService = Depends(get_compliance_service),
):
    """
    Medication compliance dashboard for clinicians / care team.
    Summary cards, compliance trend, missed doses by shift, patient monitoring table.
    """
    role = str((user or {}).get("role") or "").split(",")[0].strip().upper()
    if role not in STAFF_ROLES:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Not found."})
    page_num = max(1, _query_int(page, 1))
    limit_num = max(1, min(100, _query_int(limit, 20)))
    search_val = search.strip() if search else None
    return service.get_dashboard(
        period=period,
        page=page_num,
        limit=limit_num,
        search=search_val,
        timezone_name=timezone,
    )


@router.get("/patients/{patient_id}/medications")
def get_medications(
    patient_id: str,
    status: Optional[str] = Query(None),
    includeStopped: Optional[bool] = Query(True),
    user=Depends(require_patient_access),
    service: MedicationService = Depends(get_medication_service),
):
    medications = service.list_for_patient(patient_id)
    if status:
        medications = [m for m in medications if m["status"] == status]
    if not includeStopped:
        medications = [m for m in medications if m["status"] == "Active"]
    return {"medications": medications_response(medications)}


@router.post("/patients/{patient_id}/medications")
def create_medication_api(
    patient_id: str,
    body: MedicationInput,
    user=Depends(require_patient_access),
    service: MedicationService = Depends(get_medication_service),
):
    try:
        medication = service.create_with_reminders(patient_id, body.model_dump())
        return {"medication": medication_response(medication)}
    except MedicationDomainError as exc:
        raise _map_domain_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/patients/{patient_id}/medications/bulk")
def create_bulk_medications_api(
    patient_id: str,
    body: BulkMedicationInput,
    user=Depends(require_patient_access),
    service: MedicationService = Depends(get_medication_service),
):
    try:
        medications = service.create_bulk(
            patient_id,
            [m.model_dump() for m in body.medications],
            auto_schedule=body.autoSchedule,
        )
        return {"medications": medications_response(medications)}
    except MedicationDomainError as exc:
        raise _map_domain_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/patients/{patient_id}/medications/today")
def get_today_medications_api(
    patient_id: str,
    date_str: Optional[str] = Query(None, alias="date"),
    timezone: Optional[str] = Query(
        None,
        description="Optional IANA timezone override. Defaults to patient.timezone, then medication_dose_config.json defaultTimezone.",
    ),
    user=Depends(require_patient_access),
    service: TodayMedicationService = Depends(get_today_medication_service),
):
    try:
        target_date = date.fromisoformat(date_str) if date_str else None
        return service.get_schedule(
            patient_id,
            target_date=target_date,
            include_metrics=False,
            timezone_name=timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/patients/{patient_id}/medications/today/metrics")
def get_today_medications_with_metrics_api(
    patient_id: str,
    date_str: Optional[str] = Query(None, alias="date"),
    timezone: Optional[str] = Query(
        None,
        description="Optional IANA timezone override. Defaults to patient.timezone, then medication_dose_config.json defaultTimezone.",
    ),
    user=Depends(require_patient_access),
    service: TodayMedicationService = Depends(get_today_medication_service),
):
    try:
        target_date = date.fromisoformat(date_str) if date_str else None
        return service.get_schedule(
            patient_id,
            target_date=target_date,
            include_metrics=True,
            timezone_name=timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/patients/{patient_id}/medications/progress")
def update_medication_progress_api(
    patient_id: str,
    body: DoseProgressUpdate,
    timezone: Optional[str] = Query(
        None,
        description="Optional IANA timezone override. Defaults to patient.timezone, then medication_dose_config.json defaultTimezone.",
    ),
    user=Depends(require_patient_access),
    service: DoseHistoryService = Depends(get_dose_history_service),
):
    try:
        entries = [entry.model_dump() for entry in body.entries]
        return service.update_progress(entries, patient_id=patient_id, timezone_name=timezone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/patients/{patient_id}/medications/dose-log")
def sync_dose_log(
    patient_id: str,
    body: SyncDoseLogInput,
    timezone: Optional[str] = Query(
        None,
        description="Optional IANA timezone override. Defaults to patient.timezone, then medication_dose_config.json defaultTimezone.",
    ),
    user=Depends(require_patient_access),
    service: DoseHistoryService = Depends(get_dose_history_service),
):
    try:
        return service.sync_entries(
            [entry.model_dump() for entry in body.entries],
            patient_id=patient_id,
            timezone_name=timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/patients/{patient_id}/medications/dose-log")
def get_dose_log(
    patient_id: str,
    from_time: Optional[int] = Query(None),
    to_time: Optional[int] = Query(None),
    limit: Optional[int] = Query(100),
    user=Depends(require_patient_access),
    medication_service: MedicationService = Depends(get_medication_service),
    dose_service: DoseHistoryService = Depends(get_dose_history_service),
):
    medications = medication_service.list_for_patient(patient_id)
    medication_ids = [m["id"] for m in medications]
    history = dose_service.get_history(medication_ids, from_time, to_time)
    if limit:
        history = history[:limit]
    return {"entries": medications_response(history)}


@router.put("/patients/{patient_id}/medications/{medication_id}/daily-count/target")
def set_medication_daily_count_target_api(
    patient_id: str,
    medication_id: int,
    body: DailyCountTargetInput,
    user=Depends(require_patient_access),
    service: MedicationDailyCountService = Depends(get_daily_count_service),
):
    """Set the prescribed number of uses for each patient-local day."""
    try:
        medication = service.set_target(
            patient_id, medication_id, body.dailyTargetCount
        )
        return {"medication": medication_response(medication)}
    except MedicationDomainError as exc:
        raise _map_domain_error(exc) from exc


@router.get("/patients/{patient_id}/medications/{medication_id}/daily-count")
def get_medication_daily_count_api(
    patient_id: str,
    medication_id: int,
    date_str: Optional[str] = Query(None, alias="date"),
    timezone: Optional[str] = Query(
        None,
        description="Optional IANA timezone override. Defaults to patient.timezone, then medication_dose_config.json defaultTimezone.",
    ),
    user=Depends(require_patient_access),
    service: MedicationDailyCountService = Depends(get_daily_count_service),
):
    """Return target, taken, remaining, active, and missed counts for a local day."""
    try:
        target_date = date.fromisoformat(date_str) if date_str else None
        return service.get_summary(
            patient_id, medication_id, target_date, timezone
        )
    except (ValueError, MedicationDomainError) as exc:
        if isinstance(exc, MedicationDomainError):
            raise _map_domain_error(exc) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/patients/{patient_id}/medications/{medication_id}/daily-count/taken")
def record_medication_daily_count_taken_api(
    patient_id: str,
    medication_id: int,
    body: DailyCountTakenInput,
    timezone: Optional[str] = Query(
        None,
        description="Optional IANA timezone override. Defaults to patient.timezone, then medication_dose_config.json defaultTimezone.",
    ),
    user=Depends(require_patient_access),
    service: MedicationDailyCountService = Depends(get_daily_count_service),
):
    """Record count-based medication uses and reduce the remaining count."""
    try:
        return service.record_taken(
            patient_id,
            medication_id,
            count=body.count,
            taken_time=body.takenTime,
            timezone_name=timezone,
        )
    except MedicationDomainError as exc:
        raise _map_domain_error(exc) from exc


@router.post("/patients/{patient_id}/medications/{medication_id}/daily-count/undo")
def undo_medication_daily_count_taken_api(
    patient_id: str,
    medication_id: int,
    body: DailyCountUndoInput,
    date_str: Optional[str] = Query(None, alias="date"),
    timezone: Optional[str] = Query(
        None,
        description="Optional IANA timezone override. Defaults to patient.timezone, then medication_dose_config.json defaultTimezone.",
    ),
    user=Depends(require_patient_access),
    service: MedicationDailyCountService = Depends(get_daily_count_service),
):
    """Undo count-based medication uses for a patient-local day."""
    try:
        target_date = date.fromisoformat(date_str) if date_str else None
        return service.undo_taken(
            patient_id,
            medication_id,
            count=body.count,
            target_date=target_date,
            timezone_name=timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MedicationDomainError as exc:
        raise _map_domain_error(exc) from exc


@router.post("/patients/{patient_id}/medications/reminders/notify")
def notify_medication_reminder_api(
    patient_id: str,
    body: ReminderNotifyInput,
    user=Depends(require_patient_access),
    service: MedicationNotificationService = Depends(get_notification_service),
):
    try:
        return service.send_reminder(
            patient_id=patient_id,
            medication_id=body.medicationId,
            scheduled_time=body.scheduledTime,
            reminder_id=body.reminderId,
            title=body.title,
            body=body.body,
        )
    except MedicationDomainError as exc:
        raise _map_domain_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# --- Parameterized medication routes ---

@router.get("/patients/{patient_id}/medications/{medication_id}")
def get_medication_api(
    patient_id: str,
    medication_id: int,
    user=Depends(require_patient_access),
    service: MedicationService = Depends(get_medication_service),
):
    medication = service.get_details(medication_id, patient_id)
    if not medication:
        raise HTTPException(status_code=404, detail="Medication not found")
    return {"medication": medication_response(medication)}


@router.put("/patients/{patient_id}/medications/{medication_id}")
def update_medication_api(
    patient_id: str,
    medication_id: int,
    body: MedicationInput,
    user=Depends(require_patient_access),
    service: MedicationService = Depends(get_medication_service),
):
    try:
        # exclude_unset keeps optional dailyTargetCount from wiping existing values.
        medication = service.update_with_reminders(
            medication_id, patient_id, body.model_dump(exclude_unset=True)
        )
        return {"medication": medication_response(medication)}
    except MedicationDomainError as exc:
        raise _map_domain_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/patients/{patient_id}/medications/{medication_id}")
def delete_medication_api(
    patient_id: str,
    medication_id: int,
    user=Depends(require_patient_access),
    service: MedicationService = Depends(get_medication_service),
):
    try:
        return service.remove(medication_id, patient_id)
    except MedicationDomainError as exc:
        raise _map_domain_error(exc) from exc


@router.post("/patients/{patient_id}/medications/{medication_id}/schedule")
def schedule_medication_api(
    patient_id: str,
    medication_id: int,
    body: ScheduleMedicationInput,
    user=Depends(require_patient_access),
    service: MedicationService = Depends(get_medication_service),
):
    try:
        medication = service.schedule(
            medication_id,
            patient_id,
            {
                "reminders": [r.model_dump() for r in body.reminders] if body.reminders else None,
                "useFrequencyDefaults": body.useFrequencyDefaults,
            },
        )
        return {"medication": medication_response(medication)}
    except MedicationDomainError as exc:
        raise _map_domain_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# --- Prescriptions ---

@router.post("/patients/{patient_id}/prescriptions/scan")
async def scan_prescription_upload_api(
    patient_id: str,
    file: UploadFile = File(...),
    persistMedications: bool = Form(False),
    autoSchedule: bool = Form(False),
    extract: bool = Form(True),
    user=Depends(require_patient_access),
    service: PrescriptionService = Depends(get_prescription_service),
):
    try:
        content = await file.read()
        logger.info(
            "Prescription scan upload start patient_id=%s extract=%s persist=%s bytes=%s",
            patient_id,
            extract,
            persistMedications,
            len(content),
        )
        result = service.register_from_upload(
            patient_id,
            content,
            file.filename or "prescription.jpg",
            {
                "persistMedications": persistMedications,
                "autoSchedule": autoSchedule,
                "extract": extract,
            },
        )
        logger.info(
            "Prescription scan upload ok patient_id=%s prescription_id=%s",
            patient_id,
            (result.get("prescription") or {}).get("id"),
        )
        return result
    except PrescriptionAlreadyExistsError as exc:
        logger.info(
            "Prescription scan duplicate patient_id=%s existing_id=%s",
            patient_id,
            exc.existing_prescription_id,
        )
        return _duplicate_prescription_response(exc)
    except MedicationDomainError as exc:
        logger.info(
            "Prescription scan domain_error patient_id=%s code=%s message=%s",
            patient_id,
            type(exc).__name__,
            str(exc),
        )
        raise _map_domain_error(exc) from exc
    except Exception as exc:
        logger.exception("Prescription scan upload failed for patient_id=%s", patient_id)
        raise _api_error(
            500,
            "PRESCRIPTION_SCAN_FAILED",
            "Something went wrong while scanning the prescription. Please try again.",
        ) from exc


@router.post("/patients/{patient_id}/prescriptions")
def create_prescription_api(
    patient_id: str,
    body: PrescriptionScanInput,
    user=Depends(require_patient_access),
    service: PrescriptionService = Depends(get_prescription_service),
):
    try:
        return service.register_from_url(patient_id, body.model_dump())
    except PrescriptionAlreadyExistsError as exc:
        return _duplicate_prescription_response(exc)
    except MedicationDomainError as exc:
        raise _map_domain_error(exc) from exc
    except Exception as exc:
        logger.exception("Prescription scan URL failed for patient_id=%s", patient_id)
        raise _api_error(
            500,
            "PRESCRIPTION_SCAN_FAILED",
            "Something went wrong while scanning the prescription. Please try again.",
        ) from exc


@router.get("/patients/{patient_id}/prescriptions")
def list_prescriptions_api(
    patient_id: str,
    user=Depends(require_patient_access),
    service: PrescriptionService = Depends(get_prescription_service),
):
    return {"prescriptions": service.list_for_patient(patient_id)}


@router.get("/patients/{patient_id}/prescriptions/{prescription_id}")
def get_prescription_api(
    patient_id: str,
    prescription_id: int,
    user=Depends(require_patient_access),
    service: PrescriptionService = Depends(get_prescription_service),
):
    prescription = service.get_for_patient(patient_id, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return {"prescription": prescription}


# --- Devices ---

@router.post("/patients/{patient_id}/devices")
def register_device_api(
    patient_id: str,
    body: DeviceTokenInput,
    user=Depends(require_patient_access),
    service: MedicationNotificationService = Depends(get_notification_service),
):
    token = service.register_device(
        patient_id,
        body.deviceToken,
        body.platform,
        timezone_name=body.timezone,
    )
    return {"device": medication_response(token)}
