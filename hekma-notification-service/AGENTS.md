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

Welcome, agent. This repository is **`hekma-notification-service`**, the centralized multi-channel notification microservice for the Hekma Platform.

Treat this file and the `docs/` directory as the authoritative source of truth. Always preserve context portability across different developers, machines, and Antigravity accounts without relying on ephemeral chat histories.

---

## 1. Quick Reference & Core Documentation Links

### Shared AI Context System (Progressive Disclosure)
- **[docs/ai/CONTEXT.md](file:///D:/coding/hekma/hekma-notification-service/docs/ai/CONTEXT.md)**: Primary lightweight AI entry point (500–1000 words).
- **[docs/ai/CURRENT.md](file:///D:/coding/hekma/hekma-notification-service/docs/ai/CURRENT.md)**: Current task focus, recently completed milestones, and blockers.
- **[docs/ai/ARCHITECTURE.md](file:///D:/coding/hekma/hekma-notification-service/docs/ai/ARCHITECTURE.md)**: System architecture, Channel SPI pattern, and async worker design.
- **[docs/ai/DECISIONS.md](file:///D:/coding/hekma/hekma-notification-service/docs/ai/DECISIONS.md)**: Architecture Decision Records (ADRs) explaining technical trade-offs.
- **[docs/ai/CONVENTIONS.md](file:///D:/coding/hekma/hekma-notification-service/docs/ai/CONVENTIONS.md)**: Coding standards, DTO patterns, error handling, and testing rules.
- **[docs/ai/services/notification.md](file:///D:/coding/hekma/hekma-notification-service/docs/ai/services/notification.md)**: Module-level deep dive into `hekma-notification-service`.

### Detailed Reference Documentation
- **[docs/PROJECT_CONTEXT.md](file:///D:/coding/hekma/hekma-notification-service/docs/PROJECT_CONTEXT.md)**: Business requirements, supported communication channels, template engine, and known limitations.
- **[docs/ARCHITECTURE.md](file:///D:/coding/hekma/hekma-notification-service/docs/ARCHITECTURE.md)**: System architecture diagrams, Channel SPI Strategy Pattern, async executor design, and inter-service authentication.
- **[docs/DATABASE.md](file:///D:/coding/hekma/hekma-notification-service/docs/DATABASE.md)**: PostgreSQL schema, ERD, entity models (`NotificationLog`, `InAppNotification`), and Flyway migrations.
- **[docs/API_DOCUMENTATION.md](file:///D:/coding/hekma/hekma-notification-service/docs/API_DOCUMENTATION.md)**: REST endpoints for dispatching, broadcasting, status retrieval, and in-app feed management.
- **[docs/NOTIFICATION_FLOW.md](file:///D:/coding/hekma/hekma-notification-service/docs/NOTIFICATION_FLOW.md)**: Detailed end-to-end delivery flows across all channels (EMAIL, SMS, PUSH, IN_APP), sequence diagrams, and provider execution details.
- **[docs/DEVELOPMENT_LOG.md](file:///D:/coding/hekma/hekma-notification-service/docs/DEVELOPMENT_LOG.md)**: Chronological development log, completed features (HK-6060), and pending roadmap items.
- **[docs/DECISIONS.md](file:///D:/coding/hekma/hekma-notification-service/docs/DECISIONS.md)**: Architecture Decision Records (ADRs) explaining key design trade-offs.

---

## 2. Technology Stack & Runtime Prerequisites

- **Language & Runtime**: Java 25 (GraalVM JDK 25 / OpenJDK 25).
  > [!IMPORTANT]
  > Ensure `JAVA_HOME` points to JDK 21 or 25 (e.g. `C:\Users\Acer_PTS\.jdks\graalvm-jdk-25`) before executing Maven builds or tests.
- **Framework**: Spring Boot `4.1.1` (Spring Framework 7.x, Spring MVC, Spring Security).
- **Mailing**: Spring Boot Starter Mail (`JavaMailSender` / Jakarta Mail).
- **Persistence**: Spring Data JPA / Hibernate ORM 7.x.
- **Database & Migrations**: PostgreSQL 14+ / Flyway versioned migrations.
- **Test Infrastructure**: H2 In-Memory Database (`jdbc:h2:mem:notificationdb`) & Spring Boot Test Starter.
- **API Documentation**: SpringDoc OpenAPI `3.1.0` (Swagger UI).
- **Code Generation & JSON**: Project Lombok, Jackson (`JavaTimeModule`).

---

## 3. Architecture & Core Invariants

1. **Channel SPI & Strategy Pattern**:
   - Outbound dispatching is partitioned into decoupled channel handlers (`EmailChannelHandler`, `SmsChannelHandler`, `PushChannelHandler`, `InAppChannelHandler`) coordinated by `NotificationChannelRegistry`.
   - Each channel handler delegates to pluggable providers (`MockEmailProvider`, `SmtpEmailProvider`, `MockSmsProvider`, `TwilioSmsProvider`, `MockPushProvider`).
2. **Default Mock Mode for Local Development & CI**:
   - Providers default to `mock` implementations (e.g., logging to console) so the service builds, boots, and tests cleanly without live third-party credentials.
3. **Asynchronous Dispatch by Default**:
   - Requests to `/api/v1/notifications/send` execute asynchronously via `notificationTaskExecutor` (`ThreadPoolTaskExecutor`) unless explicitly requested as `async: false`, returning HTTP `202 Accepted` immediately.
4. **Idempotency Safeguard**:
   - If an `idempotencyKey` is provided, subsequent requests with the same key return the existing notification log without duplicate transmission.
5. **Inter-Service Security**:
   - All inter-service dispatch endpoints under `/api/v1/notifications/**` require the `X-Hekma-Service-Key` header verified by `ApiKeyAuthFilter`.
   - In-app notification endpoints (`/api/v1/in-app-notifications/**`) and Swagger docs are publicly accessible to client applications.

---

## 4. Coding Conventions & Standards

- **Package Structure**:
  - `com.hekma.notification.channel`: Channel handler interfaces, dispatch contexts, results, and registry.
  - `com.hekma.notification.channel.email`: Email handlers and providers (Mock, SMTP).
  - `com.hekma.notification.channel.inapp`: In-app notification handler.
  - `com.hekma.notification.channel.push`: Push handlers and providers (Mock, Firebase FCM).
  - `com.hekma.notification.channel.sms`: SMS handlers and providers (Mock, Twilio).
  - `com.hekma.notification.config`: Security, async executor, Jackson object mapper, and global exception advice.
  - `com.hekma.notification.controller`: REST controllers (`NotificationController`, `InAppNotificationController`).
  - `com.hekma.notification.domain.entity`: JPA entities (`NotificationLog`, `InAppNotification`).
  - `com.hekma.notification.domain.model`: Domain enums (`NotificationChannel`, `NotificationPriority`, `NotificationStatus`).
  - `com.hekma.notification.domain.repository`: Spring Data JPA repositories.
  - `com.hekma.notification.dto`: Request/response DTOs and paged response wrappers.
  - `com.hekma.notification.service`: Business services (`NotificationDispatcherService`, `InAppNotificationService`, `NotificationAsyncDispatcher`, `TemplateRenderer`).
- **Database Object & Flyway Naming Conventions**:
  - **Tables**: Microservice prefix first: `<service>_<table_name>` (e.g. `notification_logs`, `notification_in_app_notifications`, `notification_support_ticket`).
  - **Indexes**: Microservice prefix first: `<service>_idx_<table_or_concept>_<columns>` (e.g. `notification_idx_logs_recipient`, `notification_idx_in_app_user_id`).
  - **Flyway Schema History Tables**: Microservice prefix first: `<service>_flyway_schema_history` (e.g. `notification_flyway_schema_history`, `identity_flyway_schema_history`). Must be configured via `spring.flyway.table: ${FLYWAY_TABLE:<service>_flyway_schema_history}` with `baseline-version: 0` for safe co-location on the shared PostgreSQL database (`hekmaai`).
- **Entity Conventions**:
  - UUID primary keys automatically generated via `@PrePersist`.
  - UTC timestamps (`createdAt`, `updatedAt`) managed in lifecycle callbacks.
- **Error Handling**:
  - Centralized in `GlobalExceptionHandler` returning structured JSON with HTTP status, error category, message, and field validation details.
- **Logging**:
  - Use SLF4J `@Slf4j`.

---


## 5. AI Context Workflow & Token-Efficiency Rules

All AI coding agents (Claude Code, Cursor, Antigravity, and others) must follow these token-minimization rules:

### Core Agent Directives
1. **Read AGENTS.md first** to understand runtime prerequisites, safety invariants, and execution boundaries.
2. **Read `docs/ai/CONTEXT.md`** before starting a significant task for a lightweight (~500–1000 words) project overview.
3. **Read only the relevant service-specific context** (e.g. `docs/ai/services/notification.md`).
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
- Read [docs/PROJECT_CONTEXT.md](file:///D:/coding/hekma/hekma-notification-service/docs/PROJECT_CONTEXT.md) to understand business rules, supported channels, and terminology.
- Read specific documentation based on the task (e.g. [docs/ARCHITECTURE.md](file:///D:/coding/hekma/hekma-notification-service/docs/ARCHITECTURE.md) for channel SPI, [docs/DATABASE.md](file:///D:/coding/hekma/hekma-notification-service/docs/DATABASE.md) for schemas, [docs/API_DOCUMENTATION.md](file:///D:/coding/hekma/hekma-notification-service/docs/API_DOCUMENTATION.md) for endpoints).
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
  - **[docs/PROJECT_CONTEXT.md](file:///D:/coding/hekma/hekma-notification-service/docs/PROJECT_CONTEXT.md)**: When capabilities, channels, providers, or status change.
  - **[docs/ARCHITECTURE.md](file:///D:/coding/hekma/hekma-notification-service/docs/ARCHITECTURE.md)**: When channel handlers, async execution, external integrations, or architecture change.
  - **[docs/DATABASE.md](file:///D:/coding/hekma/hekma-notification-service/docs/DATABASE.md)**: When entities, table schemas, columns, indexes, or Flyway migrations change.
  - **[docs/API_DOCUMENTATION.md](file:///D:/coding/hekma/hekma-notification-service/docs/API_DOCUMENTATION.md)**: When REST endpoints, request/response DTOs, or error structures change.
  - **[docs/DEVELOPMENT_LOG.md](file:///D:/coding/hekma/hekma-notification-service/docs/DEVELOPMENT_LOG.md)**: Chronologically record significant completed work, bug fixes, and milestones.
  - **[docs/DECISIONS.md](file:///D:/coding/hekma/hekma-notification-service/docs/DECISIONS.md)**: Record Architecture Decision Records (ADRs) whenever a meaningful technical design decision was made.
  - **[AGENTS.md](file:///D:/coding/hekma/hekma-notification-service/AGENTS.md)**: Update only when project-wide rules, conventions, or agent workflows change.

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
