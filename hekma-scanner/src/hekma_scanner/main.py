"""Hekma Scanner — Clinical AI.

Owns document scan (MS-11) and EHR summary (MS-13). Identity issues tokens;
this service validates them and checks ownership. Medication *APIs* stay on
Patient Health; persistRecords may still write extracted meds during the
strangler period.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .apis.clinical_scans_api import router as clinical_scans_router
from .apis.ehr_summary_api import router as ehr_summary_router
from .settings import get_settings

logger = logging.getLogger("hekma.scanner")
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
    logger.info("Scanner started on port %s", settings.service_port)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Hekma Scanner",
        version="1.0.0",
        description="Clinical document scan and EHR summary.",
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
        return {"status": "ok", "service": "hekma-scanner"}

    @app.get("/ready", tags=["ops"])
    def ready():
        if not (os.getenv("JWT_SECRET") or get_settings().jwt_secret):
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reason": "JWT_SECRET missing"},
            )
        return {"status": "ready", "service": "hekma-scanner"}

    app.include_router(clinical_scans_router)
    app.include_router(ehr_summary_router)
    return app


app = create_app()
