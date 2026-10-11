"""FastAPI dependency providers for medication services (DIP)."""

from functools import lru_cache

from .daily_count_service import MedicationDailyCountService
from .dose_history_service import DoseHistoryService
from .medication_service import MedicationService
from .notification_service import MedicationNotificationService
from .prescription_service import PrescriptionService
from .today_service import TodayMedicationService


@lru_cache
def get_medication_service() -> MedicationService:
    return MedicationService()


@lru_cache
def get_prescription_service() -> PrescriptionService:
    return PrescriptionService(medication_service=get_medication_service())


@lru_cache
def get_dose_history_service() -> DoseHistoryService:
    return DoseHistoryService()


@lru_cache
def get_daily_count_service() -> MedicationDailyCountService:
    return MedicationDailyCountService()


@lru_cache
def get_today_medication_service() -> TodayMedicationService:
    return TodayMedicationService()


@lru_cache
def get_notification_service() -> MedicationNotificationService:
    return MedicationNotificationService()


from .compliance_service import MedicationComplianceService


@lru_cache
def get_compliance_service() -> MedicationComplianceService:
    return MedicationComplianceService()
