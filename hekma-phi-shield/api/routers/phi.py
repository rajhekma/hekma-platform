"""PHI detection HTTP API (OpenAI-backed today, swappable later)."""

from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field, field_validator, ConfigDict

from api.services.phi.service import PhiDetectionService
from api.openapi_examples import (
    PHI_PREDICT_REQUEST_EXAMPLES,
    PHI_PREDICT_RESPONSE_EXAMPLES,
    PHI_ANONYMIZE_REQUEST_EXAMPLES,
    PHI_ANONYMIZE_RESPONSE_EXAMPLES,
    PHI_HEALTH_RESPONSE_EXAMPLES,
    PHI_ENTITIES_RESPONSE_EXAMPLES,
    PHI_VALIDATE_REQUEST_EXAMPLES,
    PHI_VALIDATE_RESPONSE_EXAMPLES,
    PHI_MASK_REQUEST_EXAMPLES,
    PHI_MASK_RESPONSE_EXAMPLES,
    PHI_BATCH_PREDICT_REQUEST_EXAMPLES,
    PHI_BATCH_PREDICT_RESPONSE_EXAMPLES,
    ERROR_422_UNPROCESSABLE,
)

MAX_TEXT_LENGTH = 10_000

phi_router = APIRouter(prefix="/phi", tags=["3. Clinical PHI Detection (OpenAI / Local)"])


class TextValidationMixin:
    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty or whitespace-only")
        return v


class PhiEntity(BaseModel):
    entity: str
    text: str
    start: int
    end: int
    confidence: float
    category: Literal["phi"] = "phi"
    label: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "entity": "PATIENT_NAME",
                "text": "Elijah Fisher",
                "start": 8,
                "end": 21,
                "confidence": 0.985,
                "category": "phi",
                "label": "Patient Name",
            }
        }
    )


class PhiPredictRequest(BaseModel, TextValidationMixin):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": PHI_PREDICT_REQUEST_EXAMPLES["standard_clinical_progress_note"]["value"]
        }
    )


class PhiPredictResponse(BaseModel):
    text: str
    entities: List[PhiEntity]
    entity_count: int
    contains_phi: bool
    backend: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": PHI_PREDICT_RESPONSE_EXAMPLES["phi_detected_response"]["value"]
        }
    )


class PhiValidateRequest(BaseModel, TextValidationMixin):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    entity_types: Optional[List[str]] = None
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": PHI_VALIDATE_REQUEST_EXAMPLES["standard_phi_validate"]["value"]
        }
    )


class PhiValidateResponse(BaseModel):
    contains_phi: bool
    entity_types_found: List[str]
    entity_count: int
    entities: List[PhiEntity]
    backend: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": PHI_VALIDATE_RESPONSE_EXAMPLES["phi_found"]["value"]
        }
    )


class PhiMaskRequest(BaseModel, TextValidationMixin):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    mask_style: Literal["type", "asterisk", "placeholder", "ignore"] = "type"
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": PHI_MASK_REQUEST_EXAMPLES["standard_phi_mask"]["value"]
        }
    )


class PhiMaskResponse(BaseModel):
    original_text: str
    masked_text: str
    entities_masked: int
    entities: List[PhiEntity]
    backend: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": PHI_MASK_RESPONSE_EXAMPLES["phi_masked"]["value"]
        }
    )


class PhiBatchPredictRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1, max_length=50)
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)

    @field_validator("texts")
    @classmethod
    def texts_must_be_valid(cls, v: List[str]) -> List[str]:
        for item in v:
            if not item or not item.strip():
                raise ValueError("texts must not contain empty or whitespace-only strings")
            if len(item) > MAX_TEXT_LENGTH:
                raise ValueError(f"each text must be at most {MAX_TEXT_LENGTH} characters")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": PHI_BATCH_PREDICT_REQUEST_EXAMPLES["batch_progress_notes"]["value"]
        }
    )


class PhiBatchPredictResponse(BaseModel):
    results: List[PhiPredictResponse]
    backend: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": PHI_BATCH_PREDICT_RESPONSE_EXAMPLES["batch_results"]["value"]
        }
    )


