import contextlib
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Literal, Optional

import torch
import uvicorn
from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field, field_validator, ConfigDict
from transformers import AutoModelForTokenClassification, AutoTokenizer

from api.config.settings import settings
from api.middleware.anonymization_middleware import AnonymizationMiddleware
from api.middleware.entity_detector import entity_detector
from api.middleware.policy_engine import PolicyContext, policy_engine
from api.models.token_mapping import RestoreRequest, RestoreResult, RestoreTextRequest
from api.routers.phi import phi_router
from api.routers.structured import structured_router
from api.services.anonymizer import anonymizer
from api.services.audit_log import audit_log
from api.services.crypto import crypto_engine
from api.services.phi.factory import PhiDetectorFactory
from api.services.phi.service import PhiDetectionService
from api.services.restorer import restorer
from api.services.token_store import token_store
from api.openapi_examples import (
    UNIFIED_ANONYMIZE_REQUEST_EXAMPLES,
    UNIFIED_ANONYMIZE_RESPONSE_EXAMPLES,
    UNIFIED_RESTORE_REQUEST_EXAMPLES,
    UNIFIED_RESTORE_RESPONSE_EXAMPLES,
    PREDICT_REQUEST_EXAMPLES,
    PREDICT_RESPONSE_EXAMPLES,
    BATCH_PREDICT_REQUEST_EXAMPLES,
    BATCH_PREDICT_RESPONSE_EXAMPLES,
    VALIDATE_REQUEST_EXAMPLES,
    VALIDATE_RESPONSE_EXAMPLES,
    MASK_REQUEST_EXAMPLES,
    MASK_RESPONSE_EXAMPLES,
    ANONYMIZE_API_REQUEST_EXAMPLES,
    ANONYMIZE_API_RESPONSE_EXAMPLES,
    INTERNAL_RESTORE_REQUEST_EXAMPLES,
    INTERNAL_RESTORE_RESPONSE_EXAMPLES,
    INTERNAL_RESTORE_TEXT_REQUEST_EXAMPLES,
    INTERNAL_RESTORE_TEXT_RESPONSE_EXAMPLES,
    ENTITIES_RESPONSE_EXAMPLES,
    INFO_RESPONSE_EXAMPLES,
    HEALTH_RESPONSE_EXAMPLES,
    READINESS_RESPONSE_EXAMPLES,
    ERROR_400_BAD_REQUEST,
    ERROR_422_UNPROCESSABLE,
    ERROR_503_NOT_READY,
)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("pii-phi-service")

# Prometheus Metrics
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency in seconds", ["endpoint"])
ENTITIES_DETECTED = Counter("pii_phi_entities_detected_total", "Count of sensitive entities detected", ["type"])

# PHI detector is swappable: OpenAI today, local model when PHI_DETECTOR_BACKEND=local
phi_service: PhiDetectionService = PhiDetectionService(PhiDetectorFactory().create(settings))

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_API_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_REPO_ROOT, "models", "roberta-pii-synthetic")
STATIC_DIR = os.path.join(_API_DIR, "ui")
MAX_TEXT_LENGTH = 10_000
MAX_BATCH_SIZE = 50
WORD_PATTERN = re.compile(r"\w+|[^\w\s]")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

model = None
tokenizer = None
model_load_error: Optional[str] = None
entity_types: List[str] = []


