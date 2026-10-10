from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .config import Settings, get_settings
from .ingest_service import IngestService, empty_period_start
from .query import assemble_patient_cost
from .repository import PostgresUsageRepository, UsageRepository, open_repository
from .schemas import (
    EventListResponse,
    HealthResponse,
    IngestResult,
    PatientCostResponse,
    PriceRow,
    UsageEventIn,
)
from .sqs_worker import SqsWorker

logger = logging.getLogger("hekma.ai_usage")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app(
    repo: Optional[UsageRepository] = None,
    settings: Optional[Settings] = None,
    start_sqs: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    worker_holder: dict[str, Optional[SqsWorker]] = {"worker": None}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned_repo = False
        if getattr(app.state, "repo", None) is None:
            store = open_repository(settings.database_url)
            if hasattr(store, "migrate"):
                store.migrate()
            app.state.repo = store
            owned_repo = True
        app.state.settings = settings
        app.state.ingest = IngestService(app.state.repo)
        if start_sqs and settings.sqs_enabled and isinstance(app.state.repo, PostgresUsageRepository):
            try:
                worker = SqsWorker(app.state.ingest, settings)
                worker.start()
                worker_holder["worker"] = worker
            except Exception:
                logger.exception("SQS worker did not start; HTTP ingest remains available")
        yield
        if worker_holder["worker"]:
            worker_holder["worker"].stop()
        if owned_repo and hasattr(app.state.repo, "close"):
            app.state.repo.close()

    app = FastAPI(
        title="Hekma Commerce — AI Cost Analytics",
        version="1.0.0",
        lifespan=lifespan,
    )
    if repo is not None:
        app.state.repo = repo
        app.state.settings = settings
        app.state.ingest = IngestService(repo)

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

    return app


app = create_app()
