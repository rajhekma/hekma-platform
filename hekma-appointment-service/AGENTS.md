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
- **Avoid Low-Level Clutter**: Avoid bloating `README.md` with overly low-level technical minutiae that belong in Swagger/OpenAPI docs or code annotations.

---

# AI Coding Agent Entry Point & Instructions

Welcome, agent. This repository is **`hekma-appointment-service`**, the centralized Clinical Appointment, Scheduling, and Reminder microservice for the Hekma Platform.

Treat this file and the `docs/` directory as the authoritative source of truth. Always preserve context portability across different developers, machines, and Antigravity accounts without relying on ephemeral chat histories.

---

## 1. Quick Reference & Core Documentation Links

### Shared AI Context System (Progressive Disclosure)
- **`docs/ai/CONTEXT.md`**: Primary lightweight AI entry point (~500–1000 words).
- **`docs/ai/CURRENT.md`**: Current task focus, recently completed features, pending items, and blockers.
- **`docs/ai/ARCHITECTURE.md`**: System architecture diagrams, component interactions, conflict detection, and external contracts.
- **`docs/ai/DECISIONS.md`**: Architecture Decision Records (ADRs) explaining key design trade-offs.
- **`docs/ai/CONVENTIONS.md`**: Coding standards, DTO patterns, error handling, and testing rules.

### Detailed Reference Documentation
- **`docs/PROJECT_CONTEXT.md`**: Business requirements, scheduling workflows, reminder cadences, and domain terminology.
- **`docs/DATABASE.md`**: PostgreSQL schema, ERD, entity constraints, and Flyway migration scripts (`appointment_*`).
- **`docs/API_DOCUMENTATION.md`**: REST endpoints, GraphQL queries/mutations, payload examples, and error formats.

---

## 2. Technology Stack & Runtime Prerequisites

- **Language & Runtime**: Java 25 (Compiler release 21 target).
  > [!IMPORTANT]
  > Ensure `JAVA_HOME` points to JDK 21 or GraalVM JDK 25 before executing Maven builds or tests:
  > `$env:JAVA_HOME="C:\Users\Acer_PTS\.jdks\graalvm-jdk-25"; $env:Path="$env:JAVA_HOME\bin;" + $env:Path`
- **Framework**: Spring Boot `4.1.1` (Spring Framework 7.x, Spring Security `7.1.1`, Spring Data JPA `4.1.1`).
- **Query Engines**:
  - Spring for GraphQL `2.0.5` / GraphQL Java `25.0` (endpoint `/graphql`, explorer `/graphiql`).
  - REST with SpringDoc OpenAPI `3.1.0` (Swagger UI at `/swagger-ui/index.html`).
- **Database & Migrations**: PostgreSQL (shared `hekmaai` database) / Flyway `12.4.0`.
  - Schema History Table: `appointment_flyway_schema_history`.
  - Table Prefix: `appointment_*`.
- **Test Infrastructure**: H2 In-Memory Database (`MODE=PostgreSQL`) & Spring Boot Test Starter.
- **Security**: Bearer token authentication validated via token introspection with `hekma-identity-service` (`POST /internal/v1/auth/introspect`) on port 8080 with SHA-256 token caching.
- **Notification Integration**: HTTP client calling `hekma-notification-service` (`POST /api/v1/notifications/send`) on port 8081.

---

## 3. Architecture & Core Invariants

1. **Standalone Microservice (Port 8083)**:
   - Decoupled from legacy monolithic `hekma_api`.
   - Runs independently with dedicated Flyway migration history.
2. **Double-Booking & Conflict Detection**:
   - `ConflictDetectionService` verifies overlapping time intervals for doctors, sites, or patients:
     `existing.startTime < new.endTime AND existing.endTime > new.startTime`.
   - Rejects conflicting appointments with HTTP 409 Conflict.
3. **Automated Reminders**:
   - `AppointmentReminderScheduler` checks upcoming appointments periodically.
   - Idempotently dispatches 1-hour, 1-day, and 7-day reminders based on user preferences.
4. **Distributed Tracing & Correlation**:
   - Every request is tagged with a UUID trace ID via `TraceIdFilter`.
   - Propagated through response headers (`X-Trace-Id`, `trace-id`) and embedded in API error/success responses as single `"traceId"`.
5. **Soft Deletion & Auditing**:
   - All domain entities extend `BaseAuditEntity` (`id`, `createdAt`, `updatedAt`, `createdBy`, `updatedBy`, `@Version Long version`, `isDeleted`).
   - Soft-deleted rows are restricted via `@SQLRestriction("is_deleted = false")`.