def load_model_and_warmup():
    global model, tokenizer, model_load_error, entity_types
    try:
        weights = os.path.join(MODEL_PATH, "model.safetensors")
        if os.path.exists(weights) and os.path.getsize(weights) < 1024:
            raise RuntimeError(
                f"{weights} is a Git LFS pointer, not real weights - run 'git lfs pull' before building the image"
            )
        tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, add_prefix_space=True)
        model = AutoModelForTokenClassification.from_pretrained(MODEL_PATH)
        model.to(DEVICE)
        model.eval()
        entity_types = sorted(
            {label.split("-", 1)[1] for label in model.config.id2label.values() if label != "O"}
        )
        # Pre-warm model with dummy tensor to initialize CPU/GPU kernels
        dummy_enc = tokenizer(["Warmup text"], is_split_into_words=True, return_tensors="pt", truncation=True)
        dummy_enc = {k: v.to(DEVICE) for k, v in dummy_enc.items()}
        with torch.inference_mode():
            _ = model(**dummy_enc).logits
        logger.info("RoBERTa PII model loaded and pre-warmed on %s with %d entity types", DEVICE, len(entity_types))
    except Exception as exc:  # noqa: BLE001
        model_load_error = str(exc)
        logger.exception("Failed to load or pre-warm PII model")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Lifecycle
    logger.info("Initializing PII/PHI Security Microservice on domain %s", settings.CUSTOM_DOMAIN)
    load_model_and_warmup()

    if settings.STORAGE_BACKEND.lower() == "postgresql":
        try:
            from api.database.connection import init_db_schema
            await init_db_schema()
            logger.info("Connected to PostgreSQL Token Vault and initialized schema")
        except Exception as e:
            logger.error("Failed to initialize PostgreSQL schema on startup: %s", e)

    yield

    # Shutdown Lifecycle
    logger.info("Shutting down PII/PHI Security Microservice")
    if settings.STORAGE_BACKEND.lower() == "postgresql":
        try:
            from api.database.connection import close_db_connections
            await close_db_connections()
        except Exception as e:
            logger.warning("Error closing PostgreSQL pool: %s", e)


OPENAPI_TAGS = [
    {
        "name": "1. FHIR & Structured Ingress",
        "description": "High-throughput FHIR Resource & Batch anonymization for Fasten Health EHR and JSON pipelines. Preserves LOINC/SNOMED/ICD-10.",
    },
    {
        "name": "2. PII Detection & Tokenization (RoBERTa)",
        "description": "Sub-40ms local RoBERTa model for demographic PII detection, masking, and reversible surrogate tokenization.",
    },
    {
        "name": "3. Clinical PHI Detection (OpenAI / Local)",
        "description": "Clinical NLP detector for unstructured doctor progress notes, discharge summaries, and medical narratives.",
    },
    {
        "name": "4. Reverse Tokenization & Token Vault",
        "description": "Authorized egress token restoration for doctor UI display with immutable HIPAA audit logging.",
    },
    {
        "name": "5. Policy & Governance",
        "description": "Per-organization PII/PHI handling rules and preset enforcement (HIPAA, GDPR, CCPA).",
    },
    {
        "name": "6. HIPAA Audit Logs",
        "description": "Immutable audit trail searching and compliance statistics.",
    },
    {
        "name": "7. System Health & Observability",
        "description": "Liveness (/health), Readiness (/ready), Prometheus Metrics (/metrics), and Model info.",
    },
    {
        "name": "8. Admin Portal",
        "description": "Web dashboard and administration console.",
    },
]

app = FastAPI(
    title="PII / PHI Security Microservice",
    description=(
        "Production-grade PII & Clinical PHI Anonymization & Reverse Tokenization Layer "
        "designed for AWS ECS / IONOS Kubernetes."
    ),
    version="2.0.0",
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    if "ValidationError" in schemas:
        schemas["ValidationError"]["example"] = {
            "loc": ["body", "text"],
            "msg": "field required",
            "type": "missing",
        }
    if "HTTPValidationError" in schemas:
        schemas["HTTPValidationError"]["example"] = {
            "detail": [
                {
                    "loc": ["body", "text"],
                    "msg": "field required",
                    "type": "missing",
                }
            ]
        }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Correlation ID and Request Timing Middleware
@app.middleware("http")
async def add_correlation_and_metrics(request: Request, call_next):
    req_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = req_id
    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time
    response.headers["x-request-id"] = req_id
    response.headers["x-response-time"] = f"{duration * 1000:.2f}ms"

    # Track Prometheus metrics
    endpoint = request.url.path
    status_code = str(response.status_code)
    REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status=status_code).inc()
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)

    return response


