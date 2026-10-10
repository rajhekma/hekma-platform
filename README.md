# hekma-platform

Shared infrastructure for the Hekma microservice migration: local dependencies, API gateway config, event schemas, and platform docs.

## Quick start

```bash
cp .env.example .env
./scripts/local-dev.sh up
```

| Service | URL / port |
|---------|------------|
| API Gateway (nginx) | http://localhost:9080 |
| AI Usage API | http://localhost:8090 |
| PostgreSQL | `localhost:5433` (user `hekma`, db `hekma_platform`) |
| MySQL (CTMS) | `localhost:3307` |
| Redis | `localhost:6379` |
| LocalStack (SQS) | `localhost:4566` |

Point existing monoliths at these hosts while you extract microservices:

- **Python** (`hekma_data_pipleline`): use Postgres/Redis connection strings from `.env.example`
- **Java** (`hekma_api`): use MySQL/Redis from `.env.example`

## Repository layout

```
hekma-platform/
├── ai-usage/             # patient AI usage: backend API + local dashboard
│   ├── backend/          # ingest, pricing, query API, emitter library
│   └── frontend/         # monitoring dashboard (local only)
├── api-gateway/          # nginx routes (monolith → new services)
├── docker-compose.yml    # local Postgres, MySQL, Redis, LocalStack, gateway, AI usage
├── docs/                 # architecture & setup guides
├── event-schemas/        # async event contracts (SQS)
├── scripts/              # local-dev helpers
└── shared/               # cross-service libraries (auth, later)
```

## Docs

**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) is the design to follow.**
6 sellable products, 5 deployables. Do not build 16 microservices.

- **[docs/SERVICE_DECOMPOSITION.md](docs/SERVICE_DECOMPOSITION.md)** — how many services and why: 6 + gateway
- **[docs/NOTIFICATION_SERVICE_DESIGN.md](docs/NOTIFICATION_SERVICE_DESIGN.md)** — why it is a module in S2, not a 7th service
- **[docs/PLATFORM_API_STRATEGY.md](docs/PLATFORM_API_STRATEGY.md)** — every capability as engine + adapter: 6 sellable APIs
- **[docs/SELLABLE_API_DESIGN.md](docs/SELLABLE_API_DESIGN.md)** — the pattern worked through on Scan AI
- **[docs/TENANCY_DESIGN.md](docs/TENANCY_DESIGN.md)** — multi-org work, when you need it
- **[docs/MONETIZATION_ROADMAP.md](docs/MONETIZATION_ROADMAP.md)** — subscriptions, metering, tenancy: roadmap for leadership
- [docs/TENANCY_LEADERSHIP_OVERVIEW.md](docs/TENANCY_LEADERSHIP_OVERVIEW.md) — business-level, for leadership
- [ai-usage/docs/AI_USAGE_OVERVIEW.md](ai-usage/docs/AI_USAGE_OVERVIEW.md) — why AI Usage exists and the architecture choices
- [ai-usage/docs/AI_USAGE_HLD.md](ai-usage/docs/AI_USAGE_HLD.md) — developer design: components, APIs, pricing, how to emit
- [ai-usage/docs/AI_COST_ANALYTICS.md](ai-usage/docs/AI_COST_ANALYTICS.md) — short API reference for the same service
- [GitHub setup](docs/GITHUB_SETUP.md)
- `docs/archive/` — rejected plans, reference only

## Related repos (same workspace)

| Repo | Role |
|------|------|
| `hekma_api` | Java monolith (extract 7 services) |
| `hekma_data_pipleline` | Python monolith (extract 7 services) |
| `TrialGPT/trailgpt` | MS-15 Trial Platform |
| `PHI_PII/PHI-PII` | MS-16 PHI/PII |
| `hekma_test_suit` | Integration tests |
