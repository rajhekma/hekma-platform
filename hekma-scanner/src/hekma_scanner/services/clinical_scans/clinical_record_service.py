"""
ClinicalRecordService
=====================
Generic CRUD for the 6 clinical modules. Postgres fastenhealth_* is the only store.
Intercepts free-text notes/comments and anonymizes PII/PHI before storage.
"""
import logging
from typing import Any, Dict, List, Optional

from ...repositories.lab_catalog_repo import LabCatalogRepository
from ..clinical_fhir.hekma_clinical_store import HekmaClinicalStore
from ..clinical_fhir.models import ClinicalSource
from ...services.privacy.privacy_client import privacy_client
from .exceptions import CatalogFieldKeyError, ClinicalRecordNotFoundError
from .allergy_promotion import sync_allergy_like_conditions_to_allergies
from .dashboard_cache import DashboardCacheInvalidator

logger = logging.getLogger("clinical_records")


def enrich_standard_measurement(module: str, data: Dict[str, Any], catalog=None) -> Dict[str, Any]:
    """Copy LOINC, panel, and blank name/unit/range from standard_lab_catalog."""
    raw_key = data.get("fieldKey")
    if not isinstance(raw_key, str) or not raw_key.strip():
        return data
    if module not in {"lab_reports", "vital_signs"}:
        return data

    field_key = raw_key.strip().lower()
    repo = catalog if catalog is not None else LabCatalogRepository()
    item = repo.get(field_key)
    if not item:
        inactive = repo.get(field_key, include_inactive=True)
        if inactive:
            raise CatalogFieldKeyError(f"Standard lab '{field_key}' is inactive")
        raise CatalogFieldKeyError(f"Standard lab '{field_key}' was not found")

    expected_type = "lab" if module == "lab_reports" else "vital"
    if item["record_type"] != expected_type:
        raise CatalogFieldKeyError(
            f"Standard item '{field_key}' is not a {expected_type}"
        )

    enriched = dict(data)
    enriched["fieldKey"] = field_key
    enriched["loincCode"] = item["loinc_code"]
    enriched["category"] = item["category"]
    if module == "lab_reports":
        enriched["testName"] = enriched.get("testName") or item["display_name"]
        enriched["unit"] = enriched.get("unit") or item["conventional_unit"]
        enriched["referenceRange"] = (
            enriched.get("referenceRange") or item["conventional_reference_range"]
        )
    else:
        enriched["type"] = enriched.get("type") or item["display_name"]
        enriched["metric"] = enriched.get("metric") or item["conventional_unit"]
    return enriched


class ClinicalRecordService:
    """Generic CRUD — one instance per module, Postgres-only."""

    def __init__(
        self,
        module: str,
        cache_invalidator: Optional[DashboardCacheInvalidator] = None,
        store: Optional[HekmaClinicalStore] = None,
        fhir_projector=None,
    ):
        self._module = module
        self._store = store or HekmaClinicalStore()
        self._cache = cache_invalidator or DashboardCacheInvalidator()
        # fhir_projector kept so older tests can still pass the kwarg; writes go to store.
        self._fhir = fhir_projector

    def _anonymize_input_data(self, patient_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Anonymizes free-text notes, impressions, and provider details before DB write."""
        if not data:
            return data
        cleaned = dict(data)
        for key in ("note", "notes", "comments", "comment", "doctorName", "doctor_name", "providerName", "provider_name"):
            val = cleaned.get(key)
            if isinstance(val, str) and val.strip():
                try:
                    cleaned[key] = privacy_client.anonymize_text(val, org_id=patient_id)
                except Exception as e:
                    logger.warning("Privacy anonymization fallback for %s field '%s': %s", self._module, key, e)
        return cleaned

    def list_for_patient(
        self, patient_id: str, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        if self._module == "allergies":
            try:
                sync_allergy_like_conditions_to_allergies(patient_id)
            except Exception:
                pass
        return self._store.list_for_patient(patient_id, self._module, limit=limit, offset=offset)

    def get_one(self, patient_id: str, record_id: int) -> Dict[str, Any]:
        return self._store.get_one(patient_id, self._module, record_id)

    def create(self, patient_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        sanitized_data = self._anonymize_input_data(patient_id, data)
        created = self._store.create(
            patient_id,
            self._module,
            self._enrich_standard_measurement(sanitized_data),
            ClinicalSource.MANUAL,
        )
        self._cache.invalidate_for_modules(patient_id, [self._module])
        return created

    def update(
        self, patient_id: str, record_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        sanitized_data = self._anonymize_input_data(patient_id, data)
        result = self._store.update(
            patient_id,
            self._module,
            record_id,
            sanitized_data,
            ClinicalSource.MANUAL,
        )
        self._cache.invalidate_for_modules(patient_id, [self._module])
        return result

    def remove(self, patient_id: str, record_id: int) -> Dict[str, Any]:
        deleted = self._store.delete(patient_id, self._module, record_id)
        self._cache.invalidate_for_modules(patient_id, [self._module])
        return deleted

    def _enrich_standard_measurement(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return enrich_standard_measurement(self._module, data)
