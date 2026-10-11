from datetime import datetime, timezone
from decimal import Decimal

from service.pricing import ModelPrice, price_tokens, select_price


PRICES = [
    ModelPrice(
        provider="openai",
        model="gpt-4o",
        input_usd_per_1m=Decimal("2.5"),
        output_usd_per_1m=Decimal("10"),
        effective_from=datetime(2024, 8, 1, tzinfo=timezone.utc),
    ),
    ModelPrice(
        provider="openai",
        model="gpt-4o-mini",
        input_usd_per_1m=Decimal("0.15"),
        output_usd_per_1m=Decimal("0.60"),
        effective_from=datetime(2024, 7, 18, tzinfo=timezone.utc),
    ),
    ModelPrice(
        provider="anthropic",
        model="claude-sonnet-4",
        input_usd_per_1m=Decimal("3"),
        output_usd_per_1m=Decimal("15"),
        effective_from=datetime(2025, 5, 22, tzinfo=timezone.utc),
    ),
]


def test_mini_does_not_inherit_gpt4o_price():
    at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    mini = select_price(PRICES, "openai", "gpt-4o-mini", at)
    full = select_price(PRICES, "openai", "gpt-4o", at)
    dated = select_price(PRICES, "openai", "gpt-4o-2024-08-06", at)
    assert mini.model == "gpt-4o-mini"
    assert full.model == "gpt-4o"
    assert dated.model == "gpt-4o"


def test_claude_alias_and_prefix():
    at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    price = select_price(PRICES, "claude", "claude-sonnet-4-6", at)
    assert price is not None
    assert price.model == "claude-sonnet-4"


def test_cost_math():
    at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    priced = price_tokens(
        PRICES,
        provider="openai",
        model="gpt-4o",
        prompt_tokens=1_000_000,
        completion_tokens=500_000,
        at=at,
    )
    assert priced.pricing_status == "priced"
    assert priced.input_cost_usd == Decimal("2.50000000")
    assert priced.output_cost_usd == Decimal("5.00000000")
    assert priced.cost_usd == Decimal("7.50000000")


def test_unknown_model_is_unpriced():
    priced = price_tokens(
        PRICES,
        provider="openai",
        model="mystery-model",
        prompt_tokens=100,
        completion_tokens=10,
    )
    assert priced.pricing_status == "unpriced"
    assert priced.cost_usd == Decimal("0")
