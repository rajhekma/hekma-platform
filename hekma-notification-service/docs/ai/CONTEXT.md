# Hekma Notification Service — AI Project Context

## Project
- **Name**: `hekma-notification-service`
- **Description**: Centralized multi-channel outbound messaging, persistent in-app notification center, and support helpdesk microservice for the Hekma Platform.
- **Business/Domain Purpose**: Powers real-time clinical trial communications, authentication OTP deliveries (SMS/Email), participant onboarding confirmations, protocol amendment alerts, and participant support ticket helpdesk workflows across the decentralized clinical trial ecosystem.

---

## Technology Stack
- **Language & Runtime**: Java 25 (GraalVM JDK 25 / OpenJDK 25; compiler release 21).
- **Framework**: Spring Boot `4.1.1` (Spring Framework 7.x, Spring MVC, Spring Security, Spring Data JPA).
- **Database & Migrations**: PostgreSQL 14+; Flyway Database Migration `12.4.0` (`V1`, `V2`). Test database: H2 in-memory (`MODE=PostgreSQL`).
- **Mailing**: Spring Boot Starter Mail (`JavaMailSender` / Jakarta Mail) with SMTP delivery.
- **Third-Party Providers & SDKs**: Twilio SMS SDK, Firebase Cloud Messaging (FCM), AWS S3 SDK v2 (`software.amazon.awssdk:s3` for presigned attachment URLs), JJWT `0.12.6` (support session tokens).
- **API Documentation**: SpringDoc OpenAPI `3.1.0` (Swagger UI on port 8081).
- **Build Tool**: Maven (`mvnw` / `mvnw.cmd`).
- **Code Generation**: Project Lombok, Jackson (`JavaTimeModule`).

---

## Architecture Summary
- **Channel Strategy Pattern (SPI)**: Channel handlers (`EmailChannelHandler`, `SmsChannelHandler`, `PushChannelHandler`, `InAppChannelHandler`) implement `NotificationChannelHandler` and are dynamically registered at startup in `NotificationChannelRegistry`.
- **Pluggable Provider Architecture**: Each channel delegates to decoupled providers with dual implementations:
  - *Email*: `SmtpEmailProvider` (live SMTP via Gmail/AWS SES) vs. `MockEmailProvider` (console/log).
  - *SMS*: `TwilioSmsProvider` vs. `MockSmsProvider`.
  - *Push*: `FirebasePushProvider` vs. `MockPushProvider`.
  - *Support Storage*: `AwsS3AttachmentStorageProvider` (presigned S3 URLs) vs. `MockAttachmentStorageProvider`.
- **Asynchronous Worker Pool**: Non-blocking dispatch via `NotificationAsyncDispatcher` executing on a managed `ThreadPoolTaskExecutor` (`notificationTaskExecutor`), returning HTTP `202 Accepted` immediately. Status is updated in an isolated transaction (`Propagation.REQUIRES_NEW`).
- **Idempotency Safeguard**: In-flight deduplication via `idempotency_key` indexed on `notification_logs`, preventing duplicate OTPs or notifications upon network retries.
- **Template Rendering**: In-line parameter substitution engine supporting `{{variableName}}` placeholders.
- **Support Center Subsystem**: Multi-tenant clinical helpdesk supporting public email OTP verification, presigned S3 screenshot uploads, SLA tracking, and ticket conversations.
- **Inter-Service Security**: Header-based authentication using `X-Hekma-Service-Key` validated by `ApiKeyAuthFilter`.

---

