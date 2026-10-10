from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

from .repository import UsageRepository
from .schemas import (
    CostBucket,
    ModelCost,
    PatientCostResponse,
    Period,
    ProductCost,
    ProviderCost,
    money,
)


def _bucket(row: dict) -> dict:
    return {
        "llm_calls": int(row.get("llm_calls") or 0),
        "prompt_tokens": int(row.get("prompt_tokens") or 0),
        "completion_tokens": int(row.get("completion_tokens") or 0),
        "total_tokens": int(row.get("total_tokens") or 0),
        "cost_usd": money(row.get("cost_usd")),
        "unpriced_calls": int(row.get("unpriced_calls") or 0),
    }


def assemble_patient_cost(
    repo: UsageRepository,
    *,
    tenant_id: int,
    patient_id: str,
    start: datetime,
    end: datetime,
    product: Optional[str] = None,
) -> PatientCostResponse:
    rows = repo.aggregate_patient(
        tenant_id=tenant_id,
        patient_id=patient_id,
        start=start,
        end=end,
        product=product,
    )

    totals = CostBucket()
    products: list[ProductCost] = []
    models_by_provider: dict[str, list[ModelCost]] = defaultdict(list)
    provider_totals: dict[str, dict] = {}

    for row in rows:
        has_product = row.get("product") is not None
        has_provider = row.get("provider") is not None
        if not has_product and not has_provider:
            totals = CostBucket(**_bucket(row))
        elif has_product and not has_provider:
            products.append(ProductCost(product=row["product"], **_bucket(row)))
        elif has_provider:
            provider = row["provider"]
            model = ModelCost(model=row["model"], **_bucket(row))
            models_by_provider[provider].append(model)
            acc = provider_totals.setdefault(
                provider,
                {
                    "llm_calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                    "unpriced_calls": 0,
                },
            )
            acc["llm_calls"] += model.llm_calls
            acc["prompt_tokens"] += model.prompt_tokens
            acc["completion_tokens"] += model.completion_tokens
            acc["total_tokens"] += model.total_tokens
            acc["cost_usd"] = money(acc["cost_usd"] + model.cost_usd)
            acc["unpriced_calls"] += model.unpriced_calls

    providers = [
        ProviderCost(
            provider=name,
            models=sorted(models_by_provider[name], key=lambda m: m.cost_usd, reverse=True),
            **stats,
        )
        for name, stats in sorted(
            provider_totals.items(),
            key=lambda item: item[1]["cost_usd"],
            reverse=True,
        )
    ]
    products.sort(key=lambda p: p.cost_usd, reverse=True)

    return PatientCostResponse(
        patient_id=patient_id,
        tenant_id=tenant_id,
        period=Period(**{"from": start, "to": end}),
        totals=totals,
        by_product=products,
        by_provider=providers,
    )
