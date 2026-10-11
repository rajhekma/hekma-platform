"""Value objects for the Hekma FHIR dual-write path."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


HEKMA_ID_SYSTEM = "https://hekma.ai/fhir/id"
HEKMA_SOURCE_SYSTEM = "https://hekma.ai/fhir/source"
HEKMA_CTMS_PAYLOAD_URL = "https://hekma.ai/fhir/StructureDefinition/ctms-payload"


class ClinicalSource(str, Enum):
    """Provenance of a FHIR row in fastenhealth_* tables."""

    EHR = "ehr"
    MANUAL = "manual"
    SCAN = "scan"

    @property
    def org_connection_id(self) -> Optional[str]:
        """Sentinel connection id so UNIQUE(patient, org, resource_id) works for non-EHR rows."""
        if self is ClinicalSource.EHR:
            return None
        return f"hekma:{self.value}"


@dataclass(frozen=True)
class FhirProjection:
    """One mapped FHIR resource ready to persist."""

    resource_type: str
    resource: Dict[str, Any]
    mysql_record_id: Optional[int] = None
    document_id: Optional[str] = None


@dataclass
class ProjectionCommand:
    """Inbound dual-write request from REST, scan, or GraphQL."""

    patient_id: str
    module: str
    source: ClinicalSource
    record: Dict[str, Any]
    mysql_record_id: Optional[int] = None
    document_id: Optional[str] = None
    hekma_mail_id: Optional[str] = None
    action: str = "upsert"


@dataclass
class FhirWriteResult:
    """Outcome of a projection; never raised to the clinical write caller."""

    ok: bool
    hekma_id: Optional[str] = None
    fhir_id: Optional[str] = None
    resource_type: Optional[str] = None
    error: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)
