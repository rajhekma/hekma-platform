# Hekma Notification Service (`hekma-notification-service`)

## Purpose
The **Hekma Notification Service** is the centralized messaging, real-time alerting, persistent in-app notification center, and support helpdesk microservice for the Hekma Platform.

---

## Responsibilities
- Multi-channel outbound dispatch across `EMAIL`, `SMS`, `PUSH`, and `IN_APP` channels.
- Strategy Pattern (SPI) execution with pluggable live and mock delivery providers.
- Asynchronous task execution on a dedicated thread pool executor (`notificationTaskExecutor`), returning HTTP `202 Accepted` immediately.
- In-flight deduplication using caller-supplied `idempotencyKey` values.
- Dynamic template rendering with `{{variableName}}` placeholder interpolation.
- Multi-channel broadcast dispatch across a list of target channels.
- Persistent user inbox feed management (unread badge counts, pagination, bulk read transitions).
- Support Center & Helpdesk ticketing (public email OTP authentication, AWS S3 presigned attachment uploads, SLA tracking, and automated event notifications).

---

## Technology
- **Language**: Java 25 (GraalVM JDK 25 / OpenJDK 25; compiler release 21).
- **Framework**: Spring Boot `4.1.1` (Spring MVC, Spring Security, Spring Data JPA).
- **Mailing**: Spring Boot Starter Mail (`JavaMailSender` / Jakarta Mail) with SMTP.
- **Persistence**: PostgreSQL 14+ with Flyway Database Migration `12.4.0`.
- **Third-Party Providers**: Twilio SMS REST API, Firebase Cloud Messaging (FCM), AWS S3 SDK v2 (`software.amazon.awssdk:s3`), JJWT `0.12.6`.
- **API Documentation**: SpringDoc OpenAPI `3.1.0`.
- **Testing**: H2 In-Memory Database (`MODE=PostgreSQL`) and Spring Boot Test Starter.

---

## Important Components
- **`com.hekma.notification.service.NotificationDispatcherService`**: Orchestrates dispatching, template substitution, idempotency checks, and broadcast logic.
- **`com.hekma.notification.service.NotificationAsyncDispatcher`**: Executes channel handlers asynchronously on `notificationTaskExecutor` and updates status in an isolated transaction.
- **`com.hekma.notification.channel.NotificationChannelRegistry`**: SPI registry managing mapped channel handlers.
- **`com.hekma.notification.channel.email.EmailChannelHandler`**: Handles email delivery via `SmtpEmailProvider` or `MockEmailProvider`.
- **`com.hekma.notification.channel.sms.SmsChannelHandler`**: Handles SMS delivery via `TwilioSmsProvider` or `MockSmsProvider`.
- **`com.hekma.notification.channel.push.PushChannelHandler`**: Handles push alerts via `FirebasePushProvider` or `MockPushProvider`.
- **`com.hekma.notification.channel.inapp.InAppChannelHandler`**: Persists in-app notifications directly to `in_app_notifications`.
- **`com.hekma.notification.service.InAppNotificationService`**: Manages user inbox queries, pagination, and read acknowledgments.
- **`com.hekma.notification.support.service.SupportTicketService`**: Ticket lifecycle, comment feeds, SLA calculation, and status progression.
- **`com.hekma.notification.support.service.SupportOtpService`**: Public helpdesk email OTP verification and session token generation.
- **`com.hekma.notification.support.storage.AttachmentStorageProvider`**: SPI for presigned upload URLs (AWS S3 & Mock).
- **`com.hekma.notification.config.ApiKeyAuthFilter`**: Validates `X-Hekma-Service-Key` for inter-service security.

---

## APIs / Interfaces

### REST Endpoints (`/api/v1/`)
- **Internal Dispatching (`/api/v1/notifications`)** [Requires `X-Hekma-Service-Key`]:
  - `POST /send`: Dispatch a notification to a single channel (async or sync).
  - `POST /broadcast`: Dispatch a single notification simultaneously across multiple channels.
  - `GET /{id}`: Retrieve notification delivery log status by UUID.
- **In-App User Feed (`/api/v1/in-app-notifications`)** [Public]:
  - `GET /`: Paginated list of user notifications (`userId`, `unreadOnly`, `page`, `size`).
  - `GET /unread-count`: Real-time unread badge count for a user.
  - `PATCH /{id}/read`: Mark a single notification as read.
  - `PATCH /read-all`: Bulk mark all notifications as read for a user.
  - `DELETE /{id}`: Delete an in-app notification from user inbox.
- **Support Center (`/api/v1/support/`)**:
  - `POST /public/otp/send` & `/public/otp/verify`: Public email OTP handshake returning session token.
  - `POST /public/file-upload`: Generate presigned S3 PUT URL for pre-submit screenshot uploads.
  - `POST /public/tickets`: Submit a support ticket.
  - `GET /public/tickets/{id}` & `POST /public/tickets/{id}/comments`: Conversation thread.
  - `GET /categories` & `GET /summary`: Helpdesk metadata and personalized user stats.

---

## Database
- **Flyway Migrations**:
  - `V1__init_notification_tables.sql`: `notification_logs` and `in_app_notifications`.
  - `V2__create_support_center_tables.sql`: `support_ticket`, `support_ticket_comment`, `support_ticket_attachment`, `support_otp_session`, `support_audit_log`, `support_category_faq`.

---

## Dependencies
- Microservice dependencies: Invoked by `hekma-identity-service` and `hekma_api`.
- Outbound dependencies: SMTP server, Twilio API, Firebase FCM, AWS S3.

---

## Communication With Other Services
- Inbound: Accepts HTTP POST calls from `hekma-identity-service` for registration OTPs, welcome emails, and in-app alerts.
- Header: `X-Hekma-Service-Key` matching `hekma.security.service-api-key`.

---

## Authentication / Authorization
- Inter-service endpoints: Authenticated via static API key (`X-Hekma-Service-Key`).
- Public helpdesk endpoints: Authenticated via temporary HMAC-SHA256 session tokens (`X-Support-Otp-Token`) granted upon OTP email verification.
- Authenticated support endpoints: Authenticated via Bearer JWTs (`Authorization: Bearer <token>`).

---

## Important Rules
1. **SPI Decoupling**: All outbound delivery must go through `NotificationChannelHandler` and `AttachmentStorageProvider` implementations.
2. **Default Mock Safety**: In local and CI environments, providers default to `mock` so tests run without external credentials.
3. **Idempotency**: Requests with matching `idempotencyKey` return existing logs without duplicate dispatch.

---

## Current Status
- Production-ready multi-channel dispatcher, async executor, in-app feed, and support helpdesk module.
- 34 automated unit and integration tests passing with GraalVM JDK 25.

---

## Known Issues
- Twilio and Firebase FCM providers run in `mock` mode until live account credentials are configured in production environment variables.
