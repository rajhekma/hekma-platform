"""
SmartClinicalScanService
========================
Universal scan orchestrator — 6 parallel focused calls via ThreadPoolExecutor, all 6 modules, any document type.

Design principles:
  - Parallel focused extraction across all 6 strategies via ThreadPoolExecutor (~3s latency)
  - Enforces document constraints from clinical_scan_config.json (file size + PDF page cap)
  - persistRecords=false (default) → preview only, nothing written to DB
  - persistRecords=true → save scan metadata + clinical records
  - optional `modules` list → save only user-selected modules from what was detected
  - Server derives detectedModules from non-empty arrays (never trusts OpenAI self-report)
  - Per-module try/except → one module failing never kills the full response
    (structural errors like file-size / PDF page-limit failures still abort the scan)
"""
import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import requests

from ...repositories.clinical_scans_repo import (
    ScanHashConflictError,
    create_clinical_scan,
    find_existing_scan_by_semantic_data,
    get_clinical_scan,
    get_clinical_scan_by_hash,
    get_clinical_scans_by_patient,
    soft_delete_clinical_scan,
    update_clinical_scan,
)
from ..medications.extraction.mime_resolver import (
    guess_mime_type_from_filename,
    guess_mime_type_from_url,
)
from .exceptions import (
    ClinicalScanAlreadyExistsError,
    FileSizeExceededError,
    InvalidClinicalDocumentError,
    NoClinicalDataFoundError,
    PdfPageLimitExceededError,
    RecordAlreadyExistsError,
)
from .allergy_promotion import promote_allergy_like_conditions
from ...utils.medication_form_inference import enrich_extracted_medicines
from ..clinical_fhir.hekma_clinical_store import HekmaClinicalStore
from .dashboard_cache import DashboardCacheInvalidator
from .modules import ClinicalModule
from .strategies import build_strategy_registry
from .vision_extractor import OpenAIClinicalVisionExtractor
from ..medications.exceptions import PrescriptionAlreadyExistsError
from ..medications.prescription_service import PrescriptionService
from ...config.clinical_scan_config import get_clinical_scan_config
from ...utils.prescription_dates import normalize_prescription_date
from ...utils.serialization import prescription_response, to_camel_case

logger = logging.getLogger(__name__)

# Maps combined extraction key → clinical module name
_ARRAY_TO_MODULE: Dict[str, str] = {
    "lab_results":   "lab_reports",
    "vitals":        "vital_signs",
    "immunizations": "immunization",
    "procedures":    "procedures",
    "conditions":    "diagnosis",
    "allergies":     "allergies",
    "medicines":     "medications",
    "medications":   "medications",
}


def _derive_detected_modules(extracted: Dict[str, Any]) -> List[str]:
    """
    Derive which modules are present by inspecting actual array content.
    Never trusts OpenAI's self-reported detectedModules — server validates.
    """
    return list(dict.fromkeys([m for key, m in _ARRAY_TO_MODULE.items() if extracted.get(key)]))


def _modules_with_persisted_rows(results: Dict[str, Any]) -> List[str]:
    """Modules that wrote a scan row or clinical records (dashboard cache bust)."""
    written: List[str] = []
    for name, result in results.items():
        if not isinstance(result, dict) or result.get("skipped"):
            continue
        if result.get("scanId") or result.get("recordsCreated"):
            written.append(name)
    return written


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


MAX_FILE_SIZE_BYTES = get_clinical_scan_config().max_file_size_bytes


def _validate_file_size(file_bytes: bytes) -> None:
    """Reject empty uploads and files over configured maxFileSizeMb."""
    if not file_bytes:
        raise InvalidClinicalDocumentError("Uploaded file is empty")
    limit = get_clinical_scan_config().max_file_size_bytes
    limit_mb = get_clinical_scan_config().max_file_size_mb
    if len(file_bytes) > limit:
        raise FileSizeExceededError(
            f"File size ({len(file_bytes) / (1024 * 1024):.1f} MB) exceeds maximum limit of {limit_mb} MB"
        )


