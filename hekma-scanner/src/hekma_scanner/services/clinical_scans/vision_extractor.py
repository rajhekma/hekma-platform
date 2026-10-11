import base64
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from .exceptions import (
    ExtractionAuthError,
    ExtractionConfigurationError,
    ExtractionRateLimitError,
    ExtractionServiceError,
    InvalidClinicalDocumentError,
    PdfPageLimitExceededError,
)
from ..ai_common.openai_errors import classify_openai_http_error, scan_auth_user_message
from ..ai_common.usage_emitter import emit_llm_usage
from ..medications.extraction.mime_resolver import SUPPORTED_MIME_TYPES, guess_mime_type_from_url
from ...config.clinical_scan_config import get_clinical_scan_config
from ...utils.prescription_dates import apply_display_date
from ...utils.prescription_timing import apply_medicine_reminders


# ── Combined schema for universal extraction (all 6 modules in 1 OpenAI call) ──
# Non-strict mode (no "strict": true) to avoid schema rejection due to complexity.
# Server-side cross-validation derives detected modules from non-empty arrays.
_COMBINED_SCHEMA: Dict[str, Any] = {
    "name": "universal_clinical_extraction",
    "schema": {
        "type": "object",
        "properties": {
            "doctor_name":  {"type": "string"},
            "clinic":       {"type": "string"},
            "patient_name": {"type": "string"},
            "date":         {"type": "string"},
            "lab_results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "testName":       {"type": "string"},
                        "testCode":       {"type": "string"},
                        "category":       {"type": "string"},
                        "testValue":      {"type": "string"},
                        "unit":           {"type": "string"},
                        "referenceRange": {"type": "string"},
                        "interpretation": {"type": "string"},
                        "specimen":       {"type": "string"},
                        "performer":      {"type": "string"},
                        "resultDate":     {"type": "string"},
                        "notes":          {"type": "string"},
                    },
                },
            },
            "vitals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type":              {"type": "string"},
                        "refValue1":         {"type": "string"},
                        "refValue2":         {"type": "string"},
                        "metric":            {"type": "string"},
                        "interpretation":    {"type": "string"},
                        "bodySite":          {"type": "string"},
                        "patientPosition":   {"type": "string"},
                        "dateOfObservation": {"type": "string"},
                        "notes":             {"type": "string"},
                    },
                },
            },
            "immunizations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "vaccineName":     {"type": "string"},
                        "vaccineCode":     {"type": "string"},
                        "vaccinationDate": {"type": "string"},
                        "doseQuantity":    {"type": "string"},
                        "lotNumber":       {"type": "string"},
                        "manufacturer":    {"type": "string"},
                        "expirationDate":  {"type": "string"},
                        "site":            {"type": "string"},
                        "route":           {"type": "string"},
                        "performer":       {"type": "string"},
                        "notes":           {"type": "string"},
                    },
                },
            },
            "procedures": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "procedureName": {"type": "string"},
                        "code":          {"type": "string"},
                        "category":      {"type": "string"},
                        "status":        {"type": "string"},
                        "bodySite":      {"type": "string"},
                        "performer":     {"type": "string"},
                        "facility":      {"type": "string"},
                        "startDate":     {"type": "string"},
                        "endDate":       {"type": "string"},
                        "reason":        {"type": "string"},
                        "outcome":       {"type": "string"},
                        "complication":  {"type": "string"},
                        "followUp":      {"type": "string"},
                        "notes":         {"type": "string"},
                    },
                },
            },
            "conditions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "conditionName":      {"type": "string"},
                        "code":               {"type": "string"},
                        "clinicalStatus":     {"type": "string"},
                        "verificationStatus": {"type": "string"},
                        "category":           {"type": "string"},
                        "severity":           {"type": "string"},
                        "bodySite":           {"type": "string"},
                        "startDate":          {"type": "string"},
                        "endDate":            {"type": "string"},
                        "recordedBy":         {"type": "string"},
                        "notes":              {"type": "string"},
                    },
                },
            },
            "allergies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "substance":          {"type": "string"},
                        "criticality":        {"type": "string"},
                        "category":           {"type": "string"},
                        "severity":           {"type": "string"},
                        "verificationStatus": {"type": "string"},
                        "reaction":           {"type": "string"},
                        "onsetDate":          {"type": "string"},
                        "lastOccurrence":     {"type": "string"},
                        "notes":              {"type": "string"},
                    },
                },
            },
        },
    },
}

_ITEM_ARRAY_KEYS = (
    "allergies",
    "vitals",
    "lab_results",
    "immunizations",
    "procedures",
    "conditions",
    "medicines",
    "medications",
)