class PhiAnonymizeRequest(BaseModel, TextValidationMixin):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)
    mask_style: Literal["type", "asterisk", "placeholder"] = "type"

    model_config = ConfigDict(
        json_schema_extra={
            "example": PHI_ANONYMIZE_REQUEST_EXAMPLES["standard_phi_anonymize"]["value"]
        }
    )


class PhiAnonymizeMapping(BaseModel):
    entity_type: str
    label: str
    original_value: str
    tokenized_value: str
    policy_applied: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "entity_type": "PATIENT_NAME",
                "label": "Patient Name",
                "original_value": "Elijah Fisher",
                "tokenized_value": "[PATIENT_NAME]",
                "policy_applied": "mask",
            }
        }
    )


class PhiAnonymizeResponse(BaseModel):
    anonymized_text: str
    mappings: List[PhiAnonymizeMapping]
    entity_count: int
    backend: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": PHI_ANONYMIZE_RESPONSE_EXAMPLES["phi_anonymized_response"]["value"]
        }
    )


class PhiEntityTypeInfo(BaseModel):
    entity: str
    label: str
    description: str
    category: Literal["phi"] = "phi"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "entity": "PATIENT_NAME",
                "label": "Patient Name",
                "description": "Patient full, first, or last name",
                "category": "phi",
            }
        }
    )


class PhiEntityTypesResponse(BaseModel):
    entity_types: List[PhiEntityTypeInfo]
    count: int
    backend: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": PHI_ENTITIES_RESPONSE_EXAMPLES["phi_types"]["value"]
        }
    )


class PhiHealthResponse(BaseModel):
    status: str
    phi_ready: bool
    backend: str
    model: Optional[str] = None
    detail: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": PHI_HEALTH_RESPONSE_EXAMPLES["phi_ready"]["value"]
        }
    )


def _service() -> PhiDetectionService:
    """Late-bind to the singleton wired in api.main (avoids circular import)."""
    from api.main import phi_service

    return phi_service


def _ensure_ready(service: PhiDetectionService) -> None:
    """Fail with 503 when the configured PHI backend cannot serve."""
    status = service.status()
    if not status.ready:
        raise HTTPException(
            status_code=503,
            detail=status.detail or "PHI detector is not available",
        )


@phi_router.get(
    "/health",
    response_model=PhiHealthResponse,
    responses={
        200: {
            "description": "PHI Backend Readiness",
            "content": {
                "application/json": {
                    "examples": PHI_HEALTH_RESPONSE_EXAMPLES
                }
            }
        }
    }
)
async def phi_health():
    """PHI backend readiness (independent of the RoBERTa PII model)."""
    service = _service()
    status = service.status()
    return PhiHealthResponse(
        status="ok" if status.ready else "degraded",
        phi_ready=status.ready,
        backend=status.backend,
        model=status.model,
        detail=status.detail,
    )


@phi_router.get(
    "/entities",
    response_model=PhiEntityTypesResponse,
    responses={
        200: {
            "description": "Supported Clinical PHI Labels",
            "content": {
                "application/json": {
                    "examples": PHI_ENTITIES_RESPONSE_EXAMPLES
                }
            }
        }
    }
)
async def phi_entities():
    """List supported PHI labels with human-readable names."""
    service = _service()
    types = service.list_entity_types()
    return PhiEntityTypesResponse(
        entity_types=types,
        count=len(types),
        backend=service.status().backend,
    )


