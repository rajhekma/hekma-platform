# Repository & Agent Rules

## Git Workflow & Remote Operations
- **Strict Commit & Push Restriction**:
  - **NEVER** run `git commit` unless the user explicitly requests a commit in their prompt (e.g., "commit the changes", "git commit").
  - **NEVER** run `git push` or push branches/tags to any remote repository unless the user explicitly asks for it in the prompt (e.g., "push the code", "git push").
- **Working Tree by Default**: All file modifications must remain uncommitted in the working tree for the user to review.
- **Working Branch Consistency**: Keep documentation changes in the same working branch as the relevant code implementation whenever practical.
- **Respect Other Developers' Work**:
  - Never overwrite another developer's uncommitted documentation changes.
  - Consider the possibility of concurrent work and Git merge conflicts.
- **Status Reporting**: After completing file edits or tests, report the modified files and status. Do not stage or commit automatically.

## Planning & Execution Boundary
- **Strict Plan-Only Rule**:
  - Whenever asked to prepare a plan, create a plan document ONLY.
  - **NEVER** execute implementation directly, modify application code, change database migrations, or run destructive tasks when asked for a plan.
  - Wait for explicit user confirmation and approval before proceeding with code changes.

## Documentation & README Guidelines
- **High-Level Overview Only**: In `README.md` files, focus on essential high-level details:
  - Application purpose and core business features.
  - Tech stack, tools, and explicit library/dependency versions (e.g., Java version, Spring Boot version, database, key frameworks).
  - High-level setup/run instructions and Swagger/OpenAPI pointers.
- **Avoid Low-Level Clutter**: Avoid bloating `README.md` with overly low-level technical minutiae (such as exhaustive REST payloads, method signatures, or granular schema tables) that belong in Swagger/OpenAPI docs or code annotations.

---

# AI Coding Agent Entry Point & Instructions

Welcome, agent. This repository is **`hekma-identity-service`**, the centralized authentication, authorization, clinical user profile, and regulatory consent microservice for the Hekma Platform.

Treat this file and the `docs/` directory as the authoritative source of truth. Always preserve context portability across different developers, machines, and Antigravity accounts without relying on ephemeral chat histories.

---

## 1. Quick Reference & Core Documentation Links

