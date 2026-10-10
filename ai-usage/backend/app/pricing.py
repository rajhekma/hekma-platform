"""Versioned LLM list-price lookup.

Matching order:
1. Exact (provider, model) at the event timestamp.
2. Longest catalog key that is a prefix of the model (so gpt-4o-mini does not
   steal gpt-4o's row when both exist; gpt-4o-2024-08-06 still maps to gpt-4o).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional, Sequence


MILLION = Decimal("1000000")
COST_QUANT = Decimal("0.00000001")

PROVIDER_ALIASES = {
    "openai": "openai",
    "azure": "openai",
    "azure_openai": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "google": "google",
    "gemini": "google",
    "groq": "groq",
}


@dataclass(frozen=True)
class ModelPrice:
    provider: str
    model: str
    input_usd_per_1m: Decimal
    output_usd_per_1m: Decimal
    effective_from: datetime
    effective_to: Optional[datetime] = None

    @property
    def version(self) -> str:
        start = self.effective_from.astimezone(timezone.utc).strftime("%Y-%m-%d")
        return f"{self.provider}:{self.model}@{start}"


@dataclass(frozen=True)
class PricedTokens:
    input_cost_usd: Decimal
    output_cost_usd: Decimal
    cost_usd: Decimal
    pricing_status: str
    price_version: Optional[str]


def normalize_provider(raw: str) -> str:
    key = (raw or "other").strip().lower()
    return PROVIDER_ALIASES.get(key, key or "other")


def _active(price: ModelPrice, at: datetime) -> bool:
    if price.effective_from > at:
        return False
    if price.effective_to is not None and price.effective_to <= at:
        return False
    return True


def select_price(
    prices: Sequence[ModelPrice],
    provider: str,
    model: str,
    at: datetime,
) -> Optional[ModelPrice]:
    provider = normalize_provider(provider)
    model = (model or "").strip()
    if not model:
        return None

    candidates = [
        p for p in prices
        if p.provider == provider and _active(p, at)
    ]
    exact = [p for p in candidates if p.model == model]
    if exact:
        return max(exact, key=lambda p: p.effective_from)

    prefix = [
        p for p in candidates
        if model.startswith(p.model) and (
            model == p.model or model[len(p.model):len(p.model) + 1] in ("-", ".", "/")
        )
    ]
    if not prefix:
        return None
    longest = max(len(p.model) for p in prefix)
    prefix = [p for p in prefix if len(p.model) == longest]
    return max(prefix, key=lambda p: p.effective_from)


def price_tokens(
    prices: Iterable[ModelPrice],
    *,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    at: Optional[datetime] = None,
) -> PricedTokens:
    when = at or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    matched = select_price(list(prices), provider, model, when)
    if matched is None:
        return PricedTokens(
            input_cost_usd=Decimal("0"),
            output_cost_usd=Decimal("0"),
            cost_usd=Decimal("0"),
            pricing_status="unpriced",
            price_version=None,
        )

    prompt = Decimal(max(int(prompt_tokens or 0), 0))
    completion = Decimal(max(int(completion_tokens or 0), 0))
    input_cost = (prompt / MILLION) * matched.input_usd_per_1m
    output_cost = (completion / MILLION) * matched.output_usd_per_1m
    total = input_cost + output_cost
    return PricedTokens(
        input_cost_usd=input_cost.quantize(COST_QUANT, rounding=ROUND_HALF_UP),
        output_cost_usd=output_cost.quantize(COST_QUANT, rounding=ROUND_HALF_UP),
        cost_usd=total.quantize(COST_QUANT, rounding=ROUND_HALF_UP),
        pricing_status="priced",
        price_version=matched.version,
    )
