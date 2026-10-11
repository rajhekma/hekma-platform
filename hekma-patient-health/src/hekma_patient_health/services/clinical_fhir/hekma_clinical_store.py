"""Postgres-only store for manual and scan clinical records.

Writes FHIR into fastenhealth_* and never touches MySQL CTMS tables.
List/get return the original API payload stamped on the resource.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ...awsutils.postgresql_utils import pg_transaction
from ...fasten_health.db_schema import create_fasten_table, ensure_hekma_identity_columns
from ..clinical_scans.exceptions import ClinicalRecordNotFoundError, RecordAlreadyExistsError
from ..clinical_scans.modules import ClinicalModule
from .identity import (
    fhir_id_for_source,
    mint_hekma_id,
    read_ctms_payload,
    stamp_ctms_payload,
    stamp_hekma_identifiers,
)
from ...utils.vital_signs_normalization import normalize_vital_sign_record
from .mappers import MapperRegistry
from .models import ClinicalSource
from .store import PostgresFastenStore

logger = logging.getLogger(__name__)

# FHIR raw_resource is authoritative for clinical lifecycle fields; stamped CTMS
# extensions can lag behind direct GraphQL/FHIR updates.
_FHIR_WINS_OVER_STAMP = frozenset(
    {
        "status",
        "startDate",
        "start_date",
        "onsetDate",
        "onset",
        "endDate",
        "end_date",
        "category",
        "allergyType",
        "allergy_type",
        "substance",
        "name",
        "conditionName",
        "reaction",
    }
)

_HEKMA_SOURCES = ("manual", "scan")

# module -> (FHIR resourceType, optional Observation category)
_MODULE_FHIR: Dict[str, Tuple[str, Optional[str]]] = {
    "allergies": ("AllergyIntolerance", None),
    "diagnosis": ("Condition", None),
    "lab_reports": ("Observation", "laboratory"),
    "vital_signs": ("Observation", "vital-signs"),
    "immunization": ("Immunization", None),
    "procedures": ("Procedure", None),
    "medications": ("MedicationRequest", None),
}

# Dedup: JSONB text path + payload field, optional second date field
_DEDUP_FIELDS: Dict[str, Tuple[str, str, Optional[str], Optional[str]]] = {
    "allergies": (
        "raw_resource->'code'->>'text'",
        "substance",
        None,
        None,
    ),
    "diagnosis": (
        "raw_resource->'code'->>'text'",
        "conditionName",
        "LEFT(COALESCE(raw_resource->>'onsetDateTime',''), 10)",
        "startDate",
    ),
    "lab_reports": (
        "raw_resource->'code'->>'text'",
        "testName",
        "LEFT(COALESCE(raw_resource->>'effectiveDateTime',''), 10)",
        "resultDate",
    ),
    "vital_signs": (
        "raw_resource->'code'->>'text'",
        "type",
        "LEFT(COALESCE(raw_resource->>'effectiveDateTime',''), 10)",
        "dateOfObservation",
    ),
    "immunization": (
        "raw_resource->'vaccineCode'->>'text'",
        "vaccineName",
        "LEFT(COALESCE(raw_resource->>'occurrenceDateTime',''), 10)",
        "vaccinationDate",
    ),
    "procedures": (
        "raw_resource->'code'->>'text'",
        "procedureName",
        "LEFT(COALESCE(raw_resource->'performedPeriod'->>'start',''), 10)",
        "startDate",
    ),
    "medications": (
        "raw_resource->'medicationCodeableConcept'->>'text'",
        "name",
        "LEFT(COALESCE(raw_resource->>'authoredOn',''), 10)",
        "prescriptionDate",
    ),
}


class HekmaClinicalStore:
    """Authoritative CRUD for plus-button and document-scan clinical facts."""

    def __init__(self, pg_store: Optional[PostgresFastenStore] = None):
        self._pg = pg_store or PostgresFastenStore()
        self._mappers = MapperRegistry()

    def list_for_patient(
        self, patient_id: str, module: str, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        resource_type, category = _module_fhir(module)
        rows = self._pg.list_hekma_rows(
            resource_type=resource_type,
            patient_id=str(patient_id),
            limit=limit,
            offset=offset,
            observation_category=category,
        )
        return [self._to_api(row, patient_id, module) for row in rows]

    def get_one(self, patient_id: str, module: str, record_id: int) -> Dict[str, Any]:
        resource_type, _ = _module_fhir(module)
        row = self._pg.get_hekma_row(
            resource_type=resource_type,
            patient_id=str(patient_id),
            record_id=int(record_id),
        )
        if not row or _is_retired(row.get("raw_resource") or {}):
            raise ClinicalRecordNotFoundError(
                f"{module} record {record_id} not found for patient {patient_id}"
            )
        return self._to_api(row, patient_id, module)

    def create(
        self,
        patient_id: str,
        module: str,
        data: Dict[str, Any],
        source: ClinicalSource = ClinicalSource.MANUAL,
    ) -> Dict[str, Any]:
        existing = self.find_duplicate(patient_id, module, data)
        if existing:
            raise RecordAlreadyExistsError(
                _dup_message(module, data),
                existing_record_id=str(existing.get("id") or ""),
            )
        row_id = self._write(patient_id, module, data, source, hekma_id=mint_hekma_id())
        return self.get_one(patient_id, module, row_id)

    def update(
        self,
        patient_id: str,
        module: str,
        record_id: int,
        data: Dict[str, Any],
        source: Optional[ClinicalSource] = None,
    ) -> Dict[str, Any]:
        resource_type, _ = _module_fhir(module)
        row = self._pg.get_hekma_row(
            resource_type=resource_type,
            patient_id=str(patient_id),
            record_id=int(record_id),
        )
        if not row or _is_retired(row.get("raw_resource") or {}):
            raise ClinicalRecordNotFoundError(
                f"{module} record {record_id} not found for patient {patient_id}"
            )
        src = source or _source_from_row(row)
        merged = dict(self._to_api(row, patient_id, module))
        merged.update({k: v for k, v in data.items() if v is not None})
        hekma_id = str(row.get("hekma_id") or mint_hekma_id())
        self._write(patient_id, module, merged, src, hekma_id=hekma_id)
        return self.get_one(patient_id, module, record_id)

    def delete(self, patient_id: str, module: str, record_id: int) -> Dict[str, Any]:
        resource_type, _ = _module_fhir(module)
        row = self._pg.get_hekma_row(
            resource_type=resource_type,
            patient_id=str(patient_id),
            record_id=int(record_id),
        )
        if not row or _is_retired(row.get("raw_resource") or {}):
            raise ClinicalRecordNotFoundError(
                f"{module} record {record_id} not found for patient {patient_id}"
            )
        src = _source_from_row(row)
        self._pg.mark_entered_in_error(
            resource_type=resource_type,
            patient_id=str(patient_id),
            org_connection_id=src.org_connection_id,
            resource_id=str(row.get("resource_id") or ""),
            hekma_id=str(row.get("hekma_id") or "") or None,
        )
        return {"deleted": True, "recordId": record_id}

    def find_duplicate(
        self, patient_id: str, module: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        spec = _DEDUP_FIELDS.get(module)
        if not spec:
            return None
        name_sql, name_field, date_sql, date_field = spec
        name = str(data.get(name_field) or data.get("name") or "").strip()
        if not name:
            return None
        resource_type, category = _module_fhir(module)
        table = f"fastenhealth_{resource_type.lower()}"
        params: list = [str(patient_id), name.lower()]
        extra = ""
        if date_sql and date_field:
            date_val = str(data.get(date_field) or "")[:10]
            if date_val:
                extra = f" AND {date_sql} = %s"
                params.append(date_val)
        if category:
            extra += " AND raw_resource->'category'->0->'coding'->0->>'code' = %s"
            params.append(category)
        with pg_transaction(dict_cursor=True) as (_, cur):
            create_fasten_table(cur, resource_type)
            ensure_hekma_identity_columns(cur, table)
            cur.execute(
                f"""
                SELECT id, patient_id, hekma_id, source, resource_id, raw_resource, created_at
                FROM {table}
                WHERE patient_id = %s
                  AND (
                    COALESCE(source, '') IN ('manual', 'scan')
                    OR org_connection_id IN ('hekma:manual', 'hekma:scan')
                  )
                  AND COALESCE(raw_resource->>'status', '') <> 'entered-in-error'
                  AND COALESCE(
                        raw_resource->'verificationStatus'->'coding'->0->>'code',
                        ''
                      ) <> 'entered-in-error'
                  AND LOWER({name_sql}) = %s
                  {extra}
                ORDER BY id DESC
                LIMIT 1
                """,
                tuple(params),
            )
            row = cur.fetchone()
        return self._to_api(dict(row), patient_id, module) if row else None

    def _write(
        self,
        patient_id: str,
        module: str,
        data: Dict[str, Any],
        source: ClinicalSource,
        *,
        hekma_id: str,
    ) -> int:
        module_enum = ClinicalModule.from_value(module)
        mapper = self._mappers.mapper_for(module_enum)
        if module == "vital_signs":
            data = normalize_vital_sign_record(data)
        fhir_id = fhir_id_for_source(source, hekma_id, None)
        resource = mapper.to_fhir(str(patient_id), data)
        resource = stamp_hekma_identifiers(
            resource, hekma_id=hekma_id, fhir_id=fhir_id, source=source
        )
        resource = stamp_ctms_payload(resource, data)
        row_id = self._pg.upsert(
            patient_id=str(patient_id),
            hekma_mail_id=None,
            org_connection_id=source.org_connection_id,
            resource_id=fhir_id,
            hekma_id=hekma_id,
            source=source,
            resource=resource,
        )
        if not row_id:
            raise RuntimeError(f"Postgres write returned no id for {module}")
        logger.info(
            "Hekma clinical %s saved | patient_id=%s module=%s source=%s id=%s",
            "create" if data.get("id") is None else "upsert",
            patient_id,
            module,
            source.value,
            row_id,
        )
        return int(row_id)

    def _to_api(self, row: Dict[str, Any], patient_id: str, module: str) -> Dict[str, Any]:
        raw = row.get("raw_resource") or {}
        if not isinstance(raw, dict):
            raw = {}
        reconstructed: Dict[str, Any] = {}
        try:
            mapper = self._mappers.mapper_for(ClinicalModule.from_value(module))
            reconstructed = mapper.from_fhir(raw) or {}
        except (ValueError, AttributeError, TypeError):
            reconstructed = {}
        stamped = read_ctms_payload(raw)
        out = dict(reconstructed)
        for key, value in stamped.items():
            if value is None:
                continue
            if key in _FHIR_WINS_OVER_STAMP and reconstructed.get(key) not in (None, ""):
                continue
            if value != "" or not out.get(key):
                out[key] = value
        out["id"] = int(row["id"])
        out["patientId"] = str(patient_id)
        out["hekmaId"] = str(row.get("hekma_id") or "")
        out["source"] = str(row.get("source") or "manual")
        return out


def _module_fhir(module: str) -> Tuple[str, Optional[str]]:
    try:
        mapped = _MODULE_FHIR[ClinicalModule.from_value(module).value]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Unsupported clinical module: {module}") from exc
    return mapped


def _source_from_row(row: Dict[str, Any]) -> ClinicalSource:
    raw = str(row.get("source") or "manual").lower()
    if raw == ClinicalSource.SCAN.value:
        return ClinicalSource.SCAN
    return ClinicalSource.MANUAL


def _is_retired(raw: Dict[str, Any]) -> bool:
    """True only for soft-deleted rows. Inactive/resolved remain listable."""
    if str(raw.get("status") or "").lower() == "entered-in-error":
        return True
    vs = raw.get("verificationStatus") or {}
    if isinstance(vs, dict):
        for coding in vs.get("coding") or []:
            if isinstance(coding, dict) and str(coding.get("code") or "").lower() == "entered-in-error":
                return True
    return False


def _dup_message(module: str, data: Dict[str, Any]) -> str:
    name = (
        data.get("substance")
        or data.get("conditionName")
        or data.get("testName")
        or data.get("type")
        or data.get("vaccineName")
        or data.get("procedureName")
        or data.get("name")
        or data.get("medicationName")
        or "record"
    )
    return f"{module} '{name}' already exists for this patient"
