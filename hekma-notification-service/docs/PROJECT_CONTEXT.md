# Project Context: Hekma Notification Service (`hekma-notification-service`)

## 1. Project Overview & Business Purpose

The **Hekma Notification Service** is the centralized communication and outbound messaging microservice for the **Hekma Platform**.

In a clinical trial and digital health ecosystem, diverse events require timely, reliable, and auditable delivery across multiple channels:
- **Authentication & Security Events**: Dispatching 6-digit One-Time Passwords (OTPs) and security verification codes to trial participants and investigators via SMS and Email (orchestrated by `hekma-identity-service`).
- **Patient Engagement & Onboarding**: Sending welcome notifications, terms updates, and study onboarding confirmations.
- **Clinical Alerts & Monitoring**: Delivering high-priority trial broadcast alerts, investigator notifications, and protocol amendment alerts.
- **User Dashboard Activity**: Feeding persistent, in-app notification centers where patients and investigators can review unread announcements and trial milestones.

---

## 2. Core Capabilities & Functional Workflows

### 2.1 Multi-Channel Support

The notification engine supports four primary communication channels defined in [NotificationChannel.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/domain/model/NotificationChannel.java):

| Channel | Purpose | Delivery Format | Supported Providers |
| :--- | :--- | :--- | :--- |
| **`EMAIL`** | OTPs, welcome emails, study reports, regulatory disclosures | HTML & plain text | `MockEmailProvider` (console/log), `SmtpEmailProvider` (`JavaMailSender` / Jakarta Mail) |
| **`SMS`** | High-priority OTPs and urgent verification codes | Plain text SMS | `MockSmsProvider` (console/log), `TwilioSmsProvider` |
| **`PUSH`** | Mobile and web device push alerts | Push notification payload | `MockPushProvider` (console/log), Firebase Cloud Messaging (FCM) |
| **`IN_APP`** | Persistent inbox & notification center | Relational database record in `in_app_notifications` | `InAppChannelHandler` (PostgreSQL / Spring Data JPA) |

### 2.2 Template Rendering Engine

The service features a lightweight variable substitution engine ([TemplateRenderer.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/service/TemplateRenderer.java)):
- Placeholders follow the double curly-brace convention: `{{variableName}}`.
- Callers supply a key-value map in `templateParams` (e.g. `{"name": "Alice", "code": "654321"}`).
- Both `title` and `content` fields undergo variable substitution prior to channel dispatch.

### 2.3 Idempotency & Deduplication

To safeguard against network retries and duplicate transmissions (such as double OTP dispatches or repeated billing/alert notifications):
- Callers may provide an `idempotencyKey` string in the request payload.
- [NotificationDispatcherService.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/service/NotificationDispatcherService.java) queries `notification_logs` for any existing entry matching the key.
- If found, duplicate dispatching is bypassed, and the existing `NotificationResponse` is returned immediately.

### 2.4 Asynchronous Task Execution

- By default (`async = true`), requests to `POST /api/v1/notifications/send` are persisted with status `PENDING` and handed off to a managed thread pool executor (`notificationTaskExecutor`), returning `202 Accepted` immediately.
- The background worker executes the channel provider and updates the log record status to `SENT` or `FAILED` in a separate transaction (`REQUIRES_NEW`).
- Synchronous execution (`async = false`) is supported when calling microservices require immediate delivery confirmation before completing their transaction.

### 2.5 In-App Notification Center & Feed

The service maintains a persistent user notification feed ([InAppNotificationService.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/service/InAppNotificationService.java)):
- Paginated retrieval of user notifications (`GET /api/v1/in-app-notifications?userId={userId}&unreadOnly={true|false}`).
- Real-time unread badge count (`GET /api/v1/in-app-notifications/unread-count?userId={userId}`).
- Single notification read acknowledgment (`PATCH /api/v1/in-app-notifications/{id}/read`).
- Bulk read acknowledgment (`PATCH /api/v1/in-app-notifications/read-all?userId={userId}`).
- Inbox deletion (`DELETE /api/v1/in-app-notifications/{id}`).

### 2.6 Support Tickets & Helpdesk Center Module

