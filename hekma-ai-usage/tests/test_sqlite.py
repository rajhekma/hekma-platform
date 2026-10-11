from datetime import datetime, timezone
from uuid import uuid4

from service.ingest import IngestService
from service.query import assemble_patient_cost
from repository.sqlite import SqliteUsageRepository

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def test_sqlite_round_trip():
    repo = SqliteUsageRepository("sqlite:///:memory:")
    ingest = IngestService(repo)
    result = ingest.ingest(
        {
            "request_id": str(uuid4()),
            "occurred_at": NOW.isoformat(),
            "patient_id": "203664",
            "product": "scan_ai",
            "provider": "openai",
            "model": "gpt-4o",
            "prompt_tokens": 1000,
            "completion_tokens": 100,
        }
    )
    assert result.accepted is True
    assert result.pricing_status == "priced"

    cost = assemble_patient_cost(
        repo,
        tenant_id=1,
        patient_id="203664",
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )
    assert cost.totals.llm_calls == 1
    assert cost.by_provider[0].provider == "openai"
    repo.close()
