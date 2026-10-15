# System Architecture: Hekma Notification Service

## 1. High-Level Architecture Overview

The **Hekma Notification Service** operates as an event-driven, multi-channel outbound messaging engine and helpdesk service. It is architected around the **Strategy Pattern (Channel SPI)**, isolating dispatch orchestration from third-party provider APIs.

```
                      +---------------------------------------+
                      |         Calling Microservices         |
                      | (hekma-identity-service, hekma_api)   |
                      +-------------------+-------------------+
                                          |
                                          | HTTP POST + X-Hekma-Service-Key
                                          v
                      +---------------------------------------+
                      |           ApiKeyAuthFilter            |
                      | Validates service key -> ROLE_INTERNAL|
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |         NotificationController        |
                      |   /api/v1/notifications/send          |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |     NotificationDispatcherService     |
                      | 1. Evaluates Idempotency Key          |
                      | 2. Renders Template ({{var}})         |
                      | 3. Creates PENDING log in DB          |
                      +---------+-------------------+---------+
                                |                   |
             (async = false)    |                   | (async = true, default)
                                v                   v
                     [Direct Execution]    [NotificationAsyncDispatcher]
                                |          [@Async notificationTaskExecutor]
                                +---------+---------+
                                          |
                                          v
                      +---------------------------------------+
                      |      NotificationChannelRegistry      |
                      | Resolves handler: EMAIL, SMS, PUSH... |
                      +---------+---------+---------+---------+
                                |         |         |         |
                                v         v         v         v
                             +-----+   +-----+   +-----+   +-----+
                             |EMAIL|   | SMS |   |PUSH |   |INAPP|
                             +--+--+   +--+--+   +--+--+   +--+--+
                                |         |         |         |
                      +---------+---------+---------+---------+
                      | Pluggable Providers (Mock vs. Live)   |
                      | - SMTP (JavaMailSender)               |
                      | - Twilio SMS REST API                 |
                      | - Firebase Cloud Messaging (FCM)      |
                      | - DatabaseInAppProvider               |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |           PostgreSQL Database         |
                      | - notification_logs (Audit Record)    |
                      | - in_app_notifications (User Feed)    |
                      +---------------------------------------+
```

---

## 2. Major Services & Responsibilities

| Component / Service | Package | Primary Responsibilities |
| :--- | :--- | :--- |
| **`NotificationDispatcherService`** | `com.hekma.notification.service` | Validates payloads, evaluates idempotency deduplication, renders templates, creates initial `NotificationLog`, and coordinates broadcasts. |
| **`NotificationAsyncDispatcher`** | `com.hekma.notification.service` | Executes dispatching off the caller thread on `notificationTaskExecutor`. Updates status (`SENT` or `FAILED`) in an isolated transaction (`Propagation.REQUIRES_NEW`). |
| **`InAppNotificationService`** | `com.hekma.notification.service` | Manages persistent user inboxes, unread counts, paginated retrieval, and bulk read state transitions. |
| **`NotificationChannelRegistry`** | `com.hekma.notification.channel` | Dynamically discovers all beans implementing `NotificationChannelHandler` and registers them in a map keyed by `NotificationChannel`. |
| **`SupportTicketService`** | `com.hekma.notification.support.service` | Orchestrates support tickets, comment conversation threads, SLA calculation, and status progression. |
| **`SupportOtpService`** | `com.hekma.notification.support.service` | Issues 6-digit public email OTPs, hashes with SHA-256 + pepper, enforces 5-attempt limits, and issues session tokens. |
| **`AttachmentStorageProvider`** | `com.hekma.notification.support.storage` | Storage SPI for presigned upload URLs and multipart downloads (`AwsS3AttachmentStorageProvider` vs `MockAttachmentStorageProvider`). |
| **`ApiKeyAuthFilter`** | `com.hekma.notification.config` | Header-based security filter validating `X-Hekma-Service-Key` for internal inter-service endpoints. |

---

## 3. Communication Patterns & External Integrations

### 3.1 Asynchronous Delivery Pipeline
1. Caller sends `POST /api/v1/notifications/send` (default: `async = true`).
2. Service validates payload and checks `idempotencyKey` against `notification_logs`.
3. An initial log record is saved with status `PENDING`.
4. `NotificationAsyncDispatcher.dispatchAsync(...)` is called asynchronously, and HTTP `202 Accepted` is returned immediately.
5. In the background thread pool, the channel handler invokes the configured provider (e.g. SMTP, Twilio, FCM).
6. Result status is committed to `notification_logs` in a `REQUIRES_NEW` transaction.

### 3.2 External Integrations
- **SMTP**: Connects to `smtp.gmail.com:587` (or custom host) via Spring Mail `JavaMailSender` using TLS/StartTLS.
- **Twilio SMS**: Outbound REST calls via Twilio SDK using Account SID and Auth Token.
- **Firebase FCM**: Push notification delivery using Firebase Admin SDK credentials.
- **AWS S3**: Issues presigned PUT/GET URLs for helpdesk attachment uploads via AWS SDK v2.

---

## 4. Security & Authentication Architecture

- **Inter-Service Protection**: Endpoints under `/api/v1/notifications/**` require `X-Hekma-Service-Key` matching `hekma.security.service-api-key`.
- **Public In-App Feed**: Endpoints under `/api/v1/in-app-notifications/**` are public for direct client application consumption.
- **Support Center Authentication**:
  - Unauthenticated participants authenticate via public email OTP to obtain an HMAC-SHA256 session token (`X-Support-Otp-Token`).
  - Authenticated clinical staff authenticate via standard Bearer tokens (`Authorization: Bearer <jwt>`).

---

## 5. Persistence & Database Architecture

- **Flyway Migrations**:
  - `V1__init_notification_tables.sql`: `notification_logs` (UUID PK, idempotency index) and `in_app_notifications` (UUID PK, `(user_id, is_read)` index).
  - `V2__create_support_center_tables.sql`: `support_ticket`, `support_ticket_comment`, `support_ticket_attachment`, `support_otp_session`, `support_audit_log`, `support_category_faq`.
- **Entity Conventions**: UUID primary keys generated in `@PrePersist` callbacks; UTC timestamps (`createdAt`, `updatedAt`) managed automatically.

---

## 6. Important Architectural Constraints

1. **Provider Isolation**: Business services must NEVER call third-party APIs (Twilio, AWS, JavaMail) directly. All outbound I/O must pass through the `NotificationChannelHandler` or `AttachmentStorageProvider` interfaces.
2. **Default Mock Mode**: All providers default to `mock` in `application.yml` and test profiles so the service builds, boots, and tests cleanly without third-party network access.
3. **Idempotency Invariant**: Any retry containing an identical `idempotencyKey` must return the existing log and skip duplicate transmission.
