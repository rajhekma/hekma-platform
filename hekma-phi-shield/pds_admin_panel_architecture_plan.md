# PDS Admin Panel — Multi-Tenant Architecture Plan

> **Service:** `dev-pdsagent.hekma.ai/admin` (Privacy Detection Service Admin Portal)  
> **Goal:** Reorganize from scratch for multi-environment (DEV/QA/PROD), multi-tenant operation  
> **Constraint:** Admin panel is for **configure + monitor ONLY** — no data reversal/exposure

---

## 1. Current State Analysis

### 1.1 Architecture Overview

```mermaid
graph TB
    subgraph "Current Deployment"
        Browser["Browser"] -->|HTTPS| Ingress["K8s Ingress<br/>dev-pdsagent.hekma.ai"]
        Ingress --> Agent["pds-agent<br/>:8083 (Gunicorn+Uvicorn)"]
        Agent -->|"FastAPI /admin/*"| SPA["React SPA<br/>(Vite dist/)"]
        Agent -->|"/api/v1/*"| API["Admin API Router"]
        API --> PG["PostgreSQL<br/>87.106.50.234:5432/hekmaai"]
    end
    
    subgraph "Separate Service"
        PDS_API["pds-api :8080<br/>Detection Engine"] --> PG
    end
```

### 1.2 Current Pages & Features

| # | Page | Route | What It Does | Dynamic? | Issues Found |
|---|------|-------|-------------|----------|-------------|
| 1 | **Policy Config** | `/admin/policies` | Per-entity PII/PHI policy rules (anonymize/redact/ignore) + HIPAA/GDPR/PCI presets | ✅ Yes — reads/writes `policies` table via `/api/v1/orgs/{org_id}/policies` | Works dynamically per org |
| 2 | **Token Explorer** | `/admin/tokens` | Browse token_mappings, search, filter, export CSV | ✅ Yes — reads from `token_mappings` table, decrypts AES-256 | ⚠️ **EXPOSES `original_value`** (decrypted plaintext) + has **Restore functionality** that reveals PHI |
| 3 | **Audit Log** | `/admin/audit` | HIPAA audit trail of all anonymization/restore events | ✅ Yes — reads from `audit_logs` table | Works correctly |
| 4 | **Organization Settings** | `/admin/settings` | Org profile, API key management, retention rules, vault metrics | ✅ Yes — reads/writes `organizations` table | ⚠️ Hardcoded DB host in UI (`87.106.50.234:5432`), no env awareness |

### 1.3 Backend Stack