@phi_router.post(
    "/predict",
    response_model=PhiPredictResponse,
    responses={
        200: {
            "description": "Clinical PHI Spans Detected",
            "content": {
                "application/json": {
                    "examples": PHI_PREDICT_RESPONSE_EXAMPLES
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def phi_predict(
    payload: PhiPredictRequest = Body(
        ...,
        openapi_examples=PHI_PREDICT_REQUEST_EXAMPLES
    )
):
    """Detect PHI spans via the configured detector (OpenAI by default)."""
    service = _service()
    _ensure_ready(service)
    try:
        entities = await service.predict(payload.text, payload.min_confidence)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface provider failures cleanly
        raise HTTPException(status_code=502, detail=f"PHI detection failed: {exc}") from exc
    return PhiPredictResponse(
        text=payload.text,
        entities=entities,
        entity_count=len(entities),
        contains_phi=len(entities) > 0,
        backend=service.status().backend,
    )


@phi_router.post(
    "/validate",
    response_model=PhiValidateResponse,
    responses={
        200: {
            "description": "Validation Complete (PHI Check)",
            "content": {
                "application/json": {
                    "examples": PHI_VALIDATE_RESPONSE_EXAMPLES
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def phi_validate(
    payload: PhiValidateRequest = Body(
        ...,
        openapi_examples=PHI_VALIDATE_REQUEST_EXAMPLES
    )
):
    """Compliance check: does text contain PHI (optionally filtered by type)?"""
    service = _service()
    _ensure_ready(service)
    try:
        entities = await service.validate(
            payload.text,
            entity_types=payload.entity_types,
            min_confidence=payload.min_confidence,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"PHI validation failed: {exc}") from exc
    types_found = sorted({e["entity"] for e in entities})
    return PhiValidateResponse(
        contains_phi=len(entities) > 0,
        entity_types_found=types_found,
        entity_count=len(entities),
        entities=entities,
        backend=service.status().backend,
    )


@phi_router.post(
    "/mask",
    response_model=PhiMaskResponse,
    responses={
        200: {
            "description": "Clinical Narrative Masked",
            "content": {
                "application/json": {
                    "examples": PHI_MASK_RESPONSE_EXAMPLES
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def phi_mask(
    payload: PhiMaskRequest = Body(
        ...,
        openapi_examples=PHI_MASK_REQUEST_EXAMPLES
    )
):
    """Detect and redact PHI spans."""
    service = _service()
    _ensure_ready(service)
    try:
        entities = await service.predict(payload.text, payload.min_confidence)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"PHI masking failed: {exc}") from exc
    masked = service.mask(payload.text, entities, style=payload.mask_style)
    return PhiMaskResponse(
        original_text=payload.text,
        masked_text=masked,
        entities_masked=len(entities),
        entities=entities,
        backend=service.status().backend,
    )


@phi_router.post(
    "/predict/batch",
    response_model=PhiBatchPredictResponse,
    responses={
        200: {
            "description": "Batch PHI Predictions Complete",
            "content": {
                "application/json": {
                    "examples": PHI_BATCH_PREDICT_RESPONSE_EXAMPLES
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def phi_predict_batch(
    payload: PhiBatchPredictRequest = Body(
        ...,
        openapi_examples=PHI_BATCH_PREDICT_REQUEST_EXAMPLES
    )
):
    """Batch PHI detection — one result per input text."""
    service = _service()
    _ensure_ready(service)
    try:
        batch = await service.predict_batch(payload.texts, payload.min_confidence)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"PHI batch detection failed: {exc}") from exc
    results = [
        PhiPredictResponse(
            text=item["text"],
            entities=item["entities"],
            entity_count=item["entity_count"],
            contains_phi=item["contains_phi"],
            backend=service.status().backend,
        )
        for item in batch
    ]
    return PhiBatchPredictResponse(results=results, backend=service.status().backend)


@phi_router.post(
    "/anonymize",
    response_model=PhiAnonymizeResponse,
    responses={
        200: {
            "description": "Clinical Narrative Anonymized with PHI Mappings",
            "content": {
                "application/json": {
                    "examples": PHI_ANONYMIZE_RESPONSE_EXAMPLES
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def phi_anonymize(
    payload: PhiAnonymizeRequest = Body(
        ...,
        openapi_examples=PHI_ANONYMIZE_REQUEST_EXAMPLES
    )
):
    """Detect PHI and return anonymized text with entity mappings."""
    service = _service()
    _ensure_ready(service)
    try:
        anonymized, mappings = await service.anonymize(
            payload.text,
            min_confidence=payload.min_confidence,
            mask_style=payload.mask_style,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"PHI anonymization failed: {exc}") from exc
    return PhiAnonymizeResponse(
        anonymized_text=anonymized,
        mappings=mappings,
        entity_count=len(mappings),
        backend=service.status().backend,
    )
