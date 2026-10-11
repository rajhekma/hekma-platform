from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from service.pricing import normalize_provider

ALLOWED_PRODUCTS = frozenset({"scan_ai", "patient_summary", "trial_match"})


class UsageEventIn(BaseModel):
    schema_version: int = 1
    request_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime
    tenant_id: int = 1
    patient_id: str
    product: str
    feature: str = ""
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: Optional[int] = None
    cached: bool = False
    job_id: Optional[str] = None
    source_service: Optional[str] = None

    @field_validator("patient_id", "model")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("product")
    @classmethod
    def _product(cls, value: str) -> str:
        value = (value or "").strip()
        if value not in ALLOWED_PRODUCTS:
            raise ValueError(f"product must be one of {sorted(ALLOWED_PRODUCTS)}")
        return value

    @field_validator("provider")
    @classmethod
    def _provider(cls, value: str) -> str:
        return normalize_provider(value)

    @field_validator("prompt_tokens", "completion_tokens")
    @classmethod
    def _non_negative(cls, value: int) -> int:
        return max(int(value or 0), 0)

    def resolved_total_tokens(self) -> int:
        if self.total_tokens is not None and self.total_tokens >= 0:
            return int(self.total_tokens)
        return self.prompt_tokens + self.completion_tokens


class IngestResult(BaseModel):
    accepted: bool
    duplicate: bool = False
    request_id: UUID
    pricing_status: str
    cost_usd: float = 0.0


class CostBucket(BaseModel):
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    unpriced_calls: int = 0


class ProductCost(CostBucket):
    product: str


class ModelCost(CostBucket):
    model: str


class ProviderCost(CostBucket):
    provider: str
    models: list[ModelCost] = Field(default_factory=list)


class Period(BaseModel):
    from_: datetime = Field(alias="from")
    to: datetime

    model_config = {"populate_by_name": True, "ser_json_by_alias": True}


class PatientCostResponse(BaseModel):
    patient_id: str
    tenant_id: int
    period: Period
    currency: str = "USD"
    totals: CostBucket
    by_product: list[ProductCost]
    by_provider: list[ProviderCost]


class UsageEventOut(BaseModel):
    request_id: UUID
    occurred_at: datetime
    product: str
    feature: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    pricing_status: str
    job_id: Optional[str] = None
    source_service: Optional[str] = None


class EventListResponse(BaseModel):
    patient_id: str
    total: int
    events: list[UsageEventOut]


class PriceRow(BaseModel):
    provider: str
    model: str
    input_usd_per_1m: float
    output_usd_per_1m: float
    effective_from: datetime
    effective_to: Optional[datetime] = None


class HealthResponse(BaseModel):
    status: str
    service: str = "ai-usage"
    database: str = "unknown"
    sqs: str = "disabled"


def money(value: Any) -> float:
    return round(float(value or 0), 6)