## Repository Structure
```text
hekma-notification-service/
├── docs/                          # Architecture diagrams, delivery flows & schema specs
│   ├── ai/                        # AI progressive disclosure context system
│   │   ├── services/              # Service context (notification.md)
│   │   ├── ARCHITECTURE.md        # Detailed SPI design & async execution flows
│   │   ├── CONTEXT.md             # This entry point (~800 words)
│   │   ├── CONVENTIONS.md         # Coding, testing, and error handling standards
│   │   ├── CURRENT.md             # Active focus, recent milestones, and blockers
│   │   └── DECISIONS.md           # Architecture Decision Records (ADRs)
│   ├── API_DOCUMENTATION.md       # OpenAPI endpoint catalogs and request/response DTOs
│   ├── ARCHITECTURE.md            # Deep system architecture & Mermaid diagrams
│   ├── DATABASE.md                # PostgreSQL schema & Flyway migrations (V1, V2)
│   ├── DEVELOPMENT_LOG.md         # Chronological milestones & feature history
│   ├── NOTIFICATION_FLOW.md       # End-to-end delivery flows across all 4 channels
│   └── PROJECT_CONTEXT.md         # Business domain requirements & support workflows
├── src/main/java/com/hekma/notification/
│   ├── channel/                   # Channel SPI interfaces, registry, and handlers
│   │   ├── email/                 # Email handlers & providers (Mock, SMTP)
│   │   ├── inapp/                 # In-app persistent inbox handler
│   │   ├── push/                  # Push notification handlers & providers
│   │   └── sms/                   # SMS handlers & providers (Mock, Twilio)
│   ├── config/                    # Security, ApiKeyAuthFilter, Async & OpenAPI config
│   ├── controller/                # NotificationController & InAppNotificationController
│   ├── domain/                    # JPA entities (NotificationLog, InAppNotification) & enums
│   ├── dto/                       # Request/Response DTOs & PagedResponse wrappers
│   ├── service/                   # NotificationDispatcherService, AsyncDispatcher, TemplateRenderer
│   └── support/                   # Clinical support helpdesk module (tickets, OTP, attachments)
├── src/main/resources/
│   ├── db/migration/              # Flyway migrations (V1__init, V2__create_support_center)
│   └── application.yml            # Port 8081 configuration & provider routing
├── src/test/                      # Integration & unit test suites (H2 in-memory DB)
├── AGENTS.md                      # Instructions and safety boundaries for AI coding agents
├── CLAUDE.md                      # Claude-specific entry point to shared context
├── pom.xml                        # Maven dependencies & build configuration
└── README.md                      # Service overview, setup guide, and tech stack
```

---

## Important Rules for AI Agents
1. **Strict Plan-Only Boundary**: When asked to prepare a plan, produce ONLY planning documentation. NEVER modify application code or migrations without explicit user approval.
2. **Strict Commit & Push Restriction**: NEVER run `git commit` or `git push` unless explicitly asked in the prompt. All modifications must remain uncommitted in the working tree.
3. **Preserve Developer Edits**: Never revert uncommitted configuration edits in `application.yml` (e.g. customized SMTP or Twilio properties).
4. **Inter-Service Security**: All endpoints under `/api/v1/notifications/**` require `X-Hekma-Service-Key`. In-app feed endpoints (`/api/v1/in-app-notifications/**`) and support endpoints remain public.
5. **Mock Provider Safety**: In local dev and test environments, keep default providers set to `mock` so the build and tests execute cleanly without external credentials.
6. **JDK Prerequisite**: Use GraalVM JDK 25 or OpenJDK 21 for Maven runs:
   ```powershell
   $env:JAVA_HOME="C:\Users\Acer_PTS\.jdks\graalvm-jdk-25"; $env:Path="$env:JAVA_HOME\bin;" + $env:Path
   .\mvnw.cmd test
   ```

---

## Context Navigation
Progressively navigate into detailed documentation only when relevant to your task:

- **[CURRENT.md](file:///D:/coding/hekma/hekma-notification-service/docs/ai/CURRENT.md)**: Current development state, active focus, completed milestones, and blockers.
- **[ARCHITECTURE.md](file:///D:/coding/hekma/hekma-notification-service/docs/ai/ARCHITECTURE.md)**: Channel SPI design, async task executor details, and support module architecture.
- **[DECISIONS.md](file:///D:/coding/hekma/hekma-notification-service/docs/ai/DECISIONS.md)**: Architecture Decision Records (ADRs) explaining technical design trade-offs.
- **[CONVENTIONS.md](file:///D:/coding/hekma/hekma-notification-service/docs/ai/CONVENTIONS.md)**: Coding, naming, DTO, logging, testing, and error-handling standards.
- **[services/notification.md](file:///D:/coding/hekma/hekma-notification-service/docs/ai/services/notification.md)**: Detailed module guide for `hekma-notification-service`.
