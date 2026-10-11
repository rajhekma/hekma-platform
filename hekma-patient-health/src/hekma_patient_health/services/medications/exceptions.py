"""Domain exceptions for the medications module."""


class MedicationDomainError(Exception):
    """Base class for medication feature errors."""


class MedicationNotFoundError(MedicationDomainError):
    """Raised when a medication is missing or not owned by the patient."""


class PrescriptionNotFoundError(MedicationDomainError):
    """Raised when a prescription is missing or not owned by the patient."""


class PrescriptionAlreadyExistsError(MedicationDomainError):
    """Raised when the same prescription already has saved medications for the patient."""

    def __init__(self, existing_prescription_id: int, message: str | None = None):
        self.existing_prescription_id = existing_prescription_id
        super().__init__(message or "Prescription is already added.")


class InvalidPrescriptionError(MedicationDomainError):
    """Raised when input is not a valid prescription or source is invalid."""


class ExtractionConfigurationError(MedicationDomainError):
    """Raised when AI extraction is misconfigured (e.g. missing API key)."""


class ExtractionAuthError(MedicationDomainError):
    """Raised when scanning service credentials are invalid, revoked, or expired."""

    def __init__(self, message: str, reason_code: str | None = None):
        super().__init__(message)
        self.reason_code = reason_code or "auth_failed"


class ExtractionRateLimitError(MedicationDomainError):
    """Raised when the AI provider rate-limits or quota is exceeded."""


class ExtractionServiceError(MedicationDomainError):
    """Raised when upstream AI extraction fails unexpectedly."""


class InvalidDoseProgressError(MedicationDomainError):
    """Raised when a dose progress entry violates logging rules."""


class InvalidReminderScheduleError(MedicationDomainError):
    """Raised when reminder slots do not match the medication frequency."""


class DailyCountNotConfiguredError(MedicationDomainError):
    """Raised when count tracking is used without a positive daily target."""


class DailyCountLimitError(MedicationDomainError):
    """Raised when a count change exceeds the target or available taken count."""
