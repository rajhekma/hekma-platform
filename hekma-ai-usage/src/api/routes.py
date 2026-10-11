from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from api.schemas import (
    EventListResponse,
    HealthResponse,
    IngestResult,
    PatientCostResponse,
    PriceRow,
    UsageEventIn,
)
from config import Settings
from repository.store import UsageRepository
from service.ingest import IngestService, empty_period_start
from service.query import assemble_patient_cost

logger = logging.getLogger("hekma.ai_usage")


def register_routes(app: FastAPI) -> None:
    def current_repo() -> UsageRepository:
        return app.state.repo

    def current_ingest() -> IngestService:
        return app.state.ingest

    def current_settings() -> Settings:
        return app.state.settings

    def require_key(
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
        cfg: Settings = Depends(current_settings),
    ) -> None:
        if cfg.ai_cost_api_key and x_api_key != cfg.ai_cost_api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    @app.exception_handler(ValueError)
    async def _value_error(_, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/health", response_model=HealthResponse)
    @app.get("/v1/ai-cost/health", response_model=HealthResponse)
    def health(store: UsageRepository = Depends(current_repo), cfg: Settings = Depends(current_settings)):
        db_ok = False
        try:
            db_ok = store.ping()
        except Exception:
            logger.exception("database ping failed")
        return HealthResponse(
            status="ok" if db_ok else "degraded",
            database="up" if db_ok else "down",
            sqs="enabled" if cfg.sqs_enabled else "disabled",
        )

    @app.post(
        "/internal/v1/ai-usage/events",
        response_model=IngestResult,
        dependencies=[Depends(require_key)],
    )
    def ingest_event(body: UsageEventIn, ingest: IngestService = Depends(current_ingest)):
        return ingest.ingest(body)

    @app.post(
        "/internal/v1/ai-usage/events:batch",
        dependencies=[Depends(require_key)],
    )
    def ingest_batch(body: list[UsageEventIn], ingest: IngestService = Depends(current_ingest)):
        return [ingest.ingest(item) for item in body]

    @app.get(
        "/v1/patients/{patient_id}/ai-cost",
        response_model=PatientCostResponse,
        dependencies=[Depends(require_key)],
    )
    def patient_cost(
        patient_id: str,
        store: UsageRepository = Depends(current_repo),
        cfg: Settings = Depends(current_settings),
        product: Optional[str] = Query(default=None),
        tenant_id: Optional[int] = Query(default=None),
        from_: Optional[datetime] = Query(default=None, alias="from"),
        to: Optional[datetime] = Query(default=None),
    ):
        start = from_ or empty_period_start()
        end = to or datetime.now(timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if end <= start:
            raise HTTPException(status_code=400, detail="`to` must be after `from`")
        return assemble_patient_cost(
            store,
            tenant_id=tenant_id or cfg.default_tenant_id,
            patient_id=str(patient_id),
            start=start,
            end=end,
            product=product,
        )

    @app.get(
        "/v1/patients/{patient_id}/ai-cost/events",
        response_model=EventListResponse,
        dependencies=[Depends(require_key)],
    )
    def patient_events(
        patient_id: str,
        store: UsageRepository = Depends(current_repo),
        cfg: Settings = Depends(current_settings),
        product: Optional[str] = Query(default=None),
        tenant_id: Optional[int] = Query(default=None),
        from_: Optional[datetime] = Query(default=None, alias="from"),
        to: Optional[datetime] = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        start = from_ or empty_period_start()
        end = to or datetime.now(timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        total, events = store.list_events(
            tenant_id=tenant_id or cfg.default_tenant_id,
            patient_id=str(patient_id),
            start=start,
            end=end,
            product=product,
            limit=limit,
            offset=offset,
        )
        return EventListResponse(patient_id=str(patient_id), total=total, events=events)

    @app.get(
        "/v1/ai-cost/prices",
        response_model=list[PriceRow],
        dependencies=[Depends(require_key)],
    )
    def list_prices(store: UsageRepository = Depends(current_repo)):
        return [
            PriceRow(
                provider=p.provider,
                model=p.model,
                input_usd_per_1m=float(p.input_usd_per_1m),
                output_usd_per_1m=float(p.output_usd_per_1m),
                effective_from=p.effective_from,
                effective_to=p.effective_to,
            )
            for p in store.list_prices()
        ]

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        response = await call_next(request)
        logger.info("%s %s -> %s", request.method, request.url.path, response.status_code)
        return response
