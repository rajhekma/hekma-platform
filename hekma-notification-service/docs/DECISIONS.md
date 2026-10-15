# Architecture Decision Records (ADRs): Hekma Notification Service (`hekma-notification-service`)

This document records the architectural and design decisions made for the Hekma Notification Service in Architecture Decision Record (ADR) format.

---

## ADR-001: Multi-Channel Notification Engine via Channel Handler Strategy Pattern (SPI)

- **Status**: Accepted
- **Date**: 2026-09-30
- **Context**:
  - The Hekma Platform requires dispatching notifications across diverse channels (`EMAIL`, `SMS`, `PUSH`, `IN_APP`).
  - Hardcoding delivery logic inside a single monolithic service would result in tight coupling, high regression risk when adding new providers, and difficult testing.
- **Decision**:
  - Implement the **Strategy Pattern (Channel SPI)**:
    - Define a common interface [NotificationChannelHandler.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/channel/NotificationChannelHandler.java) with method `handle(ChannelDispatchContext context): NotificationResult`.
    - Provide concrete handlers: `EmailChannelHandler`, `SmsChannelHandler`, `PushChannelHandler`, and `InAppChannelHandler`.
    - Automatically discover and register handlers at boot time in [NotificationChannelRegistry.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/channel/NotificationChannelRegistry.java).
- **Alternatives Considered**:
  - *Large Switch Statement in Dispatcher*: Rejected due to violation of Open/Closed Principle and unmaintainable monolithic growth.
  - *Separate Microservices per Channel (e.g. Email Service, SMS Service)*: Rejected as excessive architectural overhead at the current project scale.
- **Consequences**:
  - Modular, highly testable handlers; new channels or providers can be introduced without touching existing delivery logic.

---

## ADR-002: Dual Provider Design with Mock Defaults for Local Development & CI

- **Status**: Accepted
- **Date**: 2026-09-30
- **Context**:
  - Running automated integration tests or spinning up local developer environments should not require active third-party credentials (such as Twilio account SIDs or production SMTP passwords).
- **Decision**:
  - Build dual providers for each external channel:
    - **Email**: `MockEmailProvider` (logs to console) and `SmtpEmailProvider` (`JavaMailSender`).
    - **SMS**: `MockSmsProvider` (logs to console) and `TwilioSmsProvider`.
    - **Push**: `MockPushProvider` and `FirebasePushProvider`.
  - Default configurations to `mock` in `application.yml` and test profiles.
- **Alternatives Considered**:
  - *Mandatory External Credentials with Mockito Mocks Only*: Rejected because end-to-end local application boot should work without configuring credentials.
- **Consequences**:
  - Instant local developer onboarding and frictionless CI/CD test runs.

---

## ADR-003: Asynchronous Dispatch via Dedicated Task Executor

- **Status**: Accepted
- **Date**: 2026-09-30
- **Context**:
  - Calling microservices (like `hekma-identity-service` registering a user) need to trigger notifications without waiting for third-party SMTP handshakes or SMS network roundtrips.
- **Decision**:
  - Implement asynchronous execution via [NotificationAsyncDispatcher.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/service/NotificationAsyncDispatcher.java) annotated with `@Async("notificationTaskExecutor")`.
  - Configure a dedicated `ThreadPoolTaskExecutor` (core size 5, max size 20, queue capacity 500).
  - Return HTTP `202 Accepted` immediately, and update delivery status to `SENT` or `FAILED` in an isolated database transaction (`Propagation.REQUIRES_NEW`).
- **Alternatives Considered**:
  - *Synchronous-Only Execution*: Rejected due to added latency on user registration and login workflows.
  - *Heavy Message Queue (RabbitMQ / Kafka) from Day 1*: Deferred until scale necessitates message broker infrastructure.
- **Consequences**:
  - Calling microservices experience near-zero latency overhead.
  - Delivery failures are logged in `notification_logs` without impacting caller transactions.

---

## ADR-004: Shared Secret Header (`X-Hekma-Service-Key`) for Inter-Service Authentication

- **Status**: Accepted
- **Date**: 2026-09-30
- **Context**:
  - The notification dispatch endpoints (`/api/v1/notifications/**`) are internal APIs that must not be exposed to arbitrary public internet traffic.
- **Decision**:
  - Implement [ApiKeyAuthFilter.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/config/ApiKeyAuthFilter.java) enforcing an HTTP header `X-Hekma-Service-Key` matching `hekma.security.service-api-key`.
  - Authenticated calls receive `ROLE_INTERNAL_SERVICE`. Unauthenticated calls to dispatch endpoints return `401 Unauthorized`.
  - Public in-app notification endpoints (`/api/v1/in-app-notifications/**`) remain accessible to client applications.
- **Alternatives Considered**:
  - *Full mTLS (Mutual TLS)*: Rejected as overly complex for initial internal containerized service mesh.
  - *OAuth2 Client Credentials Grant*: Deferred until a centralized authorization server is introduced across all internal microservices.
- **Consequences**:
  - Lightweight, robust protection for internal dispatching without complex token exchange machinery.

---

## ADR-005: Idempotency Key Tracking in Notification Logs

- **Status**: Accepted
- **Date**: 2026-09-30
- **Context**:
  - Microservices might retry failed HTTP calls or experience network timeouts, risking duplicate notification delivery (such as sending two OTP codes or duplicate appointment reminders).
- **Decision**:
  - Support an optional `idempotencyKey` field in [NotificationSendRequest.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/dto/NotificationSendRequest.java).
  - Create a database index on `notification_logs.idempotency_key`.
  - If a matching key exists, return the existing `NotificationLog` record and skip duplicate dispatching.
- **Alternatives Considered**:
  - *Redis Distributed Cache for Idempotency*: Rejected to avoid adding another infrastructure dependency when PostgreSQL indexed lookups are fast and already transactional.
- **Consequences**:
  - Guaranteed at-most-once delivery for callers supplying consistent idempotency keys.

---

## ADR-006: Dedicated Persistent In-App Notification Feed in PostgreSQL

- **Status**: Accepted
- **Date**: 2026-09-30
- **Context**:
  - Patients and trial investigators need an in-app inbox to view historical announcements, read states, and unread badge counts.
- **Decision**:
  - Implement a dedicated table `in_app_notifications` with composite indexing on `(user_id, is_read)`.
  - Provide REST endpoints for paginated feed retrieval, unread counts, and marking individual or all notifications as read.
- **Alternatives Considered**:
  - *Overloading `notification_logs`*: Rejected because `notification_logs` is an immutable delivery audit log, while in-app notifications require mutable read states and user-specific inbox lifecycles.
- **Consequences**:
  - Clean domain separation between system audit records and user inbox data.

---

## ADR-007: Strict Git Workflow Governance in `AGENTS.md`

- **Status**: Accepted
- **Date**: 2026-10-01
- **Context**:
  - AI coding agents working across repositories must not push or commit unverified code to remote branches without developer approval.
- **Decision**:
  - Enforce in [AGENTS.md](file:///D:/coding/hekma/hekma-notification-service/AGENTS.md) that agents **NEVER** run `git commit` or `git push` unless explicitly asked in the prompt.
  - All modifications remain in the working tree for developer inspection.
- **Alternatives Considered**:
  - *Automated Commits*: Rejected due to risk of polluting Git history.
- **Consequences**:
  - Preserves clean Git history and gives developers complete oversight.
