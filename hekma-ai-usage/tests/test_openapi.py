from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import yaml

from config import Settings
from main import create_app
from repository.store import InMemoryUsageRepository
from service.pricing import ModelPrice

CONTRACT = Path(__file__).resolve().parents[1] / "openapi.yaml"


def _app():
    repo = InMemoryUsageRepository(
        [
            ModelPrice(
                provider="openai",
                model="gpt-4o",
                input_usd_per_1m=Decimal("1"),
                output_usd_per_1m=Decimal("1"),
                effective_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
            )
        ]
    )
    return create_app(
        repo=repo,
        settings=Settings(ai_usage_sqs_enabled=False),
        start_sqs=False,
    )


def test_checked_in_openapi_matches_the_app():
    spec = _app().openapi()
    checked_in = yaml.safe_load(CONTRACT.read_text())
    assert checked_in == spec


def test_public_contract_does_not_rely_on_the_gateway_for_ingest():
    paths = set(_app().openapi()["paths"])
    assert "/internal/v1/ai-usage/events" in paths
    assert "/v1/patients/{patient_id}/ai-cost" in paths
