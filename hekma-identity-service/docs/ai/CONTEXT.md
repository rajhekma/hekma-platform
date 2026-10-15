# Hekma Identity Service — AI Project Context

## Project
- **Name**: `hekma-identity-service`
- **Description**: Centralized authentication, authorization, clinical user profile management, and regulatory consent microservice for the Hekma Platform.
- **Business/Domain Purpose**: Serves as the security and identity foundation for a decentralized clinical trial (DCT) ecosystem. It orchestrates clinical trial participant profiles (`PATIENT`), trial investigators (`SITE`), pharmaceutical research sponsors (`SPONSOR`), and system operators (`ADMIN`, `SYSTEM_ADMIN`) under strict HIPAA, GDPR, and regulatory compliance standards.

---

## Technology Stack
- **Language & Runtime**: Java 25 (Compiler target release: Java 21; requires JDK 21 or 25, e.g. GraalVM JDK 25).
- **Framework**: Spring Boot `4.1.1` (Spring Framework 7.x, Spring Security `7.1.1`, Spring Data JPA `4.1.1`).
- **Persistence & Database**: PostgreSQL 18 (production/dev); H2 In-Memory Database (`MODE=PostgreSQL`) for automated testing.
- **Database Migrations**: Flyway Database Migration `12.4.0` (`flyway-database-postgresql`).
- **Identity Provider (IdP)**: Google Firebase Admin SDK `9.4.3` (with Google STS for token refresh); local mock mode available via `firebase.mock-mode=true`.
- **Query & API Layer**: Spring Boot Web MVC, Spring for GraphQL `2.0.5` (GraphQL Java `25.0`), SpringDoc OpenAPI `3.1.0` (Swagger UI).
- **Build Tool**: Maven (`mvnw` / `mvnw.cmd` wrapper).
- **Code Generation & Utilities**: Project Lombok, Jakarta Validation (`spring-boot-starter-validation`).
- **Major External Integrations**:
  - **Google Firebase Auth & Google STS**: Credential management, custom claims, and OAuth2 token refresh.
  - **Hekma Notification Service (`hekma-notification-service`)**: Inter-service REST client dispatching email, SMS OTPs, and welcome notifications.

---

## Architecture Summary
- **Overall Pattern**: Domain-Driven Design (DDD) layered microservice architecture (Controller -> Service -> Repository/Integration -> Database/External APIs).
- **Dual-Write Consistency**: Orchestrates user creation between Google Firebase Auth and PostgreSQL using a Saga pattern with compensating rollbacks. If local database persistence or OTP dispatch fails, the user is deleted from Firebase Auth to prevent orphan state.
- **Authentication & Authorization**:
  - Stateless authentication: every protected request carries a Firebase ID token (`Authorization: Bearer`), verified with revocation checks; role/tenant are loaded from PostgreSQL (`HekmaPrincipal`), never from client headers. Passwords are created, changed, reset and validated only via the Java API and stored only in Firebase (`@StrongPassword` policy).
  - Per-user authorities for SPONSOR/SITE users (12 keys such as `patient:read`), scoped to the tenant subtree, grant ≤ own, audited.
  - Strict hierarchical Role-Based Access Control (RBAC): `SYSTEM_ADMIN` (immutable root) > `ADMIN` (operational admin) > `SPONSOR` / `SITE` / `PATIENT` (public self-registration).
  - Conditional Two-Factor Authentication (2FA): Patients with `twoFactorEnabled == true` require OTP verification before receiving authentication tokens.
- **Inter-Service Communication**: Synchronous HTTP/JSON REST client (`NotificationServiceClient`) secured by shared service API keys (`X-Hekma-Service-Key`).
- **Data Isolation & Deletion**: Relational soft-deletion enforced globally across JPA queries using Hibernate `@SQLRestriction("is_deleted = false")`. All entities extend `BaseAuditEntity` for automatic timestamps and optimistic locking.

---

