# hekma-ai-usage

Patient-level record of AI token use and USD cost. Scan AI, Health Summary, TrialGPT, and later services emit one event per successful model call. This service owns the ledger.

Every service in `hekma-platform` uses this layout:

```
hekma-{service-name}/
├── Dockerfile
├── src/
│   ├── main.py
│   ├── api/            HTTP routes
│   ├── service/        business logic
│   └── repository/     database access
├── migrations/
├── tests/
└── openapi.yaml
```

This service also keeps a local dashboard in `frontend/` and design notes in `docs/`. Those are not part of the deployable.

| | |
|---|---|
| API | http://127.0.0.1:8090 |
| Dashboard | http://127.0.0.1:8091 |
| Contract | [openapi.yaml](openapi.yaml) |

```bash
# API (SQLite when Docker is not installed)
../scripts/local-dev.sh up

# Dashboard
cd frontend && python3 server.py

# Tests
pytest
```

Other services do not store cost. They copy `shared/hekma_ai_usage` and POST `ai.usage.recorded`. The query API is `GET /v1/patients/{id}/ai-cost`.

- [Overview](docs/AI_USAGE_OVERVIEW.md)
- [High-level design](docs/AI_USAGE_HLD.md)
- [API reference](docs/AI_COST_ANALYTICS.md)
