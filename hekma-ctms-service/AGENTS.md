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

Welcome, agent. This repository is **`hekma-ctms-service`**, the centralized Clinical Trial Management System (CTMS) microservice for the Hekma Platform.

Treat this file and the `docs/` directory as the authoritative source of truth. Always preserve context portability across different developers, machines, and Antigravity accounts without relying on ephemeral chat histories.

---

## 1. Technology Stack & Runtime Prerequisites

- **Language & Runtime**: Java 25 (Compiler release 21).
- **Framework**: Spring Boot `4.1.1` (Spring Framework 7.x, Spring Security `7.1.1`, Spring Data JPA `4.1.1`).
- **Query Engines**:
  - Spring for GraphQL `2.0.5` / GraphQL Java `25.0`.
  - REST with SpringDoc OpenAPI `3.1.0`.
- **Database & Migrations**: PostgreSQL (shared database `hekmaai` / `common`) / Flyway `12.4.0`.
  - Schema History Table: `ctms_flyway_schema_history`.
  - Table Prefix: `ctms_*`.
- **Test Infrastructure**: H2 In-Memory Database (`MODE=PostgreSQL`) & Spring Boot Test Starter.
- **Security**: Bearer token authentication validated via token introspection with `hekma-identity-service` (`POST /internal/v1/auth/introspect`) with SHA-256 token caching. External EDC webhook authenticated via `X-Access-Key` and `X-Secret-Key`.
