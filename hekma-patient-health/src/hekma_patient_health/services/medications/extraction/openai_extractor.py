import base64
import json
import os
from typing import Any, Dict, Optional, Tuple

import requests

from ..exceptions import (
    ExtractionAuthError,
    ExtractionConfigurationError,
    ExtractionRateLimitError,
    ExtractionServiceError,
    InvalidPrescriptionError,
)
from ...ai_common.openai_errors import classify_openai_http_error, scan_auth_user_message
from ...ai_common.usage_emitter import emit_llm_usage
from ....utils.prescription_dates import apply_display_date
from ....utils.prescription_timing import (
    TIMING_PROMPT,
    TIMING_SCHEMA,
    apply_medicine_reminders,
)
from .mime_resolver import SUPPORTED_MIME_TYPES, guess_mime_type_from_url


_SYSTEM_PROMPT = """You are a medical prescription extraction specialist.
You inspect scanned, photographed, or PDF prescription documents and return
only machine-readable JSON. Extract only data that is clearly visible.
Do not guess, infer, or hallucinate any data.

For handwritten prescriptions, transcribe legible text and mark uncertain fields
as "uncertain". Preserve original spellings.

If the document is not a prescription, set error to "not_a_prescription"."""

_USER_PROMPT = """Analyze this prescription document and extract all visible fields.

Use standardized frequencies where possible:
- Once Daily
- Twice Daily
- Three Times Daily
- Four Times Daily
- Every other day
- Once Weekly
- Once Monthly
- As Needed (PRN)

Only report a frequency the prescription actually states. If it states none,
return an empty frequency rather than assuming a daily dose.

""" + TIMING_PROMPT + """

If any field is unreadable, return "uncertain"."""

_JSON_SCHEMA = {
    "name": "prescription_extraction",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "error": {"type": ["string", "null"]},
            "doctor_name": {"type": "string"},
            "clinic": {"type": "string"},
            "patient_name": {"type": "string"},
            "date": {"type": "string"},
            "medicines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "strength": {"type": "string"},
                        "dosage": {"type": "string"},
                        "frequency": {"type": "string"},
                        "duration": {"type": "string"},
                        "instructions": {"type": "string"},
                        "timing": TIMING_SCHEMA,
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "name", "strength", "dosage", "frequency",
                        "duration", "instructions", "timing", "confidence",
                    ],
                },
            },
            "notes": {"type": "string"},
            "overall_confidence": {"type": "number"},
        },
        "required": [
            "error", "doctor_name", "clinic", "patient_name", "date",
            "medicines", "notes", "overall_confidence",
        ],
    },
    "strict": True,
}


class OpenAIPrescriptionExtractor:
    """OpenAI Vision implementation of PrescriptionExtractor."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self._api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        self._model = (model or os.getenv("OPENAI_MODEL", "gpt-4o")).strip() or "gpt-4o"
        self._usage_patient_id: Optional[str] = None
        self._usage_product: str = "scan_ai"

    def bind_usage(self, *, patient_id: str, product: str = "scan_ai") -> None:
        self._usage_patient_id = str(patient_id)
        self._usage_product = product

    def extract_from_url(self, source_url: str) -> Dict[str, Any]:
        from ....utils.url_safety import assert_safe_download_url

        assert_safe_download_url(source_url)
        response = requests.get(source_url, timeout=30)
        response.raise_for_status()
        mime_type = guess_mime_type_from_url(source_url, response.headers.get("Content-Type"))
        self._validate_mime_type(mime_type)
        return self.extract_from_bytes(response.content, mime_type)

    def extract_from_bytes(self, content: bytes, mime_type: str) -> Dict[str, Any]:
        self._validate_mime_type(mime_type)
        encoded_data, inline_mime = self._prepare_inline_data(content, mime_type)
        extracted = self._call_vision(encoded_data, inline_mime)
        if extracted.get("error") == "not_a_prescription":
            raise InvalidPrescriptionError("The file does not appear to be a valid prescription")
        extracted.pop("error", None)
        return extracted

    def _validate_mime_type(self, mime_type: str) -> None:
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise InvalidPrescriptionError("Only JPEG, PNG, WEBP, and PDF are supported for extraction")

    def _prepare_inline_data(self, content: bytes, mime_type: str) -> Tuple[str, str]:
        if mime_type == "application/pdf":
            return self._render_pdf_first_page(content)
        return base64.b64encode(content).decode("utf-8"), mime_type

    @staticmethod
    def _render_pdf_first_page(content: bytes) -> Tuple[str, str]:
        try:
            import fitz
        except ImportError as exc:
            raise InvalidPrescriptionError(
                "PyMuPDF is required for PDF extraction. Install with: pip install PyMuPDF"
            ) from exc

        doc = fitz.open(stream=content, filetype="pdf")
        if doc.page_count == 0:
            raise InvalidPrescriptionError("PDF has no pages")

        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=180)
        encoded = base64.b64encode(pix.tobytes("png")).decode("utf-8")
        return encoded, "image/png"

    def _call_vision(self, encoded_data: str, mime_type: str) -> Dict[str, Any]:
        if not self._api_key:
            raise ExtractionAuthError(
                scan_auth_user_message("Prescription scanning"),
                reason_code="auth_failed",
            )

        image_url = f"data:{mime_type};base64,{encoded_data}"
        payload = {
            "model": self._model,
            "temperature": 0,
            "max_tokens": 4096,
            "response_format": {"type": "json_schema", "json_schema": _JSON_SCHEMA},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _USER_PROMPT},
                        {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}},
                    ],
                },
            ],
        }

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=90,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            classified = classify_openai_http_error(exc, feature="Prescription scanning")
            if classified["kind"] == "rate_limit":
                raise ExtractionRateLimitError(classified["message"]) from exc
            if classified["kind"] == "auth":
                raise ExtractionAuthError(
                    classified["message"],
                    reason_code=classified.get("reason_code"),
                ) from exc
            raise ExtractionServiceError(
                "We could not process this prescription right now. "
                "Please try again or enter medicines manually."
            ) from exc
        except requests.RequestException as exc:
            raise ExtractionServiceError(
                "Could not reach the prescription scanning service. "
                "Check your connection and try again."
            ) from exc

        body = response.json()
        emit_llm_usage(
            patient_id=self._usage_patient_id,
            product=self._usage_product,
            feature="prescription_scan",
            provider="openai",
            model=self._model,
            usage=body.get("usage") or {},
            source_service="hekma-core",
        )
        choices = body.get("choices") or []
        if not choices:
            raise InvalidPrescriptionError("Empty response from OpenAI")

        text = (choices[0].get("message") or {}).get("content")
        if not text:
            raise InvalidPrescriptionError("No text in OpenAI response")

        cleaned = text.replace("```json", "").replace("```", "").strip()
        return apply_display_date(apply_medicine_reminders(json.loads(cleaned)))
