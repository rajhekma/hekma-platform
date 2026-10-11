import hashlib
import re
import time
from typing import Any, Dict, List, Optional

from ...repositories.medication_repo import get_medications_by_patient
from ...repositories.prescriptions_repo import (
    count_medications_for_prescription,
    create_prescription,
    find_prescription_by_content_hash,
    get_prescription,
    get_prescriptions_by_patient,
    update_prescription,
)
from ...utils.serialization import medications_response, prescription_response, prescriptions_response, to_camel_case
from .exceptions import InvalidPrescriptionError, PrescriptionAlreadyExistsError
from .extraction.mapper import PrescriptionDataMapper
from .extraction.mime_resolver import guess_mime_type_from_filename
from .extraction.openai_extractor import OpenAIPrescriptionExtractor
from .extraction.protocols import PrescriptionExtractor
from .medication_service import MedicationService
from .schedule_service import MedicationScheduleService


class PrescriptionService:
    """Handles prescription scanning, persistence, and medication creation."""

    def __init__(
        self,
        extractor: Optional[PrescriptionExtractor] = None,
        medication_service: Optional[MedicationService] = None,
        schedule_service: Optional[MedicationScheduleService] = None,
        mapper: Optional[PrescriptionDataMapper] = None,
    ):
        self._extractor = extractor or OpenAIPrescriptionExtractor()
        self._medications = medication_service or MedicationService(schedule_service)
        self._mapper = mapper or PrescriptionDataMapper()

    @staticmethod
    def _compute_hash(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _resolve_duplicate_or_orphan(
        self, patient_id: str, content_hash: str
    ) -> Optional[Dict[str, Any]]:
        """
        Block only when the same document already has saved medications.

        An unfinished scan (prescription row, zero linked meds) is returned so
        the caller can refresh it instead of raising.
        """
        existing = find_prescription_by_content_hash(patient_id, content_hash)
        if not existing:
            return None
        if count_medications_for_prescription(existing["id"]) > 0:
            raise PrescriptionAlreadyExistsError(
                existing_prescription_id=existing["id"]
            )
        return existing

    @staticmethod
    def _normalize_medicine_name(name: Any) -> str:
        return re.sub(r"\s+", " ", (name or "").strip().lower())

    def _extracted_medicines_already_active(
        self, patient_id: str, extracted: Dict[str, Any]
    ) -> bool:
        """
        Detect when the same prescription was already saved through another path.

        Preview scan + bulk add can leave the prescription row with zero linked
        meds while the patient already has the extracted medicines active.
        """
        target_names = {
            self._normalize_medicine_name(item.get("name"))
            for item in extracted.get("medicines") or []
            if (item.get("name") or "").strip()
        }
        target_names.discard("")
        if not target_names:
            return False

        active_names = {
            self._normalize_medicine_name(row.get("name"))
            for row in get_medications_by_patient(patient_id)
            if row.get("status") == "Active" and (row.get("name") or "").strip()
        }
        return target_names.issubset(active_names)

    def _ensure_not_already_saved(
        self,
        patient_id: str,
        extracted: Optional[Dict[str, Any]],
        persist_medications: bool,
        existing: Optional[Dict[str, Any]],
    ) -> None:
        if not persist_medications or not extracted:
            return
        if self._extracted_medicines_already_active(patient_id, extracted):
            raise PrescriptionAlreadyExistsError(
                existing_prescription_id=(existing or {}).get("id") or 0
            )

    def _persist_prescription_row(
        self,
        patient_id: str,
        payload: Dict[str, Any],
        orphan: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Insert a new prescription, or refresh an unfinished same-document scan."""
        if orphan:
            return update_prescription(orphan["id"], payload)
        return create_prescription(patient_id, payload)

    def register_from_url(self, patient_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        source_url = body.get("sourceUrl") or body.get("imageUrl")
        extracted = None

        if body.get("extract"):
            if not source_url:
                raise InvalidPrescriptionError(
                    "sourceUrl or imageUrl is required when extract=true"
                )
            if hasattr(self._extractor, "bind_usage"):
                self._extractor.bind_usage(patient_id=str(patient_id), product="scan_ai")
            extracted = self._extractor.extract_from_url(source_url)

        payload = self._build_prescription_payload(body, source_url, extracted)
        orphan = None

        if source_url:
            import urllib.request

            content_hash = self._compute_hash(urllib.request.urlopen(source_url).read())
            orphan = self._resolve_duplicate_or_orphan(patient_id, content_hash)
            payload["contentHash"] = content_hash

        if extracted:
            self._ensure_not_already_saved(
                patient_id, extracted, body.get("persistMedications"), orphan
            )

        prescription = self._persist_prescription_row(patient_id, payload, orphan)
        return self._build_scan_response(
            patient_id,
            prescription,
            extracted,
            body.get("persistMedications"),
            body.get("autoSchedule", False),
        )

    def register_from_upload(
        self,
        patient_id: str,
        file_bytes: bytes,
        filename: str,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        mime_type = guess_mime_type_from_filename(
            filename, (options.get("contentType") or "").lower()
        )
        content_hash = self._compute_hash(file_bytes)
        orphan = self._resolve_duplicate_or_orphan(patient_id, content_hash)

        extracted = None
        if options.get("extract", True):
            if hasattr(self._extractor, "bind_usage"):
                self._extractor.bind_usage(patient_id=str(patient_id), product="scan_ai")
            extracted = self._extractor.extract_from_bytes(file_bytes, mime_type)

        payload = {
            "imageUrl": options.get("imageUrl") or f"upload://{filename}",
            "scannedAt": options.get("scannedAt") or int(time.time() * 1000),
            "prescriptionDate": options.get("prescriptionDate"),
            "prescriberName": options.get("prescriberName"),
        }
        if extracted:
            payload = self._mapper.enrich_prescription_payload(payload, extracted)

        payload["contentHash"] = content_hash
        self._ensure_not_already_saved(
            patient_id,
            extracted,
            options.get("persistMedications"),
            orphan,
        )
        prescription = self._persist_prescription_row(patient_id, payload, orphan)
        return self._build_scan_response(
            patient_id,
            prescription,
            extracted,
            options.get("persistMedications"),
            options.get("autoSchedule", False),
        )

    def list_for_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        return prescriptions_response(get_prescriptions_by_patient(patient_id))

    def get_for_patient(
        self, patient_id: str, prescription_id: int
    ) -> Optional[Dict[str, Any]]:
        prescription = get_prescription(prescription_id)
        if not prescription or prescription.get("patient_id") != patient_id:
            return None
        return prescription_response(dict(prescription))

    def _build_prescription_payload(
        self,
        body: Dict[str, Any],
        source_url: Optional[str],
        extracted: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload = dict(body)
        if source_url and not payload.get("imageUrl"):
            payload["imageUrl"] = source_url
        if not payload.get("scannedAt"):
            payload["scannedAt"] = int(time.time() * 1000)
        if extracted:
            payload = self._mapper.enrich_prescription_payload(payload, extracted)
        return payload

    def _build_scan_response(
        self,
        patient_id: str,
        prescription: Dict[str, Any],
        extracted: Optional[Dict[str, Any]],
        persist_medications: bool,
        auto_schedule: bool,
    ) -> Dict[str, Any]:
        created_medications: List[Dict[str, Any]] = []
        if persist_medications and extracted:
            created_medications = self._persist_medications(
                patient_id, prescription["id"], extracted, auto_schedule
            )

        result: Dict[str, Any] = {
            "prescription": prescription_response(dict(prescription)),
            "medicationsCreated": medications_response(created_medications),
        }
        if extracted is not None:
            result["extractedData"] = extracted
        return result

    def _persist_medications(
        self,
        patient_id: str,
        prescription_id: int,
        extracted: Dict[str, Any],
        auto_schedule: bool,
    ) -> List[Dict[str, Any]]:
        payloads = []
        for med_payload in self._mapper.to_medication_payloads(extracted):
            med_payload["prescriptionId"] = prescription_id
            payloads.append(med_payload)

        # create_bulk validates every medication before writing any, so one bad
        # row cannot leave the rest of the prescription half-saved.
        return self._medications.create_bulk(patient_id, payloads, auto_schedule)