app.add_middleware(AnonymizationMiddleware, excluded_paths=settings.EXCLUDED_PATHS)
app.include_router(phi_router)
app.include_router(structured_router)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class Entity(BaseModel):
    entity: str
    text: str
    start: int
    end: int
    confidence: float
    category: Literal["pii", "phi"] = "pii"
    label: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "entity": "PERSON",
                "text": "Elijah Fisher",
                "start": 0,
                "end": 13,
                "confidence": 0.992,
                "category": "pii",
                "label": "Person",
            }
        }
    )


class TextValidationMixin:
    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty or whitespace-only")
        return v


class PredictRequest(BaseModel, TextValidationMixin):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH, description="Text to scan for PII")
    min_confidence: float = Field(0.0, ge=0.0, le=1.0, description="Drop entities below this confidence")

    model_config = ConfigDict(
        json_schema_extra={
            "example": PREDICT_REQUEST_EXAMPLES["standard_predict"]["value"]
        }
    )


class PredictResponse(BaseModel):
    text: str
    entities: List[Entity]
    entity_count: int
    contains_pii: bool

    model_config = ConfigDict(
        json_schema_extra={
            "example": PREDICT_RESPONSE_EXAMPLES["standard_predict_response"]["value"]
        }
    )


class BatchPredictRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1, max_length=MAX_BATCH_SIZE)
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
            "example": BATCH_PREDICT_REQUEST_EXAMPLES["standard_batch"]["value"]
        }
    )


class BatchPredictResponse(BaseModel):
    results: List[PredictResponse]

    model_config = ConfigDict(
        json_schema_extra={
            "example": BATCH_PREDICT_RESPONSE_EXAMPLES["standard_batch_response"]["value"]
        }
    )


class ValidateRequest(BaseModel, TextValidationMixin):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    entity_types: Optional[List[str]] = Field(
        default=None, description="Restrict the check to these entity types only"
    )
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": VALIDATE_REQUEST_EXAMPLES["validate_any"]["value"]
        }
    )


class ValidateResponse(BaseModel):
    contains_pii: bool
    entity_types_found: List[str]
    entity_count: int
    entities: List[Entity]

    model_config = ConfigDict(
        json_schema_extra={
            "example": VALIDATE_RESPONSE_EXAMPLES["validation_positive"]["value"]
        }
    )


class MaskRequest(BaseModel, TextValidationMixin):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    mask_style: Literal["type", "asterisk", "placeholder", "ignore", "anonymize", "normalize"] = "type"
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": MASK_REQUEST_EXAMPLES["style_type"]["value"]
        }
    )


class MaskResponse(BaseModel):
    original_text: str
    masked_text: str
    entities_masked: int
    entities: List[Entity]

    model_config = ConfigDict(
        json_schema_extra={
            "example": MASK_RESPONSE_EXAMPLES["style_type_response"]["value"]
        }
    )


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    device: str
    domain: str
    storage_backend: str
    detail: Optional[str] = None
    phi_ready: bool = False
    phi_backend: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": HEALTH_RESPONSE_EXAMPLES["healthy_service"]["value"]
        }
    )


class EntityTypesResponse(BaseModel):
    entity_types: List[str]
    count: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": ENTITIES_RESPONSE_EXAMPLES["supported_entities"]["value"]
        }
    )


class ServiceInfoResponse(BaseModel):
    name: str
    version: str
    description: str
    supported_entity_types: int
    phi_entity_types: int
    endpoints: List[str]

    model_config = ConfigDict(
        json_schema_extra={
            "example": INFO_RESPONSE_EXAMPLES["service_metadata"]["value"]
        }
    )


class AnonymizeApiRequest(BaseModel):
    text: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": ANONYMIZE_API_REQUEST_EXAMPLES["standard_middleware_request"]["value"]
        }
    )


class ReadinessResponse(BaseModel):
    ready: bool
    model_warm: bool
    database_connected: bool
    storage_backend: str
    details: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": READINESS_RESPONSE_EXAMPLES["service_ready"]["value"]
        }
    )


class UnifiedAnonymizeRequest(BaseModel):
    text: Optional[str] = None
    json_data: Optional[Any] = None
    org_id: str = "default"
    policy: str = "anonymize"

    model_config = ConfigDict(
        json_schema_extra={
            "example": UNIFIED_ANONYMIZE_REQUEST_EXAMPLES["mode_a_free_text"]["value"]
        }
    )