### Shared AI Context System (Progressive Disclosure)
- **[docs/ai/CONTEXT.md](file:///D:/coding/hekma/hekma-identity-service/docs/ai/CONTEXT.md)**: Primary lightweight AI entry point (500–1000 words).
- **[docs/ai/CURRENT.md](file:///D:/coding/hekma/hekma-identity-service/docs/ai/CURRENT.md)**: Current task focus, recently completed features, pending items, and blockers.
- **[docs/ai/ARCHITECTURE.md](file:///D:/coding/hekma/hekma-identity-service/docs/ai/ARCHITECTURE.md)**: System architecture diagrams, dual-write saga, and external contracts.
- **[docs/ai/DECISIONS.md](file:///D:/coding/hekma/hekma-identity-service/docs/ai/DECISIONS.md)**: Architecture Decision Records (ADRs) explaining key design trade-offs.
- **[docs/ai/CONVENTIONS.md](file:///D:/coding/hekma/hekma-identity-service/docs/ai/CONVENTIONS.md)**: Coding standards, DTO patterns, error handling, and testing rules.
- **[docs/ai/services/identity.md](file:///D:/coding/hekma/hekma-identity-service/docs/ai/services/identity.md)**: Module-level deep dive into `hekma-identity-service`.

### Detailed Reference Documentation
- **[docs/PROJECT_CONTEXT.md](file:///D:/coding/hekma/hekma-identity-service/docs/PROJECT_CONTEXT.md)**: Business requirements, clinical consent flows, user roles, terminology, and known limitations.
- **[docs/DATABASE.md](file:///D:/coding/hekma/hekma-identity-service/docs/DATABASE.md)**: PostgreSQL schema, ERD, entity constraints, and Flyway migration scripts (V1–V8).
- **[docs/API_DOCUMENTATION.md](file:///D:/coding/hekma/hekma-identity-service/docs/API_DOCUMENTATION.md)**: REST endpoints, GraphQL queries/mutations, payload examples, and error formats.
- **[docs/DEVELOPMENT_LOG.md](file:///D:/coding/hekma/hekma-identity-service/docs/DEVELOPMENT_LOG.md)**: Chronological development log and milestone history.
- **[docs/MULTITENANCY_PLAN.md](file:///D:/coding/hekma/hekma-identity-service/docs/MULTITENANCY_PLAN.md)**: Multi-tenancy architectural proposal and migration roadmap.
- **[docs/RBAC_PLAN.md](file:///D:/coding/hekma/hekma-identity-service/docs/RBAC_PLAN.md)**: RBAC plan (all phases implemented).

---

## 2. Technology Stack & Runtime Prerequisites

- **Language & Runtime**: Java 25 (Compiler release 21).
  > [!IMPORTANT]
  > Ensure `JAVA_HOME` points to JDK 21 or 25 (e.g. `C:\Users\Acer_PTS\.jdks\graalvm-jdk-25`) before executing Maven builds or tests.
- **Framework**: Spring Boot `4.1.1` (Spring Framework 7.x, Spring Security `7.1.1`, Spring Data JPA `4.1.1`).
- **Identity & IdP**: Google Firebase Admin SDK `9.4.3` / Google STS.
- **Query Engine**: Spring for GraphQL `2.0.5` / GraphQL Java `25.0`.
- **Database & Migrations**: PostgreSQL 18 / Flyway `12.4.0`.
- **Test Infrastructure**: H2 In-Memory Database (`MODE=PostgreSQL`) & Spring Boot Test Starter.
- **Code Generation**: Project Lombok.

---

## 3. Architecture & Core Invariants

1. **Dual-Write Consistency with Compensating Rollback**:
   - User creation synchronizes Firebase Auth with PostgreSQL.
   - If PostgreSQL persistence fails, delete user from Firebase.
   - If OTP dispatch fails, delete user from PostgreSQL and Firebase.
2. **Strict RBAC Hierarchy**:
   - `SYSTEM_ADMIN`: Immutable root admin bootstrapped at startup. Only role allowed to invite `ADMIN`.
   - `ADMIN`: Operational administrator. Can manage `SPONSOR`, `SITE`, `PATIENT`. Cannot modify other `ADMIN` or `SYSTEM_ADMIN`.
   - `SPONSOR`, `SITE`: Tenant roles (role always equals the tenant type). Created by tenant self-registration (`register-tenant`, new top-level tenant) or as a sub-tenant owner — never by self-joining an existing tenant.
   - Tenants are hierarchical (materialized `path`); SPONSOR/SITE users act only within their tenant's subtree, and a non-active tenant blocks its whole subtree.
   - SPONSOR/SITE capabilities come from per-user authorities (`Authority` enum + `identity_user_authorities`); grant ≤ own, never to self; privileged changes are audited (`identity_authz_audit_log`). Exactly one `SYSTEM_ADMIN` (DB-enforced).
   - `PATIENT`: The only role allowed for public self-registration (joins the default tenant Hekma, or the inviting tenant).
3. **Conditional 2FA for Patients**:
   - `PATIENT` with `twoFactorEnabled == true`: Login triggers an OTP challenge, withholding JWT tokens until verified via `/api/v1/auth/otp/verify`.
   - All other roles / patients with 2FA disabled: Direct login returning tokens.
4. **Soft Deletion**:
   - Always soft-delete via `@SQLRestriction("is_deleted = false")`. Never run raw SQL `DELETE FROM users`.
5. **Authentication & Caller Identity**:
   - Every non-public endpoint requires `Authorization: Bearer <Firebase ID token>`, verified by `FirebaseAuthenticationFilter`; role/tenant come from PostgreSQL (`HekmaPrincipal`).
   - Never read caller or tenant identity from headers/bodies (`X-Operator-Id` was removed). Every protected handler declares `@PreAuthorize` (prefer `hasAuthority('…')`); public endpoints are listed explicitly in `SecurityConfig` and `AuthorizationGuardTest`.
6. **Passwords**:
   - Created, changed, reset and validated only through this API; stored only in Firebase (never in PostgreSQL). Every password-setting DTO uses `@StrongPassword`.

---

## 4. Coding Conventions & Standards

- **Package Structure**:
  - `com.hekma.identity.config`: Security, OpenAPI, JPA auditing, and startup initializers.
  - `com.hekma.identity.controller`: REST and GraphQL controllers.
  - `com.hekma.identity.domain`: JPA entities, enums (`Role`, `UserStatus`).
  - `com.hekma.identity.domain.otp`: OTP entities, enums (`VerificationMode`, `OtpPurpose`, `OtpStatus`, `OtpAuditEventType`).
  - `com.hekma.identity.dto`: REST and GraphQL data transfer objects.
  - `com.hekma.identity.dto.otp`: Request/response DTOs for OTP workflows.
  - `com.hekma.identity.exception`: Custom runtime exceptions and centralized `GlobalExceptionHandler`.
  - `com.hekma.identity.firebase`: Firebase service interfaces, live Admin SDK implementation, and `MockFirebaseService`.
  - `com.hekma.identity.security`: `FirebaseAuthenticationFilter`, `HekmaPrincipal`, `AuthEmails`, `SecurityErrorWriter`.
  - `com.hekma.identity.multitenancy`: `TenantContext` and `TenantFilter` (tenant from the authenticated principal).
  - `com.hekma.identity.validation`: Custom Bean Validation constraints (`@StrongPassword`).
  - `com.hekma.identity.notification`: HTTP client for `hekma-notification-service`.
  - `com.hekma.identity.repository`: Spring Data JPA repositories.
  - `com.hekma.identity.service`: Business service layer (`AuthService`, `OtpService`, `UserManagementService`, `UserQueryService`).
- **Database Object & Flyway Naming Conventions**:
  - **Tables**: Microservice prefix first: `<service>_<table_name>` (e.g. `identity_users`, `identity_patient_details`, `identity_otp_requests`, `notification_logs`).
  - **Indexes**: Microservice prefix first: `<service>_idx_<table_or_concept>_<columns>` (e.g. `identity_idx_users_email`, `identity_idx_otp_audit_phone`, `notification_idx_logs_recipient`).
  - **Flyway Schema History Tables**: Microservice prefix first: `<service>_flyway_schema_history` (e.g. `identity_flyway_schema_history`, `notification_flyway_schema_history`). Must be configured via `spring.flyway.table: ${FLYWAY_TABLE:<service>_flyway_schema_history}` with `baseline-version: 0` for safe co-location on the shared PostgreSQL database (`hekmaai`).
- **Entity Conventions**:
  - All JPA entities must extend `BaseAuditEntity` to automatically inherit `createdAt`, `updatedAt`, `createdBy`, `updatedBy`, and optimistic locking `@Version Long version`.
- **Error Handling**:
  - Never return raw exceptions or stack traces to clients. Throw domain exceptions handled by [GlobalExceptionHandler.java](file:///D:/coding/hekma/hekma-identity-service/src/main/java/com/hekma/identity/exception/GlobalExceptionHandler.java) returning standardized `ApiErrorResponse`.
- **Logging**:
  - Use SLF4J `@Slf4j`. Avoid `System.out.println` except for mock OTP console outputs during development.

---


## 5. AI Context Workflow & Token-Efficiency Rules

All AI coding agents (Claude Code, Cursor, Antigravity, and others) must follow these token-minimization rules:

### Core Agent Directives
1. **Read AGENTS.md first** to understand runtime prerequisites, safety invariants, and execution boundaries.
2. **Read `docs/ai/CONTEXT.md`** before starting a significant task for a lightweight (~500–1000 words) project overview.
3. **Read only the relevant service-specific context** (e.g. `docs/ai/services/identity.md`).
4. **Do not scan the entire repository unnecessarily**. Use targeted file lookups instead of broad directory sweeps.
5. **Use the actual source code as the final source of truth** when documentation is missing or outdated.
6. **Use `docs/ai/ARCHITECTURE.md`** for architectural, component-interaction, and data-flow questions.
7. **Use `docs/ai/DECISIONS.md`** to understand verified historical architectural and technical decisions (ADRs).
8. **Use `docs/ai/CURRENT.md`** for current development state, active focus, blockers, and recent changes.
9. **Update relevant AI documentation after significant changes** to keep the shared context synchronized.
10. **Never add secrets, API keys, credentials, or private patient data to AI documentation.**

### Before Starting a Significant Task
1. Read this `AGENTS.md`.
2. Read `docs/ai/CONTEXT.md`.
3. Identify the relevant service/module.
4. Read the corresponding file under `docs/ai/services/`.
5. Read additional documentation only when required.
6. Inspect the relevant source code.
7. Do not scan the entire repository unless necessary.

### After Completing a Significant Task
1. Review the files changed.
2. Determine whether project context changed.
3. Update `docs/ai/CURRENT.md` if project status, focus, or completed milestones changed.
4. Update `docs/ai/ARCHITECTURE.md` if architecture or component boundaries changed.
5. Update `docs/ai/DECISIONS.md` if a significant technical decision was made.
6. Update the relevant service context under `docs/ai/services/` if service behavior changed.
7. Update `docs/ai/CONVENTIONS.md` if project conventions changed.
8. Keep `docs/ai/CONTEXT.md` concise and update it only when high-level project context changes.

> [!NOTE]
> Do not update documentation for trivial changes.  
> Do not invent information or Jira keys.  
> Do not overwrite unrelated developer changes.  
> Do not commit or push changes unless explicitly requested.

---

## 6. Standard Agent Execution Workflow

Every coding task must follow this phased lifecycle:

### Step 1: Read Project Context Before Starting
- Always read this file (`AGENTS.md`) before analyzing the task.
- Read [docs/PROJECT_CONTEXT.md](file:///D:/coding/hekma/hekma-identity-service/docs/PROJECT_CONTEXT.md) to understand business rules, roles, and domain terminology.
- Read specific documentation based on the task (e.g. [docs/ARCHITECTURE.md](file:///D:/coding/hekma/hekma-identity-service/docs/ARCHITECTURE.md) for service design, [docs/DATABASE.md](file:///D:/coding/hekma/hekma-identity-service/docs/DATABASE.md) for schemas, [docs/API_DOCUMENTATION.md](file:///D:/coding/hekma/hekma-identity-service/docs/API_DOCUMENTATION.md) for endpoints).
- Inspect the current codebase, recent Git commits, and working tree status (`git status`).
- **Ground Truth Invariant**: Treat the actual codebase implementation as the ultimate source of truth whenever existing documentation contains discrepancies.

### Step 2: Planning & Approval
- Formulate a clear, step-by-step implementation plan.
- **Strict Plan-Only Rule**: When requested to prepare a plan, produce ONLY planning documentation (e.g., plan document in `docs/` or planning proposal) and NEVER execute implementation code or modify application source code directly.
- Always obtain explicit user confirmation and approval before proceeding to implementation.

### Step 3: Minimal & Robust Implementation
- Make minimal, clean, robust modifications conforming strictly to project architecture and coding conventions.
- Do not add unnecessary dependencies or modify unrelated files.

### Step 4: Test Verification
- Execute the test suite using Maven:
  ```powershell
  $env:JAVA_HOME="C:\Users\Acer_PTS\.jdks\graalvm-jdk-25"; $env:Path="$env:JAVA_HOME\bin;" + $env:Path
  .\mvnw.cmd test
  ```
- Confirm all tests pass without errors or regressions.

### Step 5: Automatic Documentation Updates
Immediately after completing any significant feature, bug fix, refactoring, or architectural change:
- Review all files changed during the task.
- Identify which documentation files are affected.
- Update the relevant Markdown files to reflect the actual implementation:
  - **[docs/PROJECT_CONTEXT.md](file:///D:/coding/hekma/hekma-identity-service/docs/PROJECT_CONTEXT.md)**: When project capabilities, functional flows, business rules, or status change.
  - **[docs/ARCHITECTURE.md](file:///D:/coding/hekma/hekma-identity-service/docs/ARCHITECTURE.md)**: When component boundaries, communication protocols, external integrations, or architectural patterns change.
  - **[docs/DATABASE.md](file:///D:/coding/hekma/hekma-identity-service/docs/DATABASE.md)**: When entities, table schemas, column definitions, relationships, constraints, or Flyway migrations change.
  - **[docs/API_DOCUMENTATION.md](file:///D:/coding/hekma/hekma-identity-service/docs/API_DOCUMENTATION.md)**: When REST endpoints, GraphQL queries/mutations/types, request/response DTOs, or error codes change.
  - **[docs/DEVELOPMENT_LOG.md](file:///D:/coding/hekma/hekma-identity-service/docs/DEVELOPMENT_LOG.md)**: Chronologically record significant completed work, bug fixes, and milestones.
  - **[docs/DECISIONS.md](file:///D:/coding/hekma/hekma-identity-service/docs/DECISIONS.md)**: Record Architecture Decision Records (ADRs) whenever a meaningful technical or architectural design decision was made.
  - **[AGENTS.md](file:///D:/coding/hekma/hekma-identity-service/AGENTS.md)**: Update only when project-wide rules, conventions, or agent workflows change.

### Step 6: Final Verification & Reporting
Before concluding a task:
- Verify that updated documentation strictly reflects the actual code.
- Check relative links and `file://` references across documentation files.
- Report the list of modified/created files and test verification results.
- Specify which documentation files were updated.
- Explicitly mention any relevant documentation that could not be updated due to missing information.
- **NEVER** run `git commit` or `git push` unless explicitly asked.

---

## 7. Documentation Accuracy & Maintenance Standards

- **Document Reality, Not Intentions**: Never document planned or hypothetical features as completed.
- **No Hallucinated Decisions**: Do not invent architectural decisions, requirements, or implementation details. Mark any inferences or assumptions clearly.
- **Avoid Redundancy**: Avoid duplicating granular information across multiple files. Cross-reference using relative links.
- **Maintain Clarity**: Keep documentation concise, structured, and easily digestible for a developer or AI agent onboarding for the first time.
- **Handling External Code Changes**:
  - If code changes made outside the current task are discovered during work, do not silently rewrite documentation based on assumptions.
  - Identify potentially outdated documentation and offer to synchronize it when appropriate.

---

## 8. Context Maintenance Commands

When the user issues these specific instructions, execute the following behavior:
- **"Update project context"**: Inspect recent code and Git changes, then update affected documentation in `docs/`.
- **"Sync documentation"**: Compare existing documentation against current codebase implementation and correct discrepancies.
- **"Prepare handover"**: Create or update `docs/HANDOVER.md` with current project status, completed work, pending tasks, blockers, and next steps for onboarding developers or AI agents.
- **"Review project context"**: Audit documentation files for completeness, consistency, accuracy, and missing details.
- **"Start a new task"**: Read this file (`AGENTS.md`) and relevant `docs/` files before analyzing and planning the requested task.
