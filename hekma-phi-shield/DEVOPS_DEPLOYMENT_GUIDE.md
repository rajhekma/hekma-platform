# DevOps Deployment & Operations Guide: Privacy Detection & Security Service

**Service Name:** `privacy-detection-service`  
**Repository:** `HekmaAI/privacy-detection-service`  
**Architecture Pattern:** Dedicated Token Vault Tables inside Existing Application Database  
**Target Platform:** IONOS Managed Kubernetes / AWS ECS Fargate + Ingress Controller + Custom Domain  

---

## 1. Executive Summary & Architecture

The **Privacy Detection & Security Service (`privacy-detection-service`)** is a standalone, high-performance microservice that:
1. Runs fine-tuned **RoBERTa Token Classification** locally for demographic PII (sub-40ms latency).
2. Calls swappable **Clinical PHI Detectors** (OpenAI `gpt-4o-mini` / local model) for unstructured doctor notes.
3. Manages 4 dedicated **Token Vault Tables** (`token_mappings`, `policies`, `audit_logs`, `organizations`) directly inside your existing application database (`hekmaai`), using AES-256 / KMS encrypted surrogate mappings with zero cleartext at rest.

```
========================================================================================================================
                                     PRODUCTION TOPOLOGY
========================================================================================================================

  [ CLIENT / CONSUMER LAYER: hekma_data_pipleline ]
         │
         │  HTTPS 443 (Persistent Connection Pool)
         ▼
  [ DNS / Load Balancer (Public IP) ]
         │  Route: pii-phi.hekma.ai ──> Ingress / Load Balancer
         ▼
  [ Ingress Controller / ALB ]
         │  - Listens on HTTPS:443 (TLS Certificate for *.hekma.ai)
         │  - Forwards to Service / Target Group: Port 8080
         │  - Health Check: GET /ready (interval: 15s, timeout: 5s, threshold: 2)
         ▼
  [ Container Workload: privacy-detection-service (2 CPU / 4GB RAM) ]
         │  - Pre-warmed RoBERTa weights in /app/models
         │  - Endpoints: /predict, /mask, /anonymize, /restore, /ready, /metrics
         ▼
  [ EXISTING APPLICATION DATABASE (87.106.50.234:5432 / hekmaai) ]
  ┌──────────────────────────────────────────────────────────────────────────────────┐
  │  Application Tables (Fasten Health / EHR Data):                                  │
  │  • fastenhealth_patients, medications, conditions, ehr_summary_cache             │
  │                                                                                  │
  │  Dedicated Isolated Token Vault Tables:                                          │
  │  • token_mappings (Stores AES-256 encrypted surrogate mappings & HMAC index)     │
  │  • policies (Stores per-tenant PII handling policies)                            │
  │  • audit_logs (Immutable HIPAA access trail)                                     │
  │  • organizations (Tenant registry)                                               │
  └──────────────────────────────────────────────────────────────────────────────────┘
========================================================================================================================
```

---

## 2. Multi-Branch & Multi-Environment Matrix

| Branch | Environment | Custom Domain URL | Database Name (`DATABASE_URL`) | Service / Deployment Name |
|---|---|---|---|---|
| **`develop`** / **`Pii`** | `development` | `https://dev-pii-phi.hekma.ai` | `hekmaai` | `privacy-detection-service-dev` |
| **`demo`** | `demo` | `https://demo-pii-phi.hekma.ai` | `hekma_demo` | `privacy-detection-service-demo` |
| **`staging`** | `staging` | `https://staging-pii-phi.hekma.ai` | `hekma_staging` | `privacy-detection-service-staging` |
| **`main`** | `production` | `https://pii-phi.hekma.ai` | `hekma_prod` / `hekmaai` | `privacy-detection-service-production` |

---

## 3. Environment Variables & Secrets Reference