class UnifiedRestoreRequest(BaseModel):
    text: Optional[str] = None
    tokens: Optional[List[str]] = None
    json_data: Optional[Any] = None
    org_id: str = "default"
    purpose: str = "patient_care"

    model_config = ConfigDict(
        json_schema_extra={
            "example": UNIFIED_RESTORE_REQUEST_EXAMPLES["mode_b_restore_tokens"]["value"]
        }
    )


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------
def ensure_model_ready() -> None:
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail=f"Model is not available: {model_load_error}")


def run_inference(text: str) -> List[dict]:
    matches = list(WORD_PATTERN.finditer(text))
    words = [m.group() for m in matches]
    if not words:
        return []

    enc = tokenizer(words, is_split_into_words=True, return_tensors="pt", truncation=True)
    word_ids = enc.word_ids(batch_index=0)
    enc = {k: v.to(DEVICE) for k, v in enc.items()}

    with torch.inference_mode():
        logits = model(**enc).logits

    probs = torch.softmax(logits, dim=2)[0]
    preds = torch.argmax(logits, dim=2)[0].tolist()

    seen = set()
    word_records = []
    for sub_idx, word_idx in enumerate(word_ids):
        if word_idx is None or word_idx in seen:
            continue
        seen.add(word_idx)
        label_id = preds[sub_idx]
        raw_label = model.config.id2label[label_id]
        confidence = probs[sub_idx, label_id].item()
        match = matches[word_idx]
        word_records.append((raw_label, confidence, match.start(), match.end()))

    entities: List[dict] = []
    current: Optional[dict] = None
    for raw_label, confidence, start, end in word_records:
        if raw_label == "O":
            if current:
                entities.append(current)
                current = None
            continue
        tag, etype = raw_label.split("-", 1) if "-" in raw_label else ("B", raw_label)
        if current and current["entity"] == etype and tag == "I":
            current["end"] = end
            current["confidences"].append(confidence)
        else:
            if current:
                entities.append(current)
            current = {"entity": etype, "start": start, "end": end, "confidences": [confidence]}
    if current:
        entities.append(current)

    out = []
    for ent in entities:
        etype = ent["entity"]
        ENTITIES_DETECTED.labels(type=etype).inc()
        out.append(
            {
                "entity": etype,
                "text": text[ent["start"] : ent["end"]],
                "start": ent["start"],
                "end": ent["end"],
                "confidence": round(sum(ent["confidences"]) / len(ent["confidences"]), 4),
            }
        )
    return out


async def detect_entities(text: str, min_confidence: float = 0.0) -> List[dict]:
    if model is None:
        load_model_and_warmup()
    ensure_model_ready()
    entities = await run_in_threadpool(run_inference, text)
    if min_confidence > 0:
        entities = [e for e in entities if e["confidence"] >= min_confidence]
    for ent in entities:
        ent.setdefault("category", "pii")
        ent.setdefault("label", ent["entity"].replace("_", " ").title())
    return entities


def build_masked_text(text: str, entities: List[dict], style: str) -> str:
    if not entities:
        return text
    ordered = sorted(entities, key=lambda e: e["start"])
    pieces = []
    cursor = 0
    for ent in ordered:
        pieces.append(text[cursor : ent["start"]])
        if style == "type":
            pieces.append(f"[{ent['entity']}]")
        elif style == "placeholder":
            pieces.append("<REDACTED>")
        elif style == "ignore":
            pieces.append(text[ent["start"] : ent["end"]])
        elif style in ("anonymize", "normalize"):
            from api.services.anonymizer import RandomizedStrategy
            gen = RandomizedStrategy.GENERATORS.get(ent["entity"].upper())
            if gen:
                pieces.append(gen())
            else:
                pieces.append("X" * (ent["end"] - ent["start"]))
        else:  # asterisk
            pieces.append("*" * (ent["end"] - ent["start"]))
        cursor = ent["end"]
    pieces.append(text[cursor:])
    return "".join(pieces)


