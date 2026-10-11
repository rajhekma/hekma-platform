"""Hekma Patient Health — S3.

Owns patient profile, EHR ingest, FHIR store, medications, and account deletion.
Identity still issues tokens; this service only validates them and checks ownership.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .apis.account_deletion_api import router as account_deletion_router
from .apis.clinical_fhir_api import router as clinical_fhir_router
from .apis.fasten_api import router as fasten_router
from .apis.medications_api import router as medications_router
from .apis.patient_api import router as patient_router
from .settings import get_settings

logger = logging.getLogger("hekma.patient_health")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not os.getenv("JWT_SECRET") and settings.jwt_secret:
        os.environ["JWT_SECRET"] = settings.jwt_secret
    if settings.jwt_algorithm:
        os.environ.setdefault("JWT_ALGORITHM", settings.jwt_algorithm)
    logger.info("Patient Health started on port %s", settings.service_port)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Hekma Patient Health",
        version="1.0.0",
        description=(
            "Patient profile, EHR integration, FHIR store, medications, "
            "and account deletion."
        ),
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok", "service": "hekma-patient-health"}

    @app.get("/ready", tags=["ops"])
    def ready():
        """Fail ready if we cannot validate tokens — better than serving blindly."""
        if not (os.getenv("JWT_SECRET") or get_settings().jwt_secret):
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reason": "JWT_SECRET missing"},
            )
        return {"status": "ready", "service": "hekma-patient-health"}

    app.include_router(patient_router)
    app.include_router(fasten_router)
    app.include_router(clinical_fhir_router)
    app.include_router(medications_router)
    app.include_router(account_deletion_router)
    return app


app = create_app()
