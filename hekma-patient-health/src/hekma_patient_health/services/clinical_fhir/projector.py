"""Best-effort dual-write of CTMS rows into fastenhealth_* FHIR tables."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from ...repositories.hekma_fhir_link_repo import (
    FhirLinkRepository,
    PostgresFhirLinkRepository,
)
from ..clinical_scans.clinical_record_service import enrich_standard_measurement
from ..clinical_scans.exceptions import CatalogFieldKeyError
from ..clinical_scans.modules import ClinicalModule
from .identity import fhir_id_for_source, stable_hekma_id, stamp_ctms_payload, stamp_hekma_identifiers
from .mappers import MapperRegistry
from .models import ClinicalSource, FhirWriteResult, ProjectionCommand
from .store import FhirResourceStore, PostgresFastenStore

logger = logging.getLogger(__name__)


def dual_write_enabled() -> bool:
    """Off switch so a bad FHIR write cannot be forced on in an emergency."""
    return os.getenv("CLINICAL_FHIR_DUAL_WRITE", "Y").strip().upper() in {
        "Y",
        "1",
        "TRUE",
        "YES",
    }


class ClinicalFhirProjector:
    """Maps a MySQL clinical row to FHIR and upserts it; never raises to callers."""

    def __init__(
        self,
        store: Optional[FhirResourceStore] = None,
        links: Optional[FhirLinkRepository] = None,
        mappers: Optional[MapperRegistry] = None,
        catalog=None,
    ):
        self._store = store or PostgresFastenStore()
        self._links = links or PostgresFhirLinkRepository()
        self._mappers = mappers or MapperRegistry()
        self._catalog = catalog

    def project_mysql_row(
        self,
        patient_id: str,
        module: str,
        record: Dict[str, Any],
        source: ClinicalSource,
        document_id: Optional[str] = None,
        hekma_mail_id: Optional[str] = None,
    ) -> FhirWriteResult:
        """Upsert FHIR for a CTMS row. Failures are logged, not raised."""
        mysql_id = _mysql_id(record)
        return self.execute(
            ProjectionCommand(
                patient_id=str(patient_id),
                module=module,
                source=source,
                record=record,
                mysql_record_id=mysql_id,
                document_id=document_id,
                hekma_mail_id=hekma_mail_id,
                action="upsert",
            )
        )

    def retire_mysql_row(
        self, patient_id: str, module: str, mysql_record_id: int
    ) -> FhirWriteResult:
        """Mark the linked FHIR resource entered-in-error / inactive."""
        return self.execute(
            ProjectionCommand(
                patient_id=str(patient_id),
                module=module,
                source=ClinicalSource.MANUAL,
                record={},
                mysql_record_id=int(mysql_record_id),
                action="retire",
            )
        )

    def execute(self, command: ProjectionCommand) -> FhirWriteResult:
        if not dual_write_enabled():
            return FhirWriteResult(ok=True, extras={"skipped": "disabled"})
        if isinstance(command.source, str):
            try:
                command.source = ClinicalSource(command.source)
            except ValueError:
                command.source = ClinicalSource.MANUAL
        try:
            module = ClinicalModule.from_value(command.module)
        except ValueError as exc:
            logger.warning("FHIR project skipped unknown module=%s", command.module)
            return FhirWriteResult(ok=False, error=str(exc))
        try:
            if command.action == "retire":
                return self._retire(command, module)
            return self._upsert(command, module)
        except Exception as exc:
            logger.warning(
                "FHIR dual-write failed patient_id=%s module=%s mysql_id=%s error=%s",
                command.patient_id,
                command.module,
                command.mysql_record_id,
                exc,
            )
            return FhirWriteResult(ok=False, error=str(exc))

    def _upsert(self, command: ProjectionCommand, module: ClinicalModule) -> FhirWriteResult:
        record = dict(command.record or {})
        if module.value in {"lab_reports", "vital_signs"}:
            try:
                record = enrich_standard_measurement(module.value, record, self._catalog)
            except CatalogFieldKeyError as exc:
                return FhirWriteResult(
                    ok=False, error=str(exc), extras={"catalogFieldKey": True}
                )
        command.record = record
        mapper = self._mappers.mapper_for(module)
        resource = mapper.to_fhir(command.patient_id, record)
        hekma_id, fhir_id = self._resolve_ids(command, module)
        stamped = stamp_hekma_identifiers(
            resource,
            hekma_id=hekma_id,
            fhir_id=fhir_id,
            source=command.source,
        )
        stamped = stamp_ctms_payload(stamped, command.record)
        org_id = command.source.org_connection_id
        self._store.upsert(
            patient_id=command.patient_id,
            hekma_mail_id=command.hekma_mail_id,
            org_connection_id=org_id,
            resource_id=fhir_id,
            hekma_id=hekma_id,
            source=command.source,
            resource=stamped,
        )
        if command.mysql_record_id is not None:
            self._links.save(
                hekma_id=hekma_id,
                patient_id=command.patient_id,
                module=module.value,
                mysql_record_id=command.mysql_record_id,
                fhir_resource_type=mapper.resource_type,
                fhir_id=fhir_id,
                source=command.source.value,
                document_id=command.document_id,
            )
        return FhirWriteResult(
            ok=True,
            hekma_id=hekma_id,
            fhir_id=fhir_id,
            resource_type=mapper.resource_type,
        )

    def _retire(
        self, command: ProjectionCommand, module: ClinicalModule
    ) -> FhirWriteResult:
        if command.mysql_record_id is None:
            return FhirWriteResult(ok=False, error="mysql_record_id required to retire")
        link = self._links.get(
            command.patient_id, module.value, command.mysql_record_id
        )
        if not link:
            return FhirWriteResult(ok=True, extras={"skipped": "no_link"})
        source = ClinicalSource(link["source"]) if link.get("source") in (
            s.value for s in ClinicalSource
        ) else ClinicalSource.MANUAL
        self._store.mark_entered_in_error(
            resource_type=link["fhir_resource_type"],
            patient_id=command.patient_id,
            org_connection_id=source.org_connection_id,
            resource_id=link["fhir_id"],
            hekma_id=str(link["hekma_id"]),
        )
        return FhirWriteResult(
            ok=True,
            hekma_id=str(link["hekma_id"]),
            fhir_id=link["fhir_id"],
            resource_type=link["fhir_resource_type"],
        )

    def _resolve_ids(
        self,
        command: ProjectionCommand,
        module: ClinicalModule,
    ) -> tuple:
        if command.mysql_record_id is not None:
            existing = self._links.get(
                command.patient_id, module.value, command.mysql_record_id
            )
            if existing:
                return str(existing["hekma_id"]), str(existing["fhir_id"])
        hekma_id = stable_hekma_id(
            command.source,
            command.patient_id,
            module.value,
            command.mysql_record_id,
        )
        fhir_id = fhir_id_for_source(command.source, hekma_id, None)
        return hekma_id, fhir_id


def _mysql_id(record: Dict[str, Any]) -> Optional[int]:
    raw = record.get("id") if isinstance(record, dict) else None
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
