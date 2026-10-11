from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from service.pricing import price_tokens
from repository.store import UsageRepository
from service.models import IngestResult, UsageEventIn

logger = logging.getLogger(__name__)


class IngestService:
    def __init__(self, repo: UsageRepository) -> None:
        self._repo = repo

    def ingest(self, raw: dict[str, Any] | UsageEventIn) -> IngestResult:
        event = raw if isinstance(raw, UsageEventIn) else UsageEventIn.model_validate(raw)
        if event.cached:
            logger.info(
                "dropping cached usage event request_id=%s patient_id=%s",
                event.request_id,
                event.patient_id,
            )
            return IngestResult(
                accepted=False,
                request_id=event.request_id,
                pricing_status="priced",
                cost_usd=0.0,
            )

        occurred = event.occurred_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)

        priced = price_tokens(
            self._repo.list_prices(occurred),
            provider=event.provider,
            model=event.model,
            prompt_tokens=event.prompt_tokens,
            completion_tokens=event.completion_tokens,
            at=occurred,
        )
        if priced.pricing_status == "unpriced":
            logger.warning(
                "unpriced model provider=%s model=%s request_id=%s",
                event.provider,
                event.model,
                event.request_id,
            )

        row = {
            "request_id": str(event.request_id),
            "tenant_id": int(event.tenant_id),
            "patient_id": event.patient_id,
            "product": event.product,
            "feature": event.feature or "",
            "provider": event.provider,
            "model": event.model,
            "prompt_tokens": event.prompt_tokens,
            "completion_tokens": event.completion_tokens,
            "total_tokens": event.resolved_total_tokens(),
            "input_cost_usd": priced.input_cost_usd,
            "output_cost_usd": priced.output_cost_usd,
            "cost_usd": priced.cost_usd,
            "pricing_status": priced.pricing_status,
            "price_version": priced.price_version,
            "cached": False,
            "job_id": event.job_id,
            "source_service": event.source_service,
            "occurred_at": occurred,
            "schema_version": event.schema_version,
        }
        inserted = self._repo.insert_event(row)
        return IngestResult(
            accepted=True,
            duplicate=not inserted,
            request_id=event.request_id if isinstance(event.request_id, UUID) else UUID(str(event.request_id)),
            pricing_status=priced.pricing_status,
            cost_usd=float(priced.cost_usd),
        )


def empty_period_start() -> datetime:
    return datetime(1970, 1, 1, tzinfo=timezone.utc)
