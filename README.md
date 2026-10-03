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
├── api-gateway/          # nginx routes (monolith → new services)
├── docker-compose.yml    # local Postgres, MySQL, Redis, LocalStack, gateway
├── docs/                 # architecture & setup guides
├── event-schemas/        # async event contracts (SQS)
├── scripts/              # local-dev helpers
└── shared/               # auth libraries (added in Phase 2)
```

## Docs

- **[Architecture v2.0](docs/ARCHITECTURE.md)** — current design: 6 products, 5 deployables
- [Microservice architecture v1.0](docs/MICROSERVICE_ARCHITECTURE.md) — superseded, kept for reference
- [GitHub / GitLab setup](docs/GITHUB_SETUP.md)

## Related repos (same workspace)

| Repo | Role |
|------|------|
| `hekma_api` | Java monolith (extract 7 services) |
| `hekma_data_pipleline` | Python monolith (extract 7 services) |
| `TrialGPT/trailgpt` | MS-15 Trial Platform |
| `PHI_PII/PHI-PII` | MS-16 PHI/PII |
| `hekma_test_suit` | Integration tests |