The service hosts the centralized Support Center migrated from `hekma_api`:
- **Public Helpdesk Flow (`/api/v1/support/public/**`)**: Unauthenticated trial participants verify email via a 6-digit OTP challenge (`/otp/send` and `/otp/verify`) to obtain a short-lived `X-Support-Otp-Token` session. Users can request presigned S3 PUT URLs for pre-submit screenshots (`/file-upload`), submit tickets (`POST /tickets`), inspect ticket conversations (`GET /tickets/{id}`), reply (`POST /tickets/{id}/comments`), and escalate (`POST /tickets/{id}/escalate`).
- **Authenticated User Flow (`/api/v1/support/**`)**: Authenticated clinical portal users and mobile users retrieve issue categories (`GET /categories`), access personalized ticket statistics (`GET /summary`), and upload multipart attachments (`POST /tickets/{id}/attachments`).
- **Attachment Storage SPI**: Decoupled via `AttachmentStorageProvider` supporting production AWS S3 presigned URLs (`AwsS3AttachmentStorageProvider`) and a zero-credential mock provider (`MockAttachmentStorageProvider`) for seamless CI/local development.
- **Automated Event Notifications**: Lifecycle events (`TICKET_CREATED`, `ASSIGNED`, `AGENT_REPLY`, `TICKET_ESCALATED`, `STATUS_CHANGED`) automatically dispatch notifications through the existing `NotificationDispatcherService` (`EMAIL` and `IN_APP`).

---

## 3. Services, Modules & Boundaries

| Component / Service | Package | Primary Responsibility |
| :--- | :--- | :--- |
| **Notification Dispatcher** | `com.hekma.notification.service.NotificationDispatcherService` | Main entry point for dispatching, template rendering, idempotency evaluation, and multi-channel broadcast |
| **Async Dispatcher** | `com.hekma.notification.service.NotificationAsyncDispatcher` | Background execution on `notificationTaskExecutor` with isolated status update transactions |
| **In-App Notification Service** | `com.hekma.notification.service.InAppNotificationService` | User feed management, unread counting, pagination, and read-state transitions |
| **Channel Registry** | `com.hekma.notification.channel.NotificationChannelRegistry` | Service Provider Interface (SPI) registry holding mapped handlers for `EMAIL`, `SMS`, `PUSH`, and `IN_APP` |
| **Support Ticket Service** | `com.hekma.notification.support.service.SupportTicketService` | Ticket lifecycle management, comment conversation feeds, SLA tracking, audit logging, and attachment linking |
| **Support OTP Service** | `com.hekma.notification.support.service.SupportOtpService` | Public email OTP generation, salted SHA-256 verification, brute-force locking, and session token resolution |
| **Support Storage Provider** | `com.hekma.notification.support.storage.AttachmentStorageProvider` | Pluggable SPI for presigned upload/download URLs and multipart storage (AWS S3 & Mock) |
| **Support Notification Integration** | `com.hekma.notification.support.service.SupportNotificationIntegrationService` | Bridges support ticket events to email and in-app channels via `NotificationDispatcherService` |
| **Support Controllers** | `com.hekma.notification.support.controller.*` | `SupportPublicController` (OTP & unauthenticated flow) and `SupportController` (categories, summary, auth attachments) |
| **Security Filter** | `com.hekma.notification.config.ApiKeyAuthFilter` | Header-based inter-service authentication enforcing `X-Hekma-Service-Key` |
| **Controllers** | `com.hekma.notification.controller.*` | `NotificationController` (inter-service) and `InAppNotificationController` (user feed) |

---

## 4. Key Business Rules & Invariants

1. **Inter-Service Authentication Invariant**:
   - Every request to `/api/v1/notifications/**` must include the `X-Hekma-Service-Key` header matching `hekma.security.service-api-key`. Missing or mismatched keys return HTTP `401 Unauthorized`.
   - In-app notification endpoints (`/api/v1/in-app-notifications/**`) are public to allow direct client application integration without leaking internal service keys.
2. **Auditability Invariant**:
   - Every outbound notification attempt (successful or failed) must produce an immutable audit record in `notification_logs` capturing channel, recipient, content, delivery status, and error messages if applicable.
3. **Pluggable Mock Safety**:
   - In development and CI environments, providers must default to `mock` so that test suites execute without requiring live external network credentials (Twilio, Firebase FCM, or Gmail SMTP).

---

## 5. Current Development Status & Known Limitations

- **Current Status**: All four communication channels (`EMAIL`, `SMS`, `PUSH`, `IN_APP`), the async dispatcher, template rendering, idempotency safeguards, and in-app feed endpoints are implemented and verified with **17 passing automated unit and integration tests**.
- **Known Limitations & Future Roadmap**:
  - **Message Broker Integration**: Currently communicates via synchronous HTTP REST from calling microservices. Future versions will introduce Apache Kafka or RabbitMQ event listeners for decoupled reactive event consumption.
  - **Rich Template Storage**: Templates are currently passed inline in request bodies with parameter substitution. A future milestone will introduce versioned template storage in PostgreSQL.
