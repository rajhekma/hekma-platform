# AI Usage

Patient-level record of AI token use and USD cost. Scan AI, Health Summary, TrialGPT, and later services emit one event per successful model call. This folder owns the ledger and the monitor.

It stays inside `hekma-platform`. It is not a separate deployable.

```
ai-usage/
├── backend/     # ingest, price catalog, query API, emitter library
└── frontend/    # monitoring dashboard, local only
```

| | |
|---|---|
| API | http://127.0.0.1:8090 |
| Dashboard | http://127.0.0.1:8091 |

```bash
# API (SQLite when Docker is not installed)
../scripts/local-dev.sh up

# Dashboard
cd frontend && python3 server.py
```

Other services do not store cost. They import `backend/hekma_ai_usage` (or the vendored copy in that repo) and POST `ai.usage.recorded`. The query API is `GET /v1/patients/{id}/ai-cost`.

- [Overview](docs/AI_USAGE_OVERVIEW.md) — problem, benefit, architecture choices
- [High-level design](docs/AI_USAGE_HLD.md) — components, APIs, pricing, how to emit
- [API reference](docs/AI_COST_ANALYTICS.md)
