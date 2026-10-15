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
| **Platform Swagger** | **http://localhost:8099/docs** |
| AI Usage API | http://localhost:8090 |
| Patient Health | http://localhost:8010 |
| Scanner (Clinical AI) | http://localhost:8011 |
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
├── hekma-patient-health/ # S3: profile, EHR, FHIR, medications, account deletion
├── hekma-scanner/        # S4: clinical scan (MS-11) + EHR summary (MS-13)
├── hekma-trial-matching/ # S5: TrialGPT (copied from TrialGPT/trailgpt)
├── hekma-phi-shield/     # S6: PHI/PII detection (copied from PHI_PII/PHI-PII)
├── hekma-ai-usage/       # metering ledger (not subscriptions)
├── api-gateway/          # nginx routes (monolith → new services)
├── docker-compose.yml    # local Postgres, MySQL, Redis, LocalStack, gateway, AI usage
├── docs/                 # architecture & setup guides
├── event-schemas/        # async event contracts (SQS)
├── scripts/              # local-dev helpers
└── shared/               # libraries copied by services (hekma_ai_usage emitter)
```

Each business service is a `hekma-{service-name}/` folder with `Dockerfile`, `src/main.py`, `src/api/`, `src/service/`, `src/repository/`, `migrations/`, `tests/`, and `openapi.yaml`.

## Docs

**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) is the design to follow.**
- **[docs/DEPLOYMENT_AND_COMMUNICATION.md](docs/DEPLOYMENT_AND_COMMUNICATION.md)** — how `hekma-*` services deploy and talk (HTTP, SQS, gateway)
6 sellable products, 5 deployables. Do not build 16 microservices.

- **[docs/SERVICE_DECOMPOSITION.md](docs/SERVICE_DECOMPOSITION.md)** — how many services and why: 6 + gateway
- **[docs/NOTIFICATION_SERVICE_DESIGN.md](docs/NOTIFICATION_SERVICE_DESIGN.md)** — why it is a module in S2, not a 7th service
- **[docs/PLATFORM_API_STRATEGY.md](docs/PLATFORM_API_STRATEGY.md)** — every capability as engine + adapter: 6 sellable APIs
- **[docs/SELLABLE_API_DESIGN.md](docs/SELLABLE_API_DESIGN.md)** — the pattern worked through on Scan AI
- **[docs/TENANCY_DESIGN.md](docs/TENANCY_DESIGN.md)** — multi-org work, when you need it
- **[docs/MONETIZATION_ROADMAP.md](docs/MONETIZATION_ROADMAP.md)** — subscriptions, metering, tenancy: roadmap for leadership
- [docs/TENANCY_LEADERSHIP_OVERVIEW.md](docs/TENANCY_LEADERSHIP_OVERVIEW.md) — business-level, for leadership
- [hekma-identity-service/docs/IDENTITY_SERVICE.md](hekma-identity-service/docs/IDENTITY_SERVICE.md) — S1 Identity (Auth, RBAC, Multi-tenancy, Custom Roles, Introspection)
- [hekma-ctms-service/docs/CTMS_SERVICE.md](hekma-ctms-service/docs/CTMS_SERVICE.md) — S2 CTMS (Clinical study protocols, sites, events, adverse events)
- [hekma-appointment-service/docs/APPOINTMENT_SERVICE.md](hekma-appointment-service/docs/APPOINTMENT_SERVICE.md) — Appointment (Scheduling, calendar conflict detection, reminders)
- [hekma-notification-service/docs/NOTIFICATION_SERVICE.md](hekma-notification-service/docs/NOTIFICATION_SERVICE.md) — Notification & Support (Email, SMS, Push, In-App, Support Desk)
- [hekma-patient-health/README.md](hekma-patient-health/README.md) — S3 Patient Health (profile, EHR, FHIR, meds, deletion)
- [hekma-scanner/docs/SCANNER.md](hekma-scanner/docs/SCANNER.md) — S4 Clinical AI (scan + EHR summary)
- [hekma-ai-usage/docs/AI_USAGE.md](hekma-ai-usage/docs/AI_USAGE.md) — AI Usage: components, APIs, and diagrams
- [hekma-ai-usage/docs/AI_USAGE_OVERVIEW.md](hekma-ai-usage/docs/AI_USAGE_OVERVIEW.md) — why AI Usage exists and the architecture choices
- [hekma-ai-usage/docs/AI_USAGE_HLD.md](hekma-ai-usage/docs/AI_USAGE_HLD.md) — developer design: components, APIs, pricing, how to emit
- [hekma-ai-usage/docs/AI_COST_ANALYTICS.md](hekma-ai-usage/docs/AI_COST_ANALYTICS.md) — short API reference for the same service
- [GitHub setup](docs/GITHUB_SETUP.md)
- `docs/archive/` — rejected plans, reference only

## Related repos (same workspace)

| Repo | Role |
|------|------|
| `hekma_api` | Java monolith (extract 7 services) |
| `hekma_data_pipleline` | Python monolith (strangler) |
| `TrialGPT/trailgpt` | Source for `hekma-trial-matching` (also copied in platform) |
| `PHI_PII/PHI-PII` | Source for `hekma-phi-shield` (also copied in platform) |
| `hekma_test_suit` | Integration tests |
