# Project Conventions: Hekma Notification Service

This document defines verified architectural, coding, testing, and operational conventions enforced in `hekma-notification-service`.

---

## 1. Naming Conventions

| Component | Convention | Example |
| :--- | :--- | :--- |
| **JPA Entities** | PascalCase, singular | `NotificationLog`, `InAppNotification`, `SupportTicket` |
| **Spring Repositories** | PascalCase ending with `Repository` | `NotificationLogRepository`, `SupportTicketRepository` |
| **Service Layer** | PascalCase ending with `Service` | `NotificationDispatcherService`, `InAppNotificationService` |
| **Channel Handlers** | PascalCase ending with `ChannelHandler` | `EmailChannelHandler`, `SmsChannelHandler` |
| **Channel Providers** | PascalCase ending with `Provider` | `SmtpEmailProvider`, `TwilioSmsProvider`, `MockPushProvider` |
| **REST Controllers** | PascalCase ending with `Controller` | `NotificationController`, `SupportPublicController` |
| **DTOs (Requests)** | PascalCase ending with `Request` | `NotificationSendRequest`, `BroadcastNotificationRequest` |
| **DTOs (Responses)** | PascalCase ending with `Response` or `Dto` | `NotificationResponse`, `InAppNotificationDto` |
| **Enums** | PascalCase type, `UPPER_SNAKE_CASE` values | `NotificationChannel.EMAIL`, `NotificationStatus.SENT` |
| **Database Tables** | Microservice prefix first: `<service>_<table_name>` | `notification_logs`, `notification_in_app_notifications`, `notification_support_ticket` |
| **Database Indexes** | Microservice prefix first: `<service>_idx_<table_or_concept>_<columns>` | `notification_idx_logs_recipient`, `notification_idx_in_app_user_id` |
| **Flyway History Table** | Microservice prefix first: `<service>_flyway_schema_history` | `notification_flyway_schema_history`, `identity_flyway_schema_history` |
| **Database Columns** | `snake_case` | `idempotency_key`, `channel`, `is_read`, `created_ts` |

---


## 2. Package Structure & Layering

Strict separation of concerns:
```text
com.hekma.notification
├── channel/        # NotificationChannelHandler SPI, registry, and concrete channel handlers
│   ├── email/      # EmailChannelHandler, SmtpEmailProvider, MockEmailProvider
│   ├── inapp/      # InAppChannelHandler
│   ├── push/       # PushChannelHandler, MockPushProvider
│   └── sms/        # SmsChannelHandler, TwilioSmsProvider, MockSmsProvider
├── config/         # Security, ApiKeyAuthFilter, Async, OpenAPI, and GlobalExceptionHandler
├── controller/     # NotificationController & InAppNotificationController
├── domain/         # JPA entities, enums (NotificationChannel, Priority, Status), and repositories
├── dto/            # Request/Response DTOs & pagination wrappers
├── service/        # NotificationDispatcherService, AsyncDispatcher, TemplateRenderer
└── support/        # Clinical support helpdesk module (tickets, public OTP, attachments, storage SPI)
```

---

## 3. Dependency Injection
- **Constructor Injection Only**: Always inject dependencies via explicit constructor or Lombok `@RequiredArgsConstructor`.
- **Field Injection Prohibited**: Never use `@Autowired` on private class fields.

---

## 4. DTO Conventions & Validation
- **Jakarta Bean Validation**: Apply `@Valid` on controller `@RequestBody` parameters.
- **Annotations**: Use `@NotBlank`, `@NotNull`, `@Size` on incoming request fields.
- **Lombok**: Use `@Getter`, `@Setter`, `@Builder`, `@NoArgsConstructor`, `@AllArgsConstructor` on DTO classes.
- **No Entity Exposure**: Entities are never exposed directly in REST responses; map explicitly to DTOs.

---

## 5. Error Handling & Exceptions
- **Centralized Advice**: Handled by `GlobalExceptionHandler` (`@RestControllerAdvice`).
- **Standardized Payload**: Return structured JSON with `status`, `error`, `message`, `timestamp`, and `errors` validation map.
- **No Raw Traces**: Never return internal stack traces or database driver details to clients.

---

## 6. Logging Standards
- **SLF4J**: Annotate classes with `@Slf4j` and use structured parameter interpolation:
  ```java
  log.info("Dispatching notification id={} via channel={}", notificationId, channel);
  log.error("Failed to send notification id={}: {}", notificationId, e.getMessage());
  ```
- **Masking**: Never log sensitive OTP codes, recipient tokens, or confidential attachment payloads in production logs.

---

## 7. Testing Standards
- **Frameworks**: JUnit 5, Mockito, Spring Boot Test (`@SpringBootTest`, `@AutoConfigureMockMvc`).
- **In-Memory Database**: Run automated tests against H2 (`jdbc:h2:mem:notificationdb;MODE=PostgreSQL`).
- **Mock Defaults**: Keep providers configured to `mock` in `src/test/resources/application.yml` for deterministic, offline test runs.
- **JDK Prerequisite**: GraalVM JDK 25 or OpenJDK 21 required to execute tests cleanly.

---

## 8. Database Migrations & Multi-Service Co-Location (Flyway)
- **Path**: `src/main/resources/db/migration/`
- **Naming Pattern**: `V{version}__{description}.sql` (e.g. `V1__init_notification_schema.sql`).
- **History Table Isolation**: When multiple microservices share the same PostgreSQL database (`hekmaai`), each service MUST configure its own Flyway schema history table with the service prefix first:
  ```yaml
  spring:
    flyway:
      table: ${FLYWAY_TABLE:<service>_flyway_schema_history}
      baseline-on-migrate: true
      baseline-version: 0
  ```
  Examples: `notification_flyway_schema_history`, `identity_flyway_schema_history`.
- **Baseline Version**: Always set `baseline-version: 0` so that if Flyway baselines an existing shared database, migration `V1` is executed rather than skipped.
- **Table & Index Prefixing**: All database objects created by a service MUST be prefixed with `<service>_` (tables: `<service>_*`, indexes: `<service>_idx_*`).
- **Immutability**: Never edit a migration script that has already been executed in an environment.

---


## 9. API Conventions
- **Base Paths**: Versioned under `/api/v1/` (e.g., `/api/v1/notifications/send`, `/api/v1/in-app-notifications`).
- **HTTP Status Codes**:
  - `200 OK`: Successful synchronous retrieval or state modification.
  - `202 Accepted`: Asynchronous dispatch accepted.
  - `400 Bad Request`: Validation failure.
  - `401 Unauthorized`: Missing or invalid `X-Hekma-Service-Key` or support session token.
  - `404 Not Found`: Target notification or support ticket not found.
  - `500 Internal Server Error`: Unhandled server failure.

---

## 10. Git & Agent Workflow Invariants
- **Strict Commit & Push Restriction**: Never execute `git commit` or `git push` unless explicitly ordered in the prompt.
- **Working Tree by Default**: All modifications remain uncommitted in the working tree for user review.
- **Strict Plan-Only Rule**: When asked to prepare a plan, produce ONLY planning documentation. Never modify application code directly.