```bash
# ── Service & Domain Settings ─────────────────────────────────────────
ENVIRONMENT="production"                        # development | demo | staging | production
SERVICE_NAME="privacy-detection-service"
SERVICE_HOST="0.0.0.0"
SERVICE_PORT="8080"
CUSTOM_DOMAIN="https://pii-phi.hekma.ai"
LOG_LEVEL="INFO"                                # DEBUG | INFO | WARNING | ERROR

# ── Application Database (hekmaai) ────────────────────────────────────
STORAGE_BACKEND="postgresql"                    # postgresql (production/dev) | json (mock)
DATABASE_URL="postgresql+asyncpg://USER:PASSWORD@HOST:5432/hekmaai"
DB_POOL_SIZE="20"
DB_MAX_OVERFLOW="10"
DB_POOL_TIMEOUT="30"

# ── Cryptography & Encryption ─────────────────────────────────────────
ENCRYPTION_KEY="<base64-aes-256-key>" # AES-256 Master Key
KMS_ENABLED="false"
HMAC_SECRET="hekma-deterministic-salt-2026"

# ── Clinical PHI Detector ─────────────────────────────────────────────
PHI_DETECTOR_BACKEND="openai"                   # openai | local
OPENAI_API_KEY="<your-openai-api-key>"
OPENAI_PHI_MODEL="gpt-4o-mini"
OPENAI_TIMEOUT_SECONDS="45.0"

# ── Inter-Service Security ────────────────────────────────────────────
SERVICE_API_KEY="hekma_sec_live_..."            # Shared with hekma_data_pipleline for /internal/restore
ADMIN_API_KEY="hekma_admin_live_..."            # For Admin Console
```

---

## 4. Database Migration Runbook

The Token Vault tables are created safely inside the application database without affecting existing tables.

### Method A: Automated Shell CLI (Recommended)
Run against any target environment before deployment:
```bash
# Migrate Development:
./scripts/migrate_database.sh dev

# Migrate Demo:
./scripts/migrate_database.sh demo

# Migrate Production:
PROD_DATABASE_URL="postgresql+asyncpg://admin:SECRET@host:5432/hekma_prod" ./scripts/migrate_database.sh prod
```

### Method B: Cross-Platform Python CLI
```bash
python3 scripts/migrate_env.py --env dev
python3 scripts/migrate_env.py --env demo
python3 scripts/migrate_env.py --env prod --db-url "postgresql+asyncpg://admin:SECRET@host:5432/hekma_prod"
```

### Method C: Direct SQL DDL (For DBA)
Execute [`api/database/migrations/001_raw_ddl_init.sql`](file:///Users/deepak/projects/PHI-PII/api/database/migrations/001_raw_ddl_init.sql) in your database query editor. It is 100% idempotent (`CREATE TABLE IF NOT EXISTS`).

---

## 5. Health Checks & Observability Probes

Configure load balancer / Ingress with the following health checks:

| Probe | Endpoint | Expected Status | Purpose |
|---|---|---|---|
| **Liveness** | `GET /health` or `GET /healthz` | `200 OK` | Confirms web server process is responsive. |
| **Readiness** | `GET /ready` | `200 OK` | **Target Check:** Confirms RoBERTa model is warm in RAM and PostgreSQL connection pool is active. |
| **Metrics** | `GET /metrics` | `200 OK` | Prometheus metrics (`http_requests_total`, `http_request_duration_seconds`). |

---

## 6. Rollback Procedure

If a bad deployment occurs:
* **Kubernetes Rollback:** `kubectl rollout undo deployment/privacy-detection-service -n privacy-detection`
* **Schema Rollback:** `alembic downgrade -1`
* **Circuit Breaker:** Upstream callers in `hekma_data_pipleline` can disable PHI calls instantly via `PHI_SECURITY_ENABLED=false`.

---

## 7. Contacts & Escalation
* **Engineering Lead:** Hekma AI Security Team
* **Health Endpoint:** `https://pii-phi.hekma.ai/health`
* **Readiness Endpoint:** `https://pii-phi.hekma.ai/ready`