| Component | File | Description |
|-----------|------|-------------|
| Admin FastAPI App | [`admin_dashboard/backend/main.py`](file:///Users/deepak/projects/PHI-PII/admin_dashboard/backend/main.py) | 572 lines, serves both API + SPA |
| React SPA | [`admin_dashboard/frontend/src/`](file:///Users/deepak/projects/PHI-PII/admin_dashboard/frontend/src/) | Vite + React + TypeScript + Lucide icons |
| API Client | [`frontend/src/lib/api.ts`](file:///Users/deepak/projects/PHI-PII/admin_dashboard/frontend/src/lib/api.ts) | Axios with `X-Admin-Key` header auth |
| Org Context | [`frontend/src/context/OrgContext.tsx`](file:///Users/deepak/projects/PHI-PII/admin_dashboard/frontend/src/context/OrgContext.tsx) | React context for org/tenant selection |
| PostgreSQL Storage | [`api/storage/postgres.py`](file:///Users/deepak/projects/PHI-PII/api/storage/postgres.py) | Token, Policy, Audit, Org stores |
| DB Models | [`api/database/models.py`](file:///Users/deepak/projects/PHI-PII/api/database/models.py) | SQLAlchemy: `token_mappings`, `policies`, `audit_logs`, `organizations` |
| DB Connection | [`api/database/connection.py`](file:///Users/deepak/projects/PHI-PII/api/database/connection.py) | Async SQLAlchemy engine with pool |
| Settings | [`api/config/settings.py`](file:///Users/deepak/projects/PHI-PII/api/config/settings.py) | Pydantic BaseSettings from `.env` |

### 1.4 Current Multi-Tenancy (What Already Exists)

```
✅ org_id column in token_mappings, policies, audit_logs
✅ OrgContext in React (tenant selector dropdown)
✅ PostgresOrgStore auto-discovers tenants from token_mappings
✅ API key rotation per org (SHA-256 hashed)
✅ Per-org policy configuration
✅ "All Tenants" global view
```

---

## 2. Critical Security Gaps (Must Fix)

> [!CAUTION]
> These are HIPAA/SOC-2 violations that must be addressed before production.

### 🔴 Gap 1: Token Explorer Exposes Original PHI Values

**Current behavior:** The Token Explorer decrypts `original_value` (AES-256) and sends cleartext back to the browser via `/api/v1/tokens/search`.

```
Line 165 in postgres.py: decrypted_orig = self._crypto.decrypt(row.original_value)
Line 285 in main.py:     "original_value": m.original_value,  ← cleartext PHI
Line 526 in TokenExplorer.tsx: <span>{mapping.original_value}</span>  ← shown in UI
```

**Fix:** Remove `original_value` from all admin API responses. Token Explorer should show:
- `tokenized_value` (surrogate token like `PERSON_9fa41f72`)
- `entity_type`, `policy_applied`, `confidence`, timestamps
- **Never** the decrypted original

### 🔴 Gap 2: Restore Endpoint Accessible from Admin UI

**Current behavior:** `/api/v1/tokens/restore` allows admins to reverse tokens → cleartext via the UI.

**Fix:** Remove the restore UI entirely. The restore API should only be callable programmatically by authorized microservices (e.g., the lambda pipeline), not from the admin portal.

### 🟡 Gap 3: Hardcoded Admin API Key

```python
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "admin-dev-key-change-in-production")
```
Frontend sends this as `X-Admin-Key`. No user-level auth, no session management, no RBAC.

### 🟡 Gap 4: Single Database for All Environments

Currently DEV, QA, and PROD would all point to the same `87.106.50.234:5432/hekmaai`. The admin panel needs to be environment-aware.

### 🟡 Gap 5: No Dashboard / Overview Page

Landing goes straight to `/policies`. No summary dashboard showing system health, environment status, or aggregate metrics.

---

## 3. Multi-Tenant Architecture Plan

### 3.1 Tenant Model

```mermaid
graph TD
    subgraph "Admin Portal (Single Deployment)"
        Portal["Admin SPA<br/>React + Vite"]
    end
    
    subgraph "Environment Layer"
        Portal -->|ENV_NAME from configMap| API["Admin API<br/>(FastAPI)"]
        API -->|"DATABASE_URL from env"| DB_DEV["DEV PostgreSQL"]
        API -->|"DATABASE_URL from env"| DB_QA["QA PostgreSQL"]
        API -->|"DATABASE_URL from env"| DB_PROD["PROD PostgreSQL"]
    end
    
    subgraph "Tenant Isolation (Per DB)"
        DB_DEV --> T1["org_id: default-org"]
        DB_DEV --> T2["org_id: 203674"]
        DB_DEV --> T3["org_id: hospital-xyz"]
    end
```

### 3.2 Environment Strategy

> [!IMPORTANT]
> **Approach: One Admin Panel Deployment Per Environment — NOT one panel managing all environments.**

**Rationale:**
- Each environment (DEV/QA/PROD) has its own PostgreSQL with different credentials, encryption keys, and data
- Cross-environment DB access from a single deployment is a security risk (PROD credentials shouldn't be in DEV pods)
- The admin panel already gets its `DATABASE_URL` from K8s configMap/secrets — this pattern naturally isolates environments
- The panel should **show which environment it's running in** but not switch between them

**Implementation:**
```yaml
# K8s configMap per environment
# DEV: dev-pdsagent.hekma.ai/admin
ENVIRONMENT: "development"
DATABASE_URL: "postgresql+asyncpg://admin:***@dev-db:5432/hekmaai"

# QA: qa-pdsagent.hekma.ai/admin  
ENVIRONMENT: "qa"
DATABASE_URL: "postgresql+asyncpg://admin:***@qa-db:5432/hekmaai"

# PROD: pdsagent.hekma.ai/admin
ENVIRONMENT: "production"
DATABASE_URL: "postgresql+asyncpg://admin:***@prod-db:5432/hekmaai"
```

**Frontend display:** The header should show an environment badge:
- 🟢 `DEV` (green) for development
- 🟡 `QA` (amber) for staging
- 🔴 `PROD` (red, prominent) for production

### 3.3 Tenant Organization & Onboarding

#### Current State
Tenants are auto-discovered from `token_mappings.org_id` (e.g., patient IDs like `203674` appear automatically). This is good but needs formal structure.

#### Proposed Tenant Lifecycle

```mermaid
flowchart LR
    A["1. Auto-Discovery<br/>org_id appears in<br/>token_mappings"] --> B["2. Org Created<br/>on-demand in<br/>organizations table"]
    B --> C["3. Admin Configures<br/>Name, Email, Policies<br/>Retention Rules"]
    C --> D["4. API Key Issued<br/>For programmatic<br/>access"]
    D --> E["5. Ongoing<br/>Monitor, Audit<br/>Policy Updates"]
```

**No manual tenant creation needed** — tenants materialize when the data pipeline sends data scoped to an `org_id`. The admin panel then lets you:
1. Name the tenant (e.g., "Mount Sinai Hospital" instead of "203674")
2. Set compliance policies (HIPAA preset)
3. Configure retention rules
4. Issue API keys for that tenant's services

---

## 4. Proposed Admin Panel Structure

### 4.1 New Page Hierarchy

```
/admin/
├── /dashboard          ← NEW: Overview + System Health
├── /policies           ← KEEP: Per-entity PII/PHI policy rules
├── /tokens             ← REFACTOR: Token Vault Monitor (NO original values)
├── /audit              ← KEEP: HIPAA Audit Trail
├── /tenants            ← RENAME from /settings: Tenant Management
│   └── /:orgId         ← Individual tenant detail
└── /system             ← NEW: System Config & Environment Info
```

### 4.2 Page Details

#### 📊 Dashboard (NEW — Landing Page)

| Section | Content |
|---------|---------|
| Environment Badge | DEV / QA / PROD with color coding |
| System Health | DB connectivity, API latency, last sync timestamp |
| Aggregate Stats | Total tokens, total tenants, total policies, total audit events |
| Recent Activity Feed | Last 10 audit log entries across all tenants |
| Token Volume Chart | Tokens created over time (last 7/30 days) |
| Top Entity Types | Bar chart of most anonymized entity types |

#### 🛡️ Policy Config (KEEP — Minor Tweaks)

- Already works well
- Add: Bulk apply preset across ALL tenants
- Add: Policy diff view (show what changed before saving)

#### 🔐 Token Vault Monitor (REFACTORED — Security Hardened)

**What stays:**
- Token search/filter by entity type, policy, date range
- Pagination, CSV export
- Stats cards (total, by entity type, by policy)

**What gets REMOVED:**
- ❌ `original_value` column — never sent from API
- ❌ Restore button / restore modal — removed entirely
- ❌ Eye icon to reveal values — removed

**What gets ADDED:**
- ✅ Token metadata only: `tokenized_value`, `entity_type`, `policy_applied`, `confidence`, `created_at`, `expires_at`
- ✅ Token lifecycle status (Active / Expired / Purged)
- ✅ Aggregate charts (tokens by type, by policy)

#### 📋 Audit Log (KEEP — Minor Enhancement)

- Add: Export to PDF/CSV for compliance reporting
- Add: Real-time auto-refresh toggle
- Add: Severity/criticality indicators

#### 🏢 Tenant Management (REFACTORED from /settings)

- Tenant list with search
- Per-tenant detail view (profile, policies, token stats, audit log)
- Tenant onboarding wizard for new organizations
- API key management with rotation
- Retention policy configuration

#### ⚙️ System Settings (NEW)

| Setting | Source | Editable? |
|---------|--------|-----------|
| Environment | `ENVIRONMENT` env var | Read-only |
| Database Host | `DATABASE_URL` (masked) | Read-only |
| Encryption Status | KMS / Fernet | Read-only |
| Storage Backend | `STORAGE_BACKEND` | Read-only |
| PHI Detector | `PHI_DETECTOR_BACKEND` | Read-only |
| Service Version | Build metadata | Read-only |

---

## 5. Authentication & RBAC (Phase 2)

### 5.1 Short-Term (Phase 1 — Now)

Keep the `X-Admin-Key` approach but:
- Generate a unique key per environment
- Store as K8s secret, inject via env
- Add rate limiting

### 5.2 Long-Term (Phase 2)

```mermaid
graph TD
    User["Admin User"] -->|"Login"| Auth["Auth Provider<br/>(Keycloak / Auth0)"]
    Auth -->|"JWT Token"| Portal["Admin Portal"]
    Portal -->|"Bearer Token"| API["Admin API"]
    API -->|"Check Role"| RBAC["Role-Based Access"]
    
    RBAC --> R1["SUPER_ADMIN<br/>All tenants, all actions"]
    RBAC --> R2["TENANT_ADMIN<br/>Single tenant, configure"]
    RBAC --> R3["AUDITOR<br/>Read-only audit access"]
    RBAC --> R4["VIEWER<br/>Dashboard only"]
```

---

## 6. Backend API Changes

### 6.1 New Endpoints

```python
# Dashboard
GET  /api/v1/dashboard/stats          # Aggregate metrics
GET  /api/v1/dashboard/health          # System health
GET  /api/v1/dashboard/activity        # Recent activity feed

# System
GET  /api/v1/system/info               # Environment, version, config (sanitized)

# Environment
GET  /api/v1/environment               # Returns { name, database_host_masked, ... }
```

### 6.2 Modified Endpoints

```diff
# Token Search — REMOVE original_value from response
POST /api/v1/tokens/search
- "original_value": m.original_value,
+ # original_value field REMOVED entirely

# Token Restore — REMOVE from admin portal (keep for service-to-service)
- POST /api/v1/tokens/restore          # Remove from admin_router
+ # Only accessible via pds-api service with service API key, not admin key
```

### 6.3 New API for Dashboard

```python
@admin_router.get("/api/v1/dashboard/stats")
async def dashboard_stats():
    """Aggregate metrics across all tenants."""
    return {
        "environment": settings.ENVIRONMENT,
        "total_tenants": ...,
        "total_tokens": ...,
        "total_policies": ...,
        "total_audit_events": ...,
        "tokens_last_24h": ...,
        "db_healthy": await check_db_health(),
    }

@admin_router.get("/api/v1/system/info")
async def system_info():
    """Sanitized system configuration."""
    return {
        "environment": settings.ENVIRONMENT,
        "database_host": mask_db_url(settings.DATABASE_URL),
        "storage_backend": settings.STORAGE_BACKEND,
        "phi_detector": settings.PHI_DETECTOR_BACKEND,
        "encryption": "AES-256-Fernet" if not settings.KMS_ENABLED else "AWS-KMS",
        "version": os.getenv("BUILD_VERSION", "dev"),
    }
```

---

## 7. Implementation Phases

### Phase 1: Security Hardening + Dashboard (1-2 weeks)

| # | Task | Priority |
|---|------|----------|
| 1 | **Remove `original_value` from token search API response** | 🔴 Critical |
| 2 | **Remove restore UI from Token Explorer** | 🔴 Critical |
| 3 | **Remove restore endpoint from admin router** (keep in pds-api) | 🔴 Critical |
| 4 | Add environment badge to header (read from `/api/v1/system/info`) | 🟡 High |
| 5 | Build Dashboard page with aggregate stats | 🟡 High |
| 6 | Remove hardcoded DB host from OrgSettings UI | 🟢 Medium |
| 7 | Add `/api/v1/dashboard/stats` + `/api/v1/system/info` endpoints | 🟡 High |

### Phase 2: Tenant Management Overhaul (1-2 weeks)

| # | Task | Priority |
|---|------|----------|
| 8 | Rename `/settings` → `/tenants` with proper tenant list view | 🟡 High |
| 9 | Per-tenant detail page with tabs (Profile, Policies, Tokens, Audit) | 🟡 High |
| 10 | Tenant onboarding flow (create org, assign preset, issue key) | 🟢 Medium |
| 11 | Bulk policy application across tenants | 🟢 Medium |

### Phase 3: Polish & Auth (2-3 weeks)

| # | Task | Priority |
|---|------|----------|
| 12 | System Settings page (read-only environment info) | 🟢 Medium |
| 13 | RBAC with JWT authentication | 🟡 High |
| 14 | Audit log PDF/CSV export | 🟢 Medium |
| 15 | Token volume charts (time series) | 🟢 Medium |
| 16 | Real-time WebSocket for activity feed | 🔵 Low |

---

## 8. Database Schema — No Changes Needed

The current schema already supports everything:

| Table | Multi-Tenant? | Notes |
|-------|--------------|-------|
| `token_mappings` | ✅ `org_id` column | Already tenant-partitioned |
| `policies` | ✅ `(org_id, entity_type)` PK | Already per-tenant |
| `audit_logs` | ✅ `org_id` column | Already per-tenant |
| `organizations` | ✅ `org_id` PK | Tenant registry |

> [!NOTE]
> No schema migration needed. The current DB design is already multi-tenant. The work is purely in the API and frontend layers.

---

## 9. Deployment Model

```
Same Docker image → different K8s configMaps per environment

┌──────────────────────────────────────────────────┐
│                Docker Image (pds-agent)           │
│  admin_dashboard/backend/main.py (FastAPI)        │
│  admin_dashboard/frontend/dist/ (React SPA)       │
│  api/ (shared storage, crypto, models)            │
└──────────────────────────────────────────────────┘
        │               │               │
   DEV values.yaml  QA values.yaml  PROD values.yaml
   ─────────────    ─────────────   ──────────────
   ENVIRONMENT=dev  ENVIRONMENT=qa  ENVIRONMENT=prod
   DATABASE_URL=... DATABASE_URL=.. DATABASE_URL=...
   ADMIN_API_KEY=.. ADMIN_API_KEY=. ADMIN_API_KEY=...
   ENCRYPTION_KEY=. ENCRYPTION_KEY= ENCRYPTION_KEY=..
```

---

## 10. Summary of What Changes

### Frontend Changes
```diff
  /admin/
+ ├── /dashboard         ← NEW landing page
  ├── /policies          ← Keep as-is
- ├── /tokens            ← REFACTOR: remove original_value + restore
+ ├── /tokens            ← Token Vault Monitor (metadata only)
  ├── /audit             ← Keep + minor enhancements
- ├── /settings          ← REFACTOR: rename + split
+ ├── /tenants           ← Tenant Management Hub
+ └── /system            ← NEW: Read-only system info
```

### Backend Changes
```diff
  # admin_dashboard/backend/main.py
- POST /api/v1/tokens/restore          ← REMOVE from admin router
+ GET  /api/v1/dashboard/stats         ← NEW
+ GET  /api/v1/system/info             ← NEW
+ GET  /api/v1/environment             ← NEW
  
  # Token search response
- "original_value": m.original_value   ← REMOVE field
+ # field not included
```

### Security Changes
```diff
- Token Explorer shows decrypted PHI    → Removed
- Restore button in admin UI            → Removed  
- Hardcoded DB host in frontend         → Read from API
- Single API key for all environments   → Per-environment keys
```

> [!TIP]
> **Zero database schema changes needed.** All improvements are API + UI layer. This means we can ship incrementally without any migration risk.