## Repository Structure
```text
hekma-identity-service/
├── .mvn/wrapper/                  # Maven wrapper binaries and configuration
├── docs/                          # Comprehensive technical documentation & plans
│   ├── ai/                        # AI-specific progressive disclosure context system
│   │   ├── services/              # Service-level context files (identity.md)
│   │   ├── ARCHITECTURE.md        # Detailed component architecture & data flow
│   │   ├── CONTEXT.md             # This entry point
│   │   ├── CONVENTIONS.md         # Coding, error handling, and testing standards
│   │   ├── CURRENT.md             # Current task focus, completed work & blockers
│   │   └── DECISIONS.md           # Architecture Decision Records (ADRs)
│   ├── API_DOCUMENTATION.md       # Full REST & GraphQL endpoint specifications
│   ├── ARCHITECTURE.md            # Deep architecture design & sequence flows
│   ├── DATABASE.md                # PostgreSQL schema definitions & ERD
│   ├── DEVELOPMENT_LOG.md         # Chronological project development log
│   ├── MULTITENANCY_PLAN.md       # Multi-tenant architectural proposal
│   ├── RBAC_PLAN.md               # RBAC plan (all phases implemented)
│   └── PROJECT_CONTEXT.md         # Business domain requirements & clinical workflows
├── src/main/java/com/hekma/identity/
│   ├── config/                    # Security, OpenAPI, JPA auditing & startup initializers
│   ├── multitenancy/              # TenantContext & TenantFilter (tenant from authenticated principal)
│   ├── security/                  # FirebaseAuthenticationFilter, HekmaPrincipal, AuthEmails
│   ├── controller/                # REST API controllers & GraphQL controllers
│   ├── domain/                    # JPA entities, enums (Role, UserStatus) & OTP domain
│   ├── dto/                       # Request/Response Data Transfer Objects & OTP payloads
│   ├── exception/                 # Custom domain exceptions & GlobalExceptionHandler
│   ├── firebase/                  # Firebase Admin SDK & Google STS integrations
│   ├── notification/              # Inter-service client for hekma-notification-service
│   ├── repository/                # Spring Data JPA repositories
│   └── service/                   # Core business logic (Auth, OTP, UserManagement, UserQuery)
├── src/main/resources/
│   ├── db/migration/              # Flyway SQL migration scripts (V1 through V8)
│   ├── graphql/                   # GraphQL schemas (schema.graphqls)
│   └── application.yml            # Main application configuration
├── src/test/                      # Integration and unit tests (H2 in-memory DB)
├── AGENTS.md                      # Primary instruction manual for all AI coding agents
├── CLAUDE.md                      # Claude-specific entry point to shared context
├── pom.xml                        # Maven dependency and build configuration
└── README.md                      # High-level developer onboarding and overview
```

---

## Important Rules for AI Agents
1. **Strict Plan-Only Boundary**: When asked to prepare a plan, produce ONLY planning documentation. NEVER modify application code, entities, migrations, or run destructive tasks without explicit user approval.
2. **Strict Commit & Push Restriction**: NEVER execute `git commit` or `git push` unless explicitly asked in the user's prompt. All modifications must remain uncommitted in the working tree.
3. **Source Code is Ground Truth**: If documentation contradicts actual source code or Flyway migrations, treat the codebase as the ultimate source of truth and propose documentation corrections.
4. **Zero Secret Policy**: Never commit, log, or document secrets, service account credentials, API keys, or private user passwords.
5. **Runtime Prerequisite**: JDK 21 or 25 must be active when running Maven builds/tests:
   ```powershell
   $env:JAVA_HOME="C:\Users\Acer_PTS\.jdks\graalvm-jdk-25"; $env:Path="$env:JAVA_HOME\bin;" + $env:Path
   .\mvnw.cmd test
   ```
6. **Auditing Invariant**: Every JPA entity MUST extend `BaseAuditEntity` to inherit audit timestamps and `@Version` optimistic locking.
7. **Soft Delete Invariant**: Never execute raw SQL `DELETE FROM users`. Soft deletion is mandatory via `is_deleted = true`.

---

## Context Navigation
To avoid unnecessary token consumption, navigate progressively into detailed documentation only when required:

- **[CURRENT.md](file:///D:/coding/hekma/hekma-identity-service/docs/ai/CURRENT.md)**: Current development state, active focus, recent milestones, and blockers.
- **[ARCHITECTURE.md](file:///D:/coding/hekma/hekma-identity-service/docs/ai/ARCHITECTURE.md)**: In-depth component interactions, sequence diagrams, and external boundaries.
- **[DECISIONS.md](file:///D:/coding/hekma/hekma-identity-service/docs/ai/DECISIONS.md)**: Architecture Decision Records (ADRs) explaining technical trade-offs.
- **[CONVENTIONS.md](file:///D:/coding/hekma/hekma-identity-service/docs/ai/CONVENTIONS.md)**: Coding, naming, DTO, logging, testing, and error-handling standards.
- **[services/identity.md](file:///D:/coding/hekma/hekma-identity-service/docs/ai/services/identity.md)**: Deep dive into the `hekma-identity-service` module components and contracts.