def _download_bytes(url: str):
    from ...utils.url_safety import UnsafeDownloadUrlError, assert_safe_download_url

    try:
        assert_safe_download_url(url)
    except UnsafeDownloadUrlError as exc:
        raise InvalidClinicalDocumentError(str(exc)) from exc
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        if not resp.content:
            raise InvalidClinicalDocumentError("Downloaded document is empty")
        _validate_file_size(resp.content)
        return resp.content, resp.headers.get("Content-Type")
    except InvalidClinicalDocumentError:
        raise
    except requests.RequestException as exc:
        raise InvalidClinicalDocumentError(
            "Could not download document from the provided URL"
        ) from exc


class SmartClinicalScanService:
    """
    Universal scan orchestrator — handles any clinical document, all 7 modules (including medications).
    Always uses parallel focused OpenAI calls via ThreadPoolExecutor to extract all module types.
    """

    def __init__(
        self,
        extractor: Optional[OpenAIClinicalVisionExtractor] = None,
        strategies: Optional[Dict[ClinicalModule, Any]] = None,
        cache_invalidator: Optional[DashboardCacheInvalidator] = None,
        fhir_projector=None,
        prescription_service: Optional[PrescriptionService] = None,
    ):
        self._extractor  = extractor  or OpenAIClinicalVisionExtractor()
        self._strategies = strategies or build_strategy_registry()
        self._cache = cache_invalidator or DashboardCacheInvalidator()
        # fhir_projector kept so older callers can pass it; writes go to Postgres only.
        self._fhir = fhir_projector
        self._prescriptions = prescription_service or PrescriptionService()

    # ── Public entry points ──────────────────────────────────────────────────

    def register_from_upload(
        self,
        patient_id: str,
        file_bytes: bytes,
        filename: str,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        if file_bytes or not options.get("extractedData"):
            _validate_file_size(file_bytes)
        mime_type = guess_mime_type_from_filename(
            filename, (options.get("contentType") or "").lower()
        )
        image_url = options.get("imageUrl") or f"upload://{filename}"
        return self._run(patient_id, file_bytes, mime_type, image_url, options)

    def register_from_url(
        self, patient_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        source_url = body.get("sourceUrl") or body.get("imageUrl")
        if not source_url:
            raise InvalidClinicalDocumentError("sourceUrl or imageUrl is required")
        file_bytes, content_type = _download_bytes(source_url)
        mime_type = guess_mime_type_from_url(source_url, content_type)
        return self._run(patient_id, file_bytes, mime_type, source_url, body)

    def list_for_patient(self, patient_id: str, module_name: Optional[str] = None) -> List[Dict[str, Any]]:
        module_value = None
        if module_name:
            try:
                module_value = ClinicalModule.from_value(module_name).value
            except ValueError:
                pass
        return [dict(r) for r in get_clinical_scans_by_patient(patient_id, module_value)]

    def get_for_patient(self, patient_id: str, scan_id: int) -> Optional[Dict[str, Any]]:
        """Load one scan for patient; patient_id compared as string for UI/path mismatches."""
        scan = get_clinical_scan(scan_id)
        if not scan or str(scan.get("patient_id")) != str(patient_id):
            return None
        if int(scan.get("is_deleted") or 0) == 1:
            return None
        return dict(scan)

    def delete_for_patient(self, patient_id: str, scan_id: int) -> bool:
        """
        Soft-delete the scan row and the clinical records saved from that scan.

        GraphQL / the app read LabReports etc., not clinical_document_scans, so
        scan-only delete left dashboard data in place. Idempotent if the scan
        was already flagged deleted.
        """
        scan = get_clinical_scan(scan_id)
        if not scan or str(scan.get("patient_id")) != str(patient_id):
            return False
        self._soft_delete_scan_clinical_records(patient_id, scan)
        if int(scan.get("is_deleted") or 0) != 1:
            if not soft_delete_clinical_scan(scan_id):
                return False
        module_name = str(scan.get("module") or "").strip()
        if module_name:
            self._cache.invalidate_for_modules(patient_id, [module_name])
        return True

    def _soft_delete_scan_clinical_records(
        self, patient_id: str, scan: Dict[str, Any]
    ) -> int:
        """Soft-delete target-table rows that match this scan's extracted payloads."""
        module_name = str(scan.get("module") or "").strip()
        try:
            module = ClinicalModule.from_value(module_name)
        except ValueError:
            return 0
        strategy = self._strategies.get(module)
        if not strategy:
            return 0
        extracted = scan.get("extracted_data") or scan.get("extractedData") or {}
        if not isinstance(extracted, dict):
            return 0
        deleted = 0
        store = HekmaClinicalStore()
        for payload in strategy.map_records(extracted):
            try:
                existing = strategy.matching_record(patient_id, payload)
            except Exception as exc:
                logger.warning(
                    "SMART_SCAN delete lookup failed patient_id=%s module=%s: %s",
                    patient_id,
                    module.value,
                    exc,
                )
                continue
            rec_id = (existing or {}).get("id") if isinstance(existing, dict) else None
            if rec_id is None:
                continue
            try:
                store.delete(patient_id, module.value, int(rec_id))
                deleted += 1
            except Exception as exc:
                logger.warning(
                    "SMART_SCAN delete record failed patient_id=%s module=%s record_id=%s: %s",
                    patient_id,
                    module.value,
                    rec_id,
                    exc,
                )
        logger.info(
            "SMART_SCAN delete records patient_id=%s scan_id=%s module=%s count=%s",
            patient_id,
            scan.get("id"),
            module.value,
            deleted,
        )
        return deleted

    def _ensure_not_duplicate(
        self, patient_id: str, content_hash: str, options: Dict[str, Any]
    ) -> None:
        if not content_hash or options.get("skipDuplicateCheck", False):
            return
        if options.get("overwrite") or options.get("forceSave"):
            logger.info(
                "SMART_SCAN duplicate check skipped patient_id=%s reason=forceSave/overwrite hash=%s",
                patient_id,
                content_hash[:12],
            )
            return
        existing = get_clinical_scan_by_hash(patient_id, module=None, content_hash=content_hash)
        if existing:
            scan_id = existing.get("id") or existing.get("scanId") or 0
            logger.info(
                "SMART_SCAN duplicate blocked patient_id=%s existing_scan_id=%s hash=%s",
                patient_id,
                scan_id,
                content_hash[:12],
            )
            raise ClinicalScanAlreadyExistsError(
                "Clinical document has already been scanned for this patient.",
                existing_scan_id=scan_id,
            )

    # ── Core orchestration ───────────────────────────────────────────────────

    def _run(
        self,
        patient_id: str,
        file_bytes: bytes,
        mime_type: str,
        image_url: str,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        persist       = bool(options.get("persistRecords", False))
        module_filter: Optional[List[str]] = options.get("modules")  # user-selected modules
        force_save    = bool(options.get("overwrite") or options.get("forceSave"))

        # Step 1 — Check if pre-extracted data was provided (Option A: skip OpenAI calls on save)
        mode = "parallel"
        extracted = options.get("extractedData")

        content_hash = (
            _hash_bytes(file_bytes) if file_bytes
            else options.get("contentHash") or (extracted.get("content_hash") if isinstance(extracted, dict) else "")
        )

        logger.info(
            "SMART_SCAN start patient_id=%s persist=%s forceSave=%s mime=%s bytes=%s hash=%s "
            "has_extractedData=%s modules_filter=%s",
            patient_id,
            persist,
            force_save,
            mime_type,
            len(file_bytes or b""),
            (content_hash[:12] if content_hash else "-"),
            bool(options.get("extractedData")),
            module_filter,
        )

        # Pre-extraction duplicate check — 0 OpenAI calls if duplicate (runs on Preview & Save)!
        if content_hash:
            self._ensure_not_duplicate(patient_id, content_hash, options)

        if hasattr(self._extractor, "bind_usage"):
            self._extractor.bind_usage(patient_id=str(patient_id), product="scan_ai")

        if not extracted:
            extracted = self._extract_parallel(file_bytes, mime_type)
            extracted = self._fill_missing_modules(file_bytes, mime_type, extracted)
        else:
            logger.info(
                "SMART_SCAN using pre-extracted data patient_id=%s (OpenAI skipped)",
                patient_id,
            )

        extracted = promote_allergy_like_conditions(extracted)
        extracted = enrich_extracted_medicines(extracted)

        # Step 2 — Derive detected modules server-side (cross-validated)
        detected = _derive_detected_modules(extracted)
        logger.info(
            "SMART_SCAN derived patient_id=%s detected=%s counts=%s",
            patient_id,
            detected,
            {
                key: len(extracted.get(key) or [])
                for key in (
                    "lab_results",
                    "vitals",
                    "immunizations",
                    "procedures",
                    "conditions",
                    "allergies",
                    "medicines",
                )
            },
        )
        if not detected:
            logger.info(
                "SMART_SCAN no clinical data patient_id=%s mime=%s",
                patient_id,
                mime_type,
            )
            raise NoClinicalDataFoundError(
                "No recognisable clinical data found in this document."
            )

        # Step 3 — Preview only — return extracted data, write nothing to DB
        if not persist:
            logger.info(
                "SMART_SCAN preview ok patient_id=%s detected=%s",
                patient_id,
                detected,
            )
            return {
                "mode":            mode,
                "detectedModules": detected,
                "extractedData":   extracted,
                "results":         {},
                "message": (
                    "Preview only — no data saved. "
                    "Resubmit with persistRecords=true to save."
                ),
            }

        # Step 4 — Save — apply module filter if user provided one
        content_hash = _hash_bytes(file_bytes)
        if module_filter:
            normalized_filter = []
            for raw_m in module_filter:
                try:
                    normalized_filter.append(ClinicalModule.from_value(raw_m).value)
                except ValueError:
                    normalized_filter.append(raw_m)
            to_save = [m for m in detected if m in normalized_filter]
        else:
            to_save = detected

        logger.info(
            "SMART_SCAN save begin patient_id=%s to_save=%s",
            patient_id,
            to_save,
        )

        results: Dict[str, Any] = {}
        for module_name in to_save:
            results[module_name] = self._process_module(
                patient_id, module_name, extracted,
                content_hash, image_url, options,
            )

        logger.info(
            "SMART_SCAN save ok patient_id=%s saved=%s scan_ids=%s",
            patient_id,
            to_save,
            {
                name: (results.get(name) or {}).get("scanId")
                for name in to_save
            },
        )
        written = _modules_with_persisted_rows(results)
        if written:
            self._cache.invalidate_for_modules(patient_id, written)
        return {
            "mode":            mode,
            "detectedModules": detected,
            "savedModules":    to_save,
            "extractedData":   extracted,
            "results":         results,
        }

    # ── Extraction helpers ───────────────────────────────────────────────────

    def _extract_parallel(self, file_bytes: bytes, mime_type: str) -> Dict[str, Any]:
        """
        Run each module's focused prompt in parallel via ThreadPoolExecutor.
        Total latency ≈ slowest single call (~3 s), not sum of 7 calls.
        Merge all results into one combined dict.
        """
        combined: Dict[str, Any] = {}
        matched: List[str] = []
        mismatched: List[str] = []
        failed: List[str] = []

        logger.info(
            "SMART_SCAN extract parallel start mime=%s modules=%s",
            mime_type,
            [m.value for m in self._strategies],
        )
        with ThreadPoolExecutor(max_workers=len(self._strategies) or 7) as pool:
            futures = {
                pool.submit(
                    self._extractor.extract_from_bytes,
                    file_bytes,
                    mime_type,
                    strategy.extraction_profile(),
                    f"smart_scan.{module.value}",
                ): module
                for module, strategy in self._strategies.items()
            }
            for future in as_completed(futures):
                module = futures[future]
                try:
                    part = future.result()
                    combined.update(part)
                    matched.append(module.value)
                    logger.debug(
                        "SMART_SCAN extract ok module=%s keys=%s",
                        module.value,
                        sorted(part.keys()),
                    )
                except (FileSizeExceededError, PdfPageLimitExceededError):
                    # Structural input errors — abort rather than look like "no clinical data".
                    raise
                except InvalidClinicalDocumentError as exc:
                    # Expected when the doc is not that module type (e.g. Rx vs labs).
                    mismatched.append(module.value)
                    logger.debug(
                        "SMART_SCAN extract mismatch module=%s: %s",
                        module.value,
                        exc,
                    )
                except Exception as exc:
                    failed.append(module.value)
                    logger.warning(
                        "SMART_SCAN extract failed module=%s: %s",
                        module.value,
                        exc,
                    )
        logger.info(
            "SMART_SCAN extract parallel done matched=%s mismatched=%s failed=%s",
            matched,
            mismatched,
            failed,
        )
        # Ensure all array keys present
        for key in ("lab_results", "vitals", "immunizations", "procedures", "conditions", "allergies", "medicines"):
            if key not in combined:
                combined[key] = []
        return combined

    def _fill_missing_modules(
        self,
        file_bytes: bytes,
        mime_type: str,
        extracted: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Mixed OPD sheets can lose a section on a focused call. When at least two
        modules already matched, run one combined Vision pass and copy only the
        arrays that are still empty.
        """
        present = [k for k in _ARRAY_TO_MODULE if extracted.get(k)]
        missing = [k for k in _ARRAY_TO_MODULE if not extracted.get(k)]
        if len(present) < 2 or not missing or not file_bytes:
            return extracted
        logger.info(
            "SMART_SCAN gap-fill start present=%s missing=%s",
            [_ARRAY_TO_MODULE[k] for k in present],
            [_ARRAY_TO_MODULE[k] for k in missing],
        )
        try:
            combined = self._extractor.extract_all_modules(file_bytes, mime_type)
        except Exception as exc:
            logger.warning("SMART_SCAN gap-fill failed: %s", exc)
            return extracted
        if not isinstance(combined, dict):
            return extracted
        for key in missing:
            extra = combined.get(key)
            if isinstance(extra, list) and extra:
                extracted[key] = extra
                logger.info(
                    "SMART_SCAN gap-fill module=%s count=%s",
                    _ARRAY_TO_MODULE[key],
                    len(extra),
                )
        for meta in ("doctor_name", "clinic", "patient_name", "date"):
            if not extracted.get(meta) and combined.get(meta):
                extracted[meta] = combined[meta]
        return extracted

    # ── Per-module processing ────────────────────────────────────────────────

    def _process_medications_module(
        self,
        patient_id: str,
        extracted: Dict[str, Any],
        content_hash: str,
        image_url: str,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        overwrite = bool(options.get("overwrite", False) or options.get("forceSave", False))
        auto_schedule = bool(options.get("autoSchedule", False))

        orphan = None
        try:
            orphan = self._prescriptions._resolve_duplicate_or_orphan(patient_id, content_hash)
        except PrescriptionAlreadyExistsError as exc:
            if not overwrite:
                raise ClinicalScanAlreadyExistsError(
                    "Prescription is already added.",
                    existing_scan_id=exc.existing_prescription_id,
                )

        payload = {
            "imageUrl": image_url or "smart_scan://document",
            "scannedAt": int(time.time() * 1000),
            "prescriberName": extracted.get("doctor_name") or options.get("providerName"),
            "contentHash": content_hash,
        }
        if extracted:
            payload = self._prescriptions._mapper.enrich_prescription_payload(payload, extracted)
        elif options.get("documentDate"):
            payload["prescriptionDate"] = normalize_prescription_date(options.get("documentDate"))

        prescription = self._prescriptions._persist_prescription_row(patient_id, payload, orphan)
        created_meds = self._prescriptions._persist_medications(
            patient_id, prescription["id"], extracted, auto_schedule
        )

        return {
            "targetTable": "medication_prescriptions",
            "scanId": prescription["id"],
            "prescription": prescription_response(dict(prescription)),
            "recordsCreated": created_meds,
            "skipped": False,
            "status": "created" if not orphan else "updated",
        }

    def _process_module(
        self,
        patient_id: str,
        module_name: str,
        extracted: Dict[str, Any],
        content_hash: str,
        image_url: str,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            module = ClinicalModule.from_value(module_name)
        except ValueError:
            return {"skipped": True, "reason": f"Unknown module: {module_name}"}

        if module == ClinicalModule.MEDICATIONS:
            return self._process_medications_module(
                patient_id, extracted, content_hash, image_url, options
            )

        strategy = self._strategies.get(module)
        if not strategy:
            return {"skipped": True, "reason": f"No strategy registered for: {module_name}"}

        doc_date = extracted.get("date")
        overwrite = bool(options.get("overwrite", False) or options.get("forceSave", False))

        # Unique key includes soft-deleted rows — look those up too.
        existing = get_clinical_scan_by_hash(
            patient_id, module.value, content_hash, include_deleted=True
        )
        existing_semantic = (
            find_existing_scan_by_semantic_data(patient_id, module.value, doc_date)
            if doc_date
            else None
        )
        target_scan = existing or existing_semantic
        target_deleted = bool(target_scan) and int(target_scan.get("is_deleted") or 0) == 1

        payload = strategy.enrich_scan_payload(
            {
                "imageUrl":     image_url,
                "contentHash":  content_hash,
                "documentType": f"{module.value}_document",
                "providerName": extracted.get("doctor_name"),
                "documentDate": doc_date,
            },
            extracted,
        )

        mapped_records = strategy.map_records(extracted)

        logger.info(
            "SMART_SCAN module process patient_id=%s module=%s overwrite=%s "
            "has_existing=%s deleted=%s records=%s",
            patient_id,
            module.value,
            overwrite,
            bool(target_scan),
            target_deleted,
            len(mapped_records),
        )

        # Revive a soft-deleted hash row, or upsert when forceSave/overwrite.
        if target_scan and (overwrite or target_deleted):
            target_scan_id = target_scan["id"]
            update_clinical_scan(target_scan_id, payload)

            updated_records: List[Dict[str, Any]] = []
            created_records: List[Dict[str, Any]] = []
            for record_payload in mapped_records:
                rec, status_action = strategy.upsert_record(patient_id, record_payload)
                if status_action == "updated":
                    updated_records.append(rec)
                else:
                    created_records.append(rec)

            return {
                "targetTable":    module.target_table,
                "scanId":         target_scan_id,
                "recordsCreated": created_records,
                "recordsUpdated": updated_records,
                "skipped":        False,
                "status":         "updated",
            }

        # Duplicate Blocking Mode (overwrite=false)
        if target_scan and not overwrite:
            scan_id = target_scan.get("id") or target_scan.get("scanId") or 0
            raise ClinicalScanAlreadyExistsError(
                f"A {module.value} document dated '{doc_date or 'unknown'}' has already been scanned for this patient.",
                existing_scan_id=scan_id,
            )

        # Fresh Scan Save — Persist individual clinical records into target table first
        created: List[Dict[str, Any]] = []
        skipped_record_ids: List[str] = []

        for record_payload in mapped_records:
            try:
                row = strategy.persist_record(patient_id, record_payload)
                created.append(row)
            except RecordAlreadyExistsError as exc:
                if exc.existing_record_id:
                    skipped_record_ids.append(exc.existing_record_id)
                logger.info(
                    "Duplicate %s record skipped for patient=%s existing=%s",
                    module.value, patient_id, exc.existing_record_id,
                )

        if mapped_records and not created and skipped_record_ids and not overwrite:
            raise RecordAlreadyExistsError(
                f"All extracted {module.value} records already exist for this patient.",
                existing_record_id=skipped_record_ids[0],
            )

        # Only create clinical scan history metadata row if records were saved or if no records to map
        try:
            scan = create_clinical_scan(patient_id, module.value, payload)
        except ScanHashConflictError as exc:
            if exc.existing and int(exc.existing.get("is_deleted") or 0) == 1:
                scan = update_clinical_scan(exc.existing_scan_id, payload)
                return {
                    "targetTable":    module.target_table,
                    "scanId":         exc.existing_scan_id,
                    "recordsCreated": created,
                    "skipped":        False,
                    "status":         "revived",
                }
            raise ClinicalScanAlreadyExistsError(
                f"A {module.value} document dated '{doc_date or 'unknown'}' "
                "has already been scanned for this patient.",
                existing_scan_id=exc.existing_scan_id,
            ) from exc

        return {
            "targetTable":    module.target_table,
            "scanId":         scan["id"],
            "recordsCreated": created,
            "skipped":        False,
        }
