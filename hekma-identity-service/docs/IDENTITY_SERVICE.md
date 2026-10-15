# Identity Service

**Service:** `hekma-identity-service` · **Port:** 8080 · **Role:** S1 in the platform (Core Authentication & Authorization)

This is the centralized authentication, authorization, regulatory consent, and tenant hierarchy authority for the Hekma platform.

It is **not** CTMS (clinical trials/studies), **not** Clinical AI, **not** Appointments/Scheduling, and **not** Patient Health (EHR/FHIR). All other services in the platform rely on this service to validate tokens, resolve user roles, verify fine-grained authorities, and enforce multi-tenant organization boundaries.

---

## What it supports

| Component | What the user sees | Owns |
|-----------|--------------------|------|
| **1 · Authentication & Session** | Login, signup, password reset, 2FA OTP | Dual-write Firebase Auth & PostgreSQL; OTP issuance & validation; session tokens |
| **2 · Hierarchical Multi-Tenancy** | Organizations, sponsor accounts, hospital sites | Materialized path tenant tree (`/top-org/sub-org`), tenant registration & lifecycle |
| **3 · RBAC, Authorities & Custom Roles** | Role assignments, custom roles, permission matrix | Fixed role hierarchy, 17+ granular authorities, tenant-scoped custom roles |
| **4 · Regulatory Consent & Clinical Profile** | Consent forms, legal e-signatures, clinical details | Immutable regulatory audit trail, patient profile metadata |
| **5 · Token Introspection** | Seamless SSO across all microservices | Inter-service `/internal/v1/auth/introspect` endpoint for downstream microservices |

---

## High-level architecture

```mermaid
flowchart TB
    APP[Web Portal / Mobile App] --> GW[API Gateway :9080]
    GW --> ID

    subgraph ID ["hekma-identity-service :8080"]
        FILTER[Firebase Auth Filter]
        AUTH[Authentication & 2FA]
        TENANT[Tenant Hierarchy Service]
        RBAC[RBAC & Custom Roles]
        CONSENT[Regulatory Consent]
        INTRO[Token Introspection]
        
        FILTER --> AUTH & TENANT & RBAC & CONSENT & INTRO
    end

    ID -->|User management & claims| FB[(Google Firebase Auth)]
    ID -->|Tables: identity_*| PG[(PostgreSQL · hekma_platform)]
    ID -->|Notifications / OTP SMS & Email| NOTIF[hekma-notification-service :8083]

    CTMS[hekma-ctms-service :8081] -->|Verify token & permissions| INTRO
    APPT[hekma-appointment-service :8082] -->|Verify token & permissions| INTRO
```

**Rule:** Identity is the single source of truth for who a user is, what organization they belong to, and what permissions they hold. Other services never validate passwords or assign tenant hierarchies.

---

## Request path (every call)

```mermaid
flowchart LR
    R[Request + Bearer Token] --> T{Firebase Token Valid?}
    T -->|no| U[401 Unauthorized]
    T -->|yes| S{User Active in Postgres?}
    S -->|no| D[401 User Deactivated]
    S -->|yes| A{Has Required Authority / Role?}
    A -->|no| F[403 Forbidden]
    A -->|yes| C[Execute Business Logic]
```

Public exceptions: `/api/v1/auth/login`, `/api/v1/auth/signup`, `/api/v1/auth/register-tenant`, `/api/v1/auth/otp/**`, `/swagger-ui/**`, `/v3/api-docs/**`.

---

## 1 · Authentication & Session Management

Manages registration, credential validation, and multi-factor authentication. Enforces dual-write consistency between Firebase Auth and PostgreSQL.

```mermaid
sequenceDiagram
    participant User
    participant API as AuthService
    participant FB as Firebase Auth
    participant PG as PostgreSQL
    participant Notif as Notification Service

    User->>API: POST /api/v1/auth/login (email + password)
    API->>FB: Verify credentials & issue ID token
    API->>PG: Load user, role & tenant
    alt Patient has 2FA enabled
        API->>PG: Generate OTP challenge
        API->>Notif: Send OTP via SMS/Email
        API-->>User: 200 (OTP Required, tokens withheld)
        User->>API: POST /api/v1/auth/otp/verify
        API-->>User: 200 (Access & Refresh Tokens)
    else Staff or 2FA disabled
        API-->>User: 200 (Access & Refresh Tokens)
    end
```

| API | Purpose |
|-----|---------|
| `POST /api/v1/auth/login` | Email/password login with conditional 2FA challenge |
| `POST /api/v1/auth/signup` | Public self-registration (Patients only) |
| `POST /api/v1/auth/register-tenant` | Self-service registration of top-level Sponsor / Site tenant |
| `POST /api/v1/auth/otp/verify` | Verify OTP code and complete login |
| `POST /api/v1/auth/password/reset-request` | Initiate password recovery flow |
| `POST /api/v1/auth/password/reset-confirm` | Complete password reset with secure token |

