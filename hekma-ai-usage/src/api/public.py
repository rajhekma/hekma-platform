from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query

from api.deps import AppDeps, require_key
from api.schemas import HealthResponse
from repository.store import UsageRepository
from service.ingest import empty_period_start
from service.models import EventListResponse, PatientCostResponse, PriceRow
from service.query import assemble_patient_cost

logger = logging.getLogger("hekma.ai_usage")


def _period(from_: Optional[datetime], to: Optional[datetime]) -> tuple[datetime, datetime]:
    start = from_ or empty_period_start()
    end = to or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end <= start:
        raise HTTPException(status_code=400, detail="`to` must be after `from`")
    return start, end


def register_public(app: FastAPI, deps: AppDeps) -> None:
    """Routes the gateway may publish."""

    @app.get("/health", response_model=HealthResponse)
    @app.get("/v1/ai-cost/health", response_model=HealthResponse)
    def health(
        store: UsageRepository = Depends(deps.current_repo),
        cfg=Depends(deps.current_settings),
    ):
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

    @app.get(
        "/v1/patients/{patient_id}/ai-cost",
        response_model=PatientCostResponse,
        dependencies=[Depends(require_key(deps))],
    )
    def patient_cost(
        patient_id: str,
        store: UsageRepository = Depends(deps.current_repo),
        cfg=Depends(deps.current_settings),
        product: Optional[str] = Query(default=None),
        tenant_id: Optional[int] = Query(default=None),
        from_: Optional[datetime] = Query(default=None, alias="from"),
        to: Optional[datetime] = Query(default=None),
    ):
        start, end = _period(from_, to)
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
        dependencies=[Depends(require_key(deps))],
    )
    def patient_events(
        patient_id: str,
        store: UsageRepository = Depends(deps.current_repo),
        cfg=Depends(deps.current_settings),
        product: Optional[str] = Query(default=None),
        tenant_id: Optional[int] = Query(default=None),
        from_: Optional[datetime] = Query(default=None, alias="from"),
        to: Optional[datetime] = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        start, end = _period(from_, to)
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
        dependencies=[Depends(require_key(deps))],
    )
    def list_prices(store: UsageRepository = Depends(deps.current_repo)):
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
