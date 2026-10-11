from __future__ import annotations

from fastapi import Depends, FastAPI

from api.deps import AppDeps, require_key
from service.ingest import IngestService
from service.models import IngestResult, UsageEventIn


def register_internal(app: FastAPI, deps: AppDeps) -> None:
    """Ingest stays off the public gateway. Callers use the service URL or SQS."""

    @app.post(
        "/internal/v1/ai-usage/events",
        response_model=IngestResult,
        tags=["Ingest"],
        dependencies=[Depends(require_key(deps))],
    )
    def ingest_event(body: UsageEventIn, ingest: IngestService = Depends(deps.current_ingest)):
        return ingest.ingest(body)

    @app.post(
        "/internal/v1/ai-usage/events:batch",
        tags=["Ingest"],
        dependencies=[Depends(require_key(deps))],
    )
    def ingest_batch(body: list[UsageEventIn], ingest: IngestService = Depends(deps.current_ingest)):
        return [ingest.ingest(item) for item in body]