---

## 2 · Hierarchical Multi-Tenancy

Implements tree-based multi-tenancy using materialized paths (e.g. `/pfizer/site-nyc`). Sub-tenants inherit boundaries, and users are strictly isolated to their tenant subtree.

```mermaid
flowchart TD
    ROOT[Hekma Default Tenant]
    SPONSOR[Sponsor: Pfizer<br/>path: /pfizer]
    SITE1[Site: Mayo Clinic<br/>path: /pfizer/mayo]
    SITE2[Site: Mount Sinai<br/>path: /pfizer/mount-sinai]

    ROOT -.-> SPONSOR
    SPONSOR --> SITE1
    SPONSOR --> SITE2
```

| API | Purpose |
|-----|---------|
| `POST /api/v1/tenants/sub-tenants` | Create sub-tenant site under current sponsor (`subtenant:create`) |
| `GET /api/v1/tenants/my-tenant` | Retrieve tenant details and subscription tier |
| `PUT /api/v1/tenants/{tenantId}` | Update tenant branding and contact information (`tenant:update`) |
| `GET /api/v1/tenants` | List tenants within caller's subtree |

---

## 3 · RBAC, Authorities & Custom Roles

Combines high-level system roles with 17+ granular permissions and tenant-scoped custom roles.

```mermaid
flowchart TD
    subgraph Roles [Fixed System Roles]
        SA[SYSTEM_ADMIN · Global Root]
        A[ADMIN · Platform Operator]
        SP[SPONSOR · Trial Sponsor Lead]
        ST[SITE · Principal Investigator / Site Lead]
        PT[PATIENT · Clinical Subject]
    end

    subgraph CustomRoles [Tenant-Scoped Custom Roles]
        CR1[Clinical Monitor]
        CR2[Data Safety Board]
        CR3[Study Coordinator]
    end

    subgraph Authorities [Granular Permission Matrix]
        P1[study:read / study:create / study:update]
        P2[patient:read / patient:create / patient:update]
        P3[role:create / role:update / role:assign]
        P4[tenant:read / subtenant:create]
    end

    SP --> CR1 & CR3
    CR1 --> P1 & P2
```

| API | Purpose |
|-----|---------|
| `GET /api/v1/roles/authorities/catalogue` | Catalogue of all 17+ platform authorities |
| `GET /api/v1/roles/custom` | List custom roles defined in caller's tenant |
| `POST /api/v1/roles/custom` | Create a new custom role with authority subset (`role:create`) |
| `PUT /api/v1/roles/custom/{roleId}` | Modify custom role authorities (`role:update`) |
| `POST /api/v1/users/{userId}/custom-roles` | Assign custom roles to a staff member (`role:assign`) |

---

## 4 · Token Introspection (Inter-Service Contract)

Downstream microservices (CTMS, Appointment, Scanner) validate caller tokens by calling Identity's internal introspection endpoint:

```mermaid
sequenceDiagram
    participant Downstream as Downstream Service (CTMS / Appt)
    participant ID as Identity Service
    participant PG as PostgreSQL

    Downstream->>ID: POST /internal/v1/auth/introspect (Header: X-Hekma-Service-Key)
    ID->>PG: Validate Firebase token, role, tenant path, direct & custom authorities
    ID-->>Downstream: 200 { active: true, userId, role, tenantPath, authorities: [...] }
```

| API | Purpose |
|-----|---------|
| `POST /internal/v1/auth/introspect` | Internal high-throughput token validation for microservices |

---

## Where it sits on the platform

```mermaid
flowchart LR
    ID[1 Identity :8080] -->|Token Introspection| CTMS[2 CTMS :8081]
    ID -->|Token Introspection| APPT[Appointment :8082]
    ID -->|Token Introspection| PH[3 Patient Health :8010]
    ID -->|Token Introspection| SCAN[4 Scanner :8011]
    ID -->|OTP & Invites| NOTIF[Notification :8083]
```

| This service does | Another service does |
|-------------------|----------------------|
| Auth credentials, passwords, 2FA | CTMS: Studies, protocols, adverse events |
| Tenant hierarchy, materialized paths | Appointment: Booking, calendar conflict detection |
| System roles & custom roles | Notification: Email/SMS delivery, support tickets |
| Token introspection | Patient Health: EHR, FHIR stores, medications |

---

## Data stores

| Store | Used for |
|-------|----------|
| PostgreSQL (`hekma_platform`) | `identity_users`, `identity_tenants`, `identity_custom_roles`, `identity_otp_requests`, `identity_consents` |
| Google Firebase Auth | Secure password hashing, ID token minting, phone authentication |

---

## Run & Test

```powershell
cd hekma-identity-service
$env:JAVA_HOME="C:\Users\Acer_PTS\.jdks\graalvm-jdk-25"; $env:Path="$env:JAVA_HOME\bin;" + $env:Path
.\mvnw.cmd test
.\mvnw.cmd spring-boot:run
```
