"""Domain exceptions for the shared clinical document scan module."""


class ClinicalScanDomainError(Exception):
    """Base class for clinical scan errors."""


class ClinicalScanNotFoundError(ClinicalScanDomainError):
    """Scan missing or not owned by patient."""


class ClinicalScanAlreadyExistsError(ClinicalScanDomainError):
    def __init__(self, message: str, existing_scan_id: int = 0):
        super().__init__(message)
        self.existing_scan_id = existing_scan_id


class InvalidClinicalDocumentError(ClinicalScanDomainError):
    """Invalid or unsupported document input."""


class FileSizeExceededError(InvalidClinicalDocumentError):
    """Raised when document size exceeds maximum allowed threshold (10 MB)."""


class PdfPageLimitExceededError(InvalidClinicalDocumentError):
    """Raised when PDF page count exceeds maximum allowed limit (5 pages)."""


class NoClinicalDataFoundError(InvalidClinicalDocumentError):
    """Raised when document extraction yields zero recognisable clinical modules."""


class UnsupportedClinicalModuleError(ClinicalScanDomainError):
    """Unknown module name."""


class RecordAlreadyExistsError(ClinicalScanDomainError):
    def __init__(self, message: str, existing_record_id: str = ""):
        super().__init__(message)
        self.existing_record_id = existing_record_id


class ExtractionConfigurationError(ClinicalScanDomainError):
    """Raised when AI extraction is misconfigured (e.g. missing API key)."""


class ExtractionAuthError(ClinicalScanDomainError):
    """Raised when scanning service credentials are invalid, revoked, or expired."""

    def __init__(self, message: str, reason_code: str | None = None):
        super().__init__(message)
        self.reason_code = reason_code or "auth_failed"


class ExtractionRateLimitError(ClinicalScanDomainError):
    pass


class ExtractionServiceError(ClinicalScanDomainError):
    pass


class ClinicalRecordNotFoundError(ClinicalScanDomainError):
    """Clinical record missing or not owned by this patient."""


class CatalogFieldKeyError(ClinicalScanDomainError):
    """fieldKey is missing, inactive, or the wrong lab/vital type."""
