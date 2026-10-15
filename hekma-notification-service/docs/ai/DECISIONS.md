# Architecture Decisions

This document records architectural decisions made for `hekma-notification-service`, capturing context, decisions, alternatives considered, and consequences.

---

## ADR-001 — Multi-Channel Notification Engine via Channel Handler Strategy Pattern (SPI)

Status: Accepted

### Context
The platform requires dispatching notifications across diverse channels (`EMAIL`, `SMS`, `PUSH`, `IN_APP`). Hardcoding delivery logic inside a monolithic service creates tight coupling, regression risk when adding providers, and difficult testing.

### Decision
Implement the **Strategy Pattern (Channel SPI)**:
- Define `NotificationChannelHandler` with method `handle(ChannelDispatchContext context): NotificationResult`.
- Provide concrete handlers: `EmailChannelHandler`, `SmsChannelHandler`, `PushChannelHandler`, and `InAppChannelHandler`.
- Automatically discover and register handlers at startup in `NotificationChannelRegistry`.

### Alternatives Considered
- *Large Switch Statement in Dispatcher*: Rejected due to violation of Open/Closed Principle.
- *Separate Microservices per Channel*: Rejected as excessive architectural complexity for current volume.

### Consequences
- Modular, highly testable handlers; new channels or third-party providers can be introduced without modifying existing delivery code.

---

## ADR-002 — Dual Provider Design with Mock Defaults for Local Development & CI

Status: Accepted

### Context
Running automated tests or local developer environments must not require live third-party credentials (Twilio account SIDs, production SMTP credentials, AWS S3 keys).

### Decision
Build dual providers for each channel and attachment storage:
- **Email**: `MockEmailProvider` and `SmtpEmailProvider`.
- **SMS**: `MockSmsProvider` and `TwilioSmsProvider`.
- **Push**: `MockPushProvider` and `FirebasePushProvider`.
- **Storage**: `MockAttachmentStorageProvider` and `AwsS3AttachmentStorageProvider`.
- Default configuration to `mock` in `application.yml` and test profiles.

### Alternatives Considered
- *Mandatory External Credentials with Mockito Mocks Only*: Rejected because the full application boot sequence must work cleanly without external credentials.

### Consequences
- Frictionless developer onboarding and reliable, fast CI/CD test runs.

---

## ADR-003 — Asynchronous Dispatch via Dedicated Task Executor

Status: Accepted

### Context
Calling microservices (like `hekma-identity-service`) need to trigger notifications without waiting for third-party SMTP handshakes or SMS network latencies.

### Decision
Implement asynchronous execution via `NotificationAsyncDispatcher` annotated with `@Async("notificationTaskExecutor")`:
- Configure a dedicated `ThreadPoolTaskExecutor` (core size 5, max size 20, queue capacity 500).
- Return HTTP `202 Accepted` immediately.
- Update delivery status to `SENT` or `FAILED` in an isolated database transaction (`Propagation.REQUIRES_NEW`).

### Alternatives Considered
- *Synchronous-Only Execution*: Rejected due to unacceptable latency on caller registration and login workflows.
- *Message Broker (Kafka / RabbitMQ)*: Deferred until transaction volume necessitates distributed queue infrastructure.

### Consequences
- Calling services experience near-zero latency overhead.
- Delivery failures are logged in `notification_logs` without impacting caller transactions.

---

## ADR-004 — Shared Secret Header (`X-Hekma-Service-Key`) for Inter-Service Authentication

Status: Accepted

### Context
The notification dispatch endpoints (`/api/v1/notifications/**`) are internal APIs that must not be exposed to unauthorized external traffic.

### Decision
Implement `ApiKeyAuthFilter` enforcing an HTTP header `X-Hekma-Service-Key` matching `hekma.security.service-api-key`:
- Authenticated calls receive `ROLE_INTERNAL_SERVICE`. Unauthorized calls return `401 Unauthorized`.
- Public in-app feed endpoints (`/api/v1/in-app-notifications/**`) and support endpoints remain publicly accessible.

### Alternatives Considered
- *Full mTLS (Mutual TLS)*: Rejected as overly complex for initial internal service mesh.
- *OAuth2 Client Credentials Grant*: Deferred until a centralized authorization server is introduced across all internal microservices.

### Consequences
- Lightweight, robust protection for internal dispatching without complex token exchange overhead.

---

## ADR-005 — Idempotency Key Tracking in Notification Logs

Status: Accepted

### Context
Microservices might retry failed HTTP calls or experience network timeouts, risking duplicate notification delivery (such as sending double OTP codes or duplicate appointment reminders).

### Decision
Support an optional `idempotencyKey` field in `NotificationSendRequest`:
- Index `notification_logs.idempotency_key`.
- If a matching key exists, return the existing `NotificationLog` record and bypass duplicate dispatching.

### Alternatives Considered
- *Redis Distributed Cache for Idempotency*: Rejected to avoid an extra infrastructure dependency when PostgreSQL indexed lookups are fast and transactional.

### Consequences
- Guaranteed at-most-once delivery for callers supplying consistent idempotency keys.

---

## ADR-006 — Dedicated Persistent In-App Notification Feed in PostgreSQL

Status: Accepted

### Context
Trial participants and investigators require an in-app inbox to view announcements, read states, and unread badge counts.

### Decision
Implement a dedicated table `in_app_notifications` with composite indexing on `(user_id, is_read)`:
- Expose REST endpoints for paginated feed retrieval, unread counts, and single/bulk read acknowledgments.

### Alternatives Considered
- *Overloading `notification_logs`*: Rejected because `notification_logs` is an immutable delivery audit log, while in-app notifications require mutable read states and user-specific inbox lifecycles.

### Consequences
- Clean domain separation between system audit logs and mutable user inbox data.

---

## ADR-007 — Support Center Architecture with Presigned S3 Attachment Storage SPI

Status: Accepted

### Context
Support ticket submissions require file attachments (screenshots, clinical reports). Uploading large binary files directly through Spring Boot application servers consumes server memory and worker threads.

### Decision
Decouple attachment storage via `AttachmentStorageProvider`:
- `AwsS3AttachmentStorageProvider` generates short-lived presigned S3 PUT URLs, allowing clients to upload directly to S3.
- `MockAttachmentStorageProvider` simulates uploads for local development and CI testing.

### Alternatives Considered
- *Direct Database BLOB Storage*: Rejected due to database bloat and performance degradation.
- *Local Filesystem Storage*: Rejected due to non-portability in containerized cloud environments.

### Consequences
- High-performance, scalable attachment handling with zero server memory overhead for large files.
