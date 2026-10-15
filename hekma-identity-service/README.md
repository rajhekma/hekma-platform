# Hekma Identity Service (`hekma-identity-service`)

The **Hekma Identity Service** is the central authentication, authorization, user lifecycle management, and consent auditing microservice for the **Hekma Platform**.

It implements a hybrid identity architecture that synchronizes **Google Firebase Authentication** (identity provider, JWT ID tokens, and custom claims) with **PostgreSQL** (clinical user profiles, tenant relations, and audit records), protected by compensating rollbacks for transactional consistency.

---

## Core Features

- **Hybrid Authentication & Dual-Write Consistency**: Integrates Firebase Auth with PostgreSQL clinical profiles, utilizing compensating rollbacks to guarantee data integrity across distributed state.
- **Role-Based Access Control (RBAC)**: Five roles (`SYSTEM_ADMIN`, `ADMIN`, `SPONSOR`, `SITE`, `PATIENT`). Every protected request is authenticated with a Firebase ID token; role and tenant are loaded from PostgreSQL and enforced per endpoint.
- **Per-User Authorities**: Twelve fine-grained authorities (e.g. `patient:read`, `user:invite`, `subtenant:create`) per SPONSOR/SITE user, granted never beyond the grantor's own, with staff invitations, `/api/v1/me` and an append-only audit log of privileged actions.
- **Hierarchical Multi-Tenancy**: Organizations self-register as SPONSOR or SITE tenants and create sub-tenants of any type at any depth; users see their own tenant and its sub-tenants only.
- **Password Management via the API**: Passwords are created, changed, reset (OTP-verified) and validated only through this service and stored only in Firebase, with a shared strength policy.
- **Admin Delegation & Hierarchy**: Automated bootstrap for `SYSTEM_ADMIN` on startup, with dedicated administrative APIs to invite and provision `ADMIN` users.
- **Patient Onboarding & 2FA**: Dedicated patient profile registration with mandatory regulatory consent tracking (terms, privacy, health data), and optional Two-Factor Authentication (2FA) via OTP.
- **Multi-Mode OTP Verification**: Generation, transmission, and verification of 6-digit OTP codes via Email and SMS, backed by rate limiting and lockout protection, integrated with `hekma-notification-service`.
- **User Lifecycle & Soft Deletion**: Hierarchical user activation/deactivation (`isActive`), status transitions, and audit-compliant soft deletion via Hibernate `@SQLRestriction`.
- **GraphQL & REST Dual Exposure**: Unified REST endpoints for transactional operations alongside a flexible GraphQL schema for administrative user search and role filtering.

---

## Tech Stack & Dependency Versions

| Component / Tool | Technology | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Language** | Java (GraalVM / OpenJDK) | `25` (Release `21`) | Primary runtime |
| **Framework** | Spring Boot | `4.1.1` | Core application framework |
| **Security** | Spring Security | `7.1.1` | Security filters & stateless authentication |
| **Identity Provider** | Firebase Admin SDK | `9.4.3` | User sync, JWT token issuance & claims |
| **Query Engine** | Spring for GraphQL / GraphQL Java | `2.0.5` / `25.0` | Flexible administrative user querying |
| **API Documentation** | SpringDoc OpenAPI (Swagger UI) | `3.1.0` (UI `5.32.11`) | Interactive REST documentation & testing |
| **Persistence** | Spring Data JPA / Hibernate | `4.1.1` | Relational data access & ORM |
| **Database** | PostgreSQL / PostgreSQL Driver | `18` / Runtime | Primary persistent store |
| **Migrations** | Flyway Database PostgreSQL | `12.4.0` | Versioned schema migrations |
| **Code Generation**| Project Lombok | Latest | Boilerplate elimination |
| **Test Database** | H2 Database Engine | In-Memory | Unit & integration test execution |

---

## Quick Start & Setup

### Prerequisites
- Java 21 or Java 25 installed
- PostgreSQL instance running (default database: `hekma-identity`)
- Google Firebase Service Account credentials **and** Web API key (or enable mock mode for local testing)

### Key Environment Variables
| Variable | Required | Purpose |
| :--- | :--- | :--- |
| `FIREBASE_MOCK_MODE` | No (default `false`) | In-memory Firebase for local development |
| `FIREBASE_CREDENTIALS_PATH`, `FIREBASE_WEB_API_KEY` | Yes, unless mock mode | Firebase Admin SDK and password sign-in |
| `NOTIFICATION_SERVICE_KEY` | Yes | Shared key for `hekma-notification-service` |
| `APP_CORS_ALLOWED_ORIGINS` | No (default `http://localhost:3000`) | Allowed browser origins |
| `APP_EXPOSE_API_DOCS`, `GRAPHIQL_ENABLED` | No (default `false`) | Swagger/OpenAPI and GraphiQL |
| `OTP_CONSOLE_ECHO` | No (default `false`) | Print OTPs to the console (local development only) |

### Run Locally
```bash
# Clone the repository
git clone https://github.com/HekmaAI/hekma-identity-service.git
cd hekma-identity-service

# Build and run with Maven Wrapper
./mvnw spring-boot:run
```

The service will start on port `8080` by default.

---

## Interactive Documentation

Detailed API payloads, parameter schemas, and real-time execution are available directly through interactive UI tools (enable with `APP_EXPOSE_API_DOCS=true` / `GRAPHIQL_ENABLED=true`; protected endpoints need `Authorization: Bearer <idToken>`):

- **Swagger UI (REST API)**: [http://localhost:8080/swagger-ui.html](http://localhost:8080/swagger-ui.html)
- **OpenAPI 3 JSON Specification**: [http://localhost:8080/v3/api-docs](http://localhost:8080/v3/api-docs)
- **GraphiQL Explorer (GraphQL API)**: [http://localhost:8080/graphiql](http://localhost:8080/graphiql)