_COMBINED_SYSTEM_PROMPT = (
    "You are an expert clinical documentation analyst specializing in FHIR R4 medical record extraction. "
    "Analyze the provided medical document (discharge summary, lab report, surgical report, chart, "
    "OPD/consultation sheet, or clinical note) and extract ALL present clinical data elements with extreme precision.\n\n"
    "Extraction Guidelines:\n"
    "1. High Clinical Fidelity: Extract exact medical terminology, LOINC/ICD-10/CPT codes if printed, exact test values, units, reference ranges, body sites, performing doctors, and facilities.\n"
    "2. Standardized Dates: Format all dates as YYYY-MM-DD whenever discernible.\n"
    "3. No Hallucination: Extract only explicit data present in the document. For missing or unmentioned attributes, return empty strings \"\" or nulls. If a section is absent, return an empty array [].\n"
    "4. Abbreviations: Expand standard medical abbreviations when unambiguous (e.g. 's/p' -> status post, 'c/o' -> complains of), otherwise preserve exact printed text.\n"
    "5. Mixed documents: A single sheet often has several labeled sections. Extract every section that is present — "
    "do not skip vitals, allergies, or procedures because labs/diagnosis/immunization are also on the page.\n"
    "6. No hallucination: extract only printed text. Do not invent ICD/CPT/LOINC codes or values. "
    "Do not infer diagnoses from BMI, BP, or labs unless written. Do not copy C/o complaints into conditions. "
    "Do not copy Rx drug names into procedures/labs/immunizations. NKDA/Nil/None means allergies=[]. "
    "Do not copy procedure findings (ECG interpretation, imaging/endoscopy notes) into conditions unless listed under Diagnosis."
)

_COMBINED_USER_PROMPT = (
    "Extract all clinical data matching FHIR R4 domain models. Mixed OPD sheets may include all of these:\n"
    "- Procedures / investigations table: ECG, X-ray, ultrasound, CT/MRI, endoscopy, biopsy, swabs. "
    "Fields: procedureName, code (CPT/SNOMED), category, status, bodySite, performer, facility, startDate, endDate, reason, outcome, complication, followUp, notes. "
    "Put findings such as Normal or Culture: Negative in outcome/notes. Do not put these rows in lab_results.\n"
    "- Lab Reports (blood/urine chemistry/hematology tables): testName, testCode (LOINC), category, testValue, unit, referenceRange, interpretation (HIGH/LOW/NORMAL/CRITICAL), specimen, performer, resultDate, notes.\n"
    "- Vital Signs from a table or labeled list (BP, Pulse, Temperature, RR, SpO2, Height, Weight, BMI): "
    "type, refValue1 (systolic/value), refValue2 (diastolic), metric (unit), interpretation, bodySite, patientPosition, dateOfObservation, notes.\n"
    "- Immunizations: vaccineName, vaccineCode (CVX/NDC), vaccinationDate, doseQuantity, lotNumber, manufacturer, expirationDate, site, route, performer, notes.\n"
    "- Medical Conditions / Diagnoses: conditionName, code (ICD-10/SNOMED), clinicalStatus, verificationStatus, category, severity, bodySite, startDate, endDate, recordedBy, notes.\n"
    "- Allergies & Intolerances from Allergen/Reaction tables: substance, criticality (high/low/unable-to-assess), category (food/medication/environment/biologic), severity, verificationStatus, reaction, onsetDate, lastOccurrence, notes.\n"
    "- Document Metadata: doctor_name, clinic, patient_name, date."
)


def items_key_from_profile(profile: Dict[str, Any]) -> Optional[str]:
    """Return the clinical items array key declared on a focused extraction profile."""
    schema = profile.get("json_schema") or {}
    props = (schema.get("schema") or {}).get("properties") or {}
    for key in _ITEM_ARRAY_KEYS:
        if key in props:
            return key
    return None