# ---------------------------------------------------------------------------
# Simple Top-Level Clean Endpoints (No Ports, Simple URLs)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Simple Top-Level Clean Endpoints (No Ports, Simple URLs)
# ---------------------------------------------------------------------------
@app.post(
    "/anonymize",
    tags=["2. PII Detection & Tokenization (RoBERTa)"],
    responses={
        200: {
            "description": "Text or JSON Successfully Anonymized",
            "content": {
                "application/json": {
                    "examples": UNIFIED_ANONYMIZE_RESPONSE_EXAMPLES
                }
            }
        },
        400: ERROR_400_BAD_REQUEST,
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def unified_anonymize(
    payload: UnifiedAnonymizeRequest = Body(
        ...,
        openapi_examples=UNIFIED_ANONYMIZE_REQUEST_EXAMPLES
    )
):
    """Clean Top-Level Anonymization Endpoint (handles text or structured JSON)."""
    if payload.json_data is not None:
        from api.services.fhir_anonymizer import fhir_anonymizer
        anon_data, mappings = await fhir_anonymizer.anonymize_fhir_resource(
            payload.json_data, org_id=payload.org_id
        )
        return {
            "anonymized_data": anon_data,
            "entity_count": len(mappings),
            "mappings": [
                {
                    "entity_type": m.entity_type,
                    "original_value": m.original_value,
                    "tokenized_value": m.tokenized_value,
                }
                for m in mappings
            ],
        }

    if payload.text is not None:
        ensure_model_ready()
        entities = await detect_entities(payload.text)
        anonymized_text = build_masked_text(payload.text, entities, style="type")
        return {
            "original_text": payload.text,
            "anonymized_text": anonymized_text,
            "entities": entities,
            "entity_count": len(entities),
        }

    raise HTTPException(status_code=400, detail="Must provide either 'text' or 'json_data'")


@app.post(
    "/restore",
    tags=["4. Reverse Tokenization & Token Vault"],
    responses={
        200: {
            "description": "Tokens Successfully Restored for UI Display",
            "content": {
                "application/json": {
                    "examples": UNIFIED_RESTORE_RESPONSE_EXAMPLES
                }
            }
        },
        400: ERROR_400_BAD_REQUEST,
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def unified_restore(
    payload: UnifiedRestoreRequest = Body(
        ...,
        openapi_examples=UNIFIED_RESTORE_REQUEST_EXAMPLES
    ),
    request: Request = None,
):
    """Clean Top-Level Restoration Endpoint for authorized clinical display."""
    api_key = request.headers.get("x-api-key", "") if request else ""
    current_user = f"user-{abs(hash(api_key)) % 10000}" if api_key else "system-user"
    client_ip = request.client.host if (request and request.client) else "127.0.0.1"

    if payload.text is not None:
        restored = await restorer.restore_in_text(
            payload.text, payload.org_id, current_user, payload.purpose, client_ip
        )
        return {"restored_text": restored}

    if payload.json_data is not None:
        restored = await restorer.restore_in_json(
            payload.json_data, payload.org_id, current_user, payload.purpose, client_ip
        )
        return {"restored_data": restored}

    if payload.tokens:
        results = await restorer.restore(
            RestoreRequest(
                tokenized_values=payload.tokens,
                org_id=payload.org_id,
                requester_id=current_user,
                ip_address=client_ip,
                purpose=payload.purpose,
            )
        )
        return {"results": [r.__dict__ for r in results]}

    raise HTTPException(status_code=400, detail="Must provide 'text', 'json_data', or 'tokens'")


# ---------------------------------------------------------------------------
# Health, Readiness & Metrics Endpoints (AWS ALB / CloudWatch Probes)
# ---------------------------------------------------------------------------
@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["7. System Health & Observability"],
    responses={
        200: {
            "description": "Liveness Probe: Service Running",
            "content": {
                "application/json": {
                    "examples": HEALTH_RESPONSE_EXAMPLES
                }
            }
        }
    }
)
@app.get(
    "/healthz",
    response_model=HealthResponse,
    tags=["7. System Health & Observability"],
    responses={
        200: {
            "description": "Liveness Probe: Service Running",
            "content": {
                "application/json": {
                    "examples": HEALTH_RESPONSE_EXAMPLES
                }
            }
        }
    }
)
async def health():
    """Liveness probe: returns 200 OK when process is running."""
    phi_status = phi_service.status()
    pii_ok = model is not None
    overall = "ok" if pii_ok else "degraded"
    return HealthResponse(
        status=overall,
        model_loaded=pii_ok,
        device=DEVICE,
        domain=settings.CUSTOM_DOMAIN,
        storage_backend=settings.STORAGE_BACKEND,
        detail=model_load_error,
        phi_ready=phi_status.ready,
        phi_backend=phi_status.backend,
    )


@app.get(
    "/ready",
    response_model=ReadinessResponse,
    tags=["7. System Health & Observability"],
    responses={
        200: {
            "description": "Readiness Probe: Model Warm & DB Connected",
            "content": {
                "application/json": {
                    "examples": READINESS_RESPONSE_EXAMPLES
                }
            }
        },
        503: ERROR_503_NOT_READY,
    }
)
async def readiness():
    """Readiness probe: validates RoBERTa model is warm in RAM and Database is healthy."""
    model_warm = model is not None
    db_connected = True

    if settings.STORAGE_BACKEND.lower() == "postgresql":
        from api.database.connection import check_db_health
        db_connected = await check_db_health()

    ready = model_warm and db_connected
    if not ready:
        raise HTTPException(
            status_code=503,
            detail=f"Service Not Ready (model_warm={model_warm}, db_connected={db_connected})",
        )

    return ReadinessResponse(
        ready=ready,
        model_warm=model_warm,
        database_connected=db_connected,
        storage_backend=settings.STORAGE_BACKEND,
    )


@app.get(
    "/metrics",
    tags=["7. System Health & Observability"],
    responses={
        200: {
            "description": "Prometheus text metrics format for ECS CloudWatch and Grafana",
            "content": {
                "text/plain": {
                    "example": (
                        "# HELP phi_tokens_anonymized_total Total tokens anonymized\n"
                        "# TYPE phi_tokens_anonymized_total counter\n"
                        "phi_tokens_anonymized_total 42.0\n"
                        "# HELP http_requests_total Total HTTP requests\n"
                        "# TYPE http_requests_total counter\n"
                        'http_requests_total{status="200"} 150.0\n'
                        "# HELP process_resident_memory_bytes Resident memory size in bytes\n"
                        "# TYPE process_resident_memory_bytes gauge\n"
                        "process_resident_memory_bytes 314572800.0"
                    )
                }
            },
        }
    },
)
async def metrics():
    """Prometheus metrics endpoint for ECS CloudWatch / Grafana monitoring."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get(
    "/info",
    response_model=ServiceInfoResponse,
    tags=["7. System Health & Observability"],
    responses={
        200: {
            "description": "Metadata and service information",
            "content": {
                "application/json": {
                    "examples": INFO_RESPONSE_EXAMPLES
                }
            }
        }
    }
)
async def service_info():
    """Metadata and service information."""
    phi_status = phi_service.status()
    return ServiceInfoResponse(
        name="PII / PHI Security Microservice",
        version=app.version,
        description=(
            "Production-grade PII & Clinical PHI Anonymization & Reverse Tokenization Layer "
            f"(domain={settings.CUSTOM_DOMAIN}, phi_backend={phi_status.backend})."
        ),
        supported_entity_types=len(entity_types),
        phi_entity_types=len(phi_service.entity_type_names()),
        endpoints=[
            "/health",
            "/healthz",
            "/ready",
            "/metrics",
            "/info",
            "/entities",
            "/predict",
            "/predict/batch",
            "/validate",
            "/mask",
            "/anonymize",
            "/restore",
            "/phi/health",
            "/phi/entities",
            "/phi/predict",
            "/phi/predict/batch",
            "/phi/validate",
            "/phi/mask",
            "/phi/anonymize",
            "/api/v1/anonymize",
            "/api/v1/anonymize/fhir",
            "/api/v1/anonymize/fhir/batch",
            "/api/v1/anonymize/json",
            "/internal/restore",
            "/internal/restore-text",
            "/internal/restore-json",
        ],
    )


# ---------------------------------------------------------------------------
# Standard PII Endpoints
# ---------------------------------------------------------------------------
@app.get(
    "/entities",
    response_model=EntityTypesResponse,
    tags=["2. PII Detection & Tokenization (RoBERTa)"],
    responses={
        200: {
            "description": "List supported PII entity types",
            "content": {
                "application/json": {
                    "examples": ENTITIES_RESPONSE_EXAMPLES
                }
            }
        }
    }
)
async def list_entities():
    """List supported PII entity types from the fine-tuned RoBERTa model."""
    ensure_model_ready()
    return EntityTypesResponse(entity_types=entity_types, count=len(entity_types))


@app.post(
    "/predict",
    response_model=PredictResponse,
    tags=["2. PII Detection & Tokenization (RoBERTa)"],
    responses={
        200: {
            "description": "Entities Detected with Confidence Scores",
            "content": {
                "application/json": {
                    "examples": PREDICT_RESPONSE_EXAMPLES
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def predict(
    payload: PredictRequest = Body(
        ...,
        openapi_examples=PREDICT_REQUEST_EXAMPLES
    )
):
    ensure_model_ready()
    entities = await detect_entities(payload.text, payload.min_confidence)
    return PredictResponse(
        text=payload.text,
        entities=entities,
        entity_count=len(entities),
        contains_pii=len(entities) > 0,
    )


@app.post(
    "/predict/batch",
    response_model=BatchPredictResponse,
    tags=["2. PII Detection & Tokenization (RoBERTa)"],
    responses={
        200: {
            "description": "Batch Predictions Complete",
            "content": {
                "application/json": {
                    "examples": BATCH_PREDICT_RESPONSE_EXAMPLES
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def predict_batch(
    payload: BatchPredictRequest = Body(
        ...,
        openapi_examples=BATCH_PREDICT_REQUEST_EXAMPLES
    )
):
    ensure_model_ready()
    results = []
    for text in payload.texts:
        entities = await detect_entities(text, payload.min_confidence)
        results.append(
            PredictResponse(
                text=text,
                entities=entities,
                entity_count=len(entities),
                contains_pii=len(entities) > 0,
            )
        )
    return BatchPredictResponse(results=results)


@app.post(
    "/validate",
    response_model=ValidateResponse,
    tags=["2. PII Detection & Tokenization (RoBERTa)"],
    responses={
        200: {
            "description": "Validation Complete (PII Presence Checked)",
            "content": {
                "application/json": {
                    "examples": VALIDATE_RESPONSE_EXAMPLES
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def validate(
    payload: ValidateRequest = Body(
        ...,
        openapi_examples=VALIDATE_REQUEST_EXAMPLES
    )
):
    ensure_model_ready()
    entities = await detect_entities(payload.text, payload.min_confidence)
    if payload.entity_types:
        allowed = {t.upper() for t in payload.entity_types}
        entities = [e for e in entities if e["entity"] in allowed]
    types_found = sorted({e["entity"] for e in entities})
    return ValidateResponse(
        contains_pii=len(entities) > 0,
        entity_types_found=types_found,
        entity_count=len(entities),
        entities=entities,
    )


@app.post(
    "/mask",
    response_model=MaskResponse,
    tags=["2. PII Detection & Tokenization (RoBERTa)"],
    responses={
        200: {
            "description": "Text Masked with Specified Strategy",
            "content": {
                "application/json": {
                    "examples": MASK_RESPONSE_EXAMPLES
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def mask(
    payload: MaskRequest = Body(
        ...,
        openapi_examples=MASK_REQUEST_EXAMPLES
    )
):
    ensure_model_ready()
    entities = await detect_entities(payload.text, payload.min_confidence)
    masked_text = build_masked_text(payload.text, entities, payload.mask_style)
    return MaskResponse(
        original_text=payload.text,
        masked_text=masked_text,
        entities_masked=len(entities),
        entities=entities,
    )


@app.post(
    "/api/v1/anonymize",
    tags=["2. PII Detection & Tokenization (RoBERTa)"],
    responses={
        200: {
            "description": "Middleware Anonymization Result",
            "content": {
                "application/json": {
                    "examples": ANONYMIZE_API_RESPONSE_EXAMPLES
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def anonymize_endpoint(
    request: Request,
    payload: AnonymizeApiRequest = Body(
        ...,
        openapi_examples=ANONYMIZE_API_REQUEST_EXAMPLES
    )
):
    """Processes request through AnonymizationMiddleware, saving tokens, and returns anonymized text"""
    mappings = getattr(request.state, "anonymization_mappings", [])
    mappings_summary = []

    for m in mappings:
        try:
            original = m.original_value
            if isinstance(original, str) and original.startswith("gAAAAA"):
                original = token_store.decrypt(original)
        except Exception:
            original = m.original_value

        mappings_summary.append({
            "entity_type": m.entity_type,
            "original_value": original,
            "tokenized_value": m.tokenized_value,
            "policy_applied": m.policy_applied,
        })

    return {
        "anonymized_text": payload.text,
        "mappings": mappings_summary,
    }


# ---------------------------------------------------------------------------
# Reverse Tokenization Endpoints
# ---------------------------------------------------------------------------
async def get_current_user(request: Request) -> str:
    api_key = request.headers.get("x-api-key")
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    return f"user-{abs(hash(api_key)) % 10000}"


@app.post(
    "/internal/restore",
    tags=["4. Reverse Tokenization & Token Vault"],
    responses={
        200: {
            "description": "Direct Token Vault Restore Results",
            "content": {
                "application/json": {
                    "examples": INTERNAL_RESTORE_RESPONSE_EXAMPLES
                }
            }
        },
        401: {"description": "API Key Required"},
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def restore_tokens(
    request: RestoreRequest = Body(
        ...,
        openapi_examples=INTERNAL_RESTORE_REQUEST_EXAMPLES
    ),
    current_user: str = Depends(get_current_user),
):
    results = await restorer.restore(request)
    return {"results": [r.__dict__ for r in results]}


@app.post(
    "/internal/restore-text",
    tags=["4. Reverse Tokenization & Token Vault"],
    responses={
        200: {
            "description": "Internal Restored Cleartext",
            "content": {
                "application/json": {
                    "examples": INTERNAL_RESTORE_TEXT_RESPONSE_EXAMPLES
                }
            }
        },
        401: {"description": "API Key Required"},
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def restore_in_text(
    request: RestoreTextRequest = Body(
        ...,
        openapi_examples=INTERNAL_RESTORE_TEXT_REQUEST_EXAMPLES
    ),
    current_user: str = Depends(get_current_user),
):
    restored = await restorer.restore_in_text(
        request.text, request.org_id, current_user, request.purpose, request.ip_address
    )
    return {"restored_text": restored}


# Admin portal and /api/v1 admin routes live on pds-agent. Point bookmarks here
# before the "/" static mount, which would otherwise swallow /admin.
def _admin_on_agent_detail(path: str) -> dict:
    detail = {
        "detail": "The admin portal is served by the pds-agent service, not this host.",
        "path": "/" + path.lstrip("/"),
    }
    agent_base = os.getenv("PDS_AGENT_BASE_URL", "").rstrip("/")
    if agent_base:
        detail["admin_portal"] = f"{agent_base}/admin/"
        detail["admin_api_docs"] = f"{agent_base}/docs"
    return detail


@app.get("/admin", include_in_schema=False)
@app.get("/admin/{full_path:path}", include_in_schema=False)
async def admin_lives_on_agent(full_path: str = ""):
    pointed = f"admin/{full_path}" if full_path else "admin"
    raise HTTPException(status_code=404, detail=_admin_on_agent_detail(pointed))


if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")


if __name__ == "__main__":
    uvicorn.run(app, host=settings.SERVICE_HOST, port=settings.SERVICE_PORT)