class OpenAIClinicalVisionExtractor:
    """Shared OpenAI Vision client; module-specific prompts/schemas injected per call."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self._api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        self._model = (model or os.getenv("OPENAI_MODEL", "gpt-4o")).strip() or "gpt-4o"
        self._usage_patient_id: Optional[str] = None
        self._usage_product: str = "scan_ai"

    def bind_usage(self, *, patient_id: str, product: str = "scan_ai") -> None:
        self._usage_patient_id = str(patient_id)
        self._usage_product = product

    def extract_from_bytes(
        self,
        content: bytes,
        mime_type: str,
        profile: Dict[str, Any],
        feature: str = "smart_scan",
    ) -> Dict[str, Any]:
        """
        Run one focused Vision call. A module mismatch error no longer aborts:
        keep rows if present, otherwise return an empty items array.
        """
        self._validate_mime_type(mime_type)
        images = self._prepare_images(content, mime_type)
        extracted = self._call_vision(images, profile, feature=feature)
        invalid_code = profile.get("invalid_error_code") or "not_a_clinical_document"
        items_key = items_key_from_profile(profile)
        items = extracted.get(items_key) if items_key else None
        if extracted.get("error") == invalid_code:
            # Mixed OPD sheets often trip the module mismatch flag even when the
            # section is present (or simply absent). Keep any extracted rows;
            # otherwise treat as "this module not on the page", not a hard reject.
            extracted.pop("error", None)
            if items:
                return extracted
            if items_key:
                extracted[items_key] = []
            return extracted
        extracted.pop("error", None)
        return extracted

    def extract_from_url(self, source_url: str, profile: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.get(source_url, timeout=30)
        response.raise_for_status()
        mime_type = guess_mime_type_from_url(source_url, response.headers.get("Content-Type"))
        return self.extract_from_bytes(response.content, mime_type, profile)

    def extract_all_modules(self, content: bytes, mime_type: str) -> Dict[str, Any]:
        """
        Single OpenAI Vision call — detects AND extracts all 6 module types.
        Uses the combined non-strict schema. Server-side code derives which modules
        were actually found by checking for non-empty arrays in the response.
        """
        self._validate_mime_type(mime_type)
        images = self._prepare_images(content, mime_type)
        profile = {
            "system_prompt": _COMBINED_SYSTEM_PROMPT,
            "user_prompt":   _COMBINED_USER_PROMPT,
            "json_schema":   _COMBINED_SCHEMA,
        }
        result = self._call_vision(images, profile, feature="smart_scan.gap_fill")
        # Ensure all array keys exist with defaults (guard against partial responses)
        for key in ("lab_results", "vitals", "immunizations", "procedures", "conditions", "allergies"):
            if key not in result:
                result[key] = []
        return result

    def _validate_mime_type(self, mime_type: str) -> None:
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise InvalidClinicalDocumentError("Only JPEG, PNG, WEBP, and PDF are supported")

    def _prepare_images(self, content: bytes, mime_type: str) -> List[Tuple[str, str]]:
        """Return [(base64, mime), ...] for Vision — PDFs may include multiple pages."""
        if mime_type == "application/pdf":
            return self._render_pdf_pages(content)
        return [(base64.b64encode(content).decode("utf-8"), mime_type)]

    @staticmethod
    def _render_pdf_pages(content: bytes) -> List[Tuple[str, str]]:
        """
        Rasterize each PDF page for Vision, up to configured maxPdfPages.

        Raises PdfPageLimitExceededError when the PDF has more pages than allowed.
        """
        try:
            import fitz
        except ImportError as exc:
            raise InvalidClinicalDocumentError(
                "PyMuPDF is required for PDF extraction. Install with: pip install PyMuPDF"
            ) from exc

        max_pages = get_clinical_scan_config().max_pdf_pages
        doc = fitz.open(stream=content, filetype="pdf")
        try:
            if doc.page_count == 0:
                raise InvalidClinicalDocumentError("PDF has no pages")
            if doc.page_count > max_pages:
                raise PdfPageLimitExceededError(
                    f"PDF document exceeds maximum limit of {max_pages} pages "
                    f"(found {doc.page_count} pages). "
                    f"Only documents with up to {max_pages} pages are allowed."
                )
            images: List[Tuple[str, str]] = []
            for index in range(doc.page_count):
                page = doc.load_page(index)
                pix = page.get_pixmap(dpi=160)
                images.append(
                    (base64.b64encode(pix.tobytes("png")).decode("utf-8"), "image/png")
                )
            return images
        finally:
            doc.close()

    def _emit_usage(self, usage: Any, feature: str) -> None:
        emit_llm_usage(
            patient_id=self._usage_patient_id,
            product=self._usage_product,
            feature=feature,
            provider="openai",
            model=self._model,
            usage=usage,
            source_service="hekma-core",
        )

    def _call_vision(
        self,
        images: List[Tuple[str, str]],
        profile: Dict[str, Any],
        feature: str = "smart_scan",
    ) -> Dict[str, Any]:
        if not self._api_key:
            raise ExtractionAuthError(
                scan_auth_user_message("Document scanning"),
                reason_code="auth_failed",
            )
        if not images:
            raise InvalidClinicalDocumentError("No page images available for extraction")

        user_content: List[Dict[str, Any]] = [
            {"type": "text", "text": profile["user_prompt"]},
        ]
        for encoded_data, mime_type in images:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{encoded_data}",
                        "detail": "high",
                    },
                }
            )

        payload = {
            "model": self._model,
            "temperature": 0,
            "max_tokens": 4096,
            "response_format": {
                "type": "json_schema",
                "json_schema": profile["json_schema"],
            },
            "messages": [
                {"role": "system", "content": profile["system_prompt"]},
                {"role": "user", "content": user_content},
            ],
        }
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=90,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            classified = classify_openai_http_error(exc, feature="Document scanning")
            if classified["kind"] == "rate_limit":
                raise ExtractionRateLimitError(classified["message"]) from exc
            if classified["kind"] == "auth":
                raise ExtractionAuthError(
                    classified["message"],
                    reason_code=classified.get("reason_code"),
                ) from exc
            raise ExtractionServiceError(classified["message"]) from exc
        except requests.RequestException as exc:
            raise ExtractionServiceError("Could not reach the clinical document scanning service.") from exc

        body = response.json()
        self._emit_usage(body.get("usage") or {}, feature)
        choices = body.get("choices") or []
        if not choices:
            raise InvalidClinicalDocumentError("Empty response from OpenAI")
        text = (choices[0].get("message") or {}).get("content")
        if not text:
            raise InvalidClinicalDocumentError("No text in OpenAI response")
        cleaned = text.replace("```json", "").replace("```", "").strip()
        return apply_display_date(apply_medicine_reminders(json.loads(cleaned)))
