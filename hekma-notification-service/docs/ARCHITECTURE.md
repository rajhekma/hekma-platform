# System Architecture: Hekma Notification Service (`hekma-notification-service`)

## 1. High-Level Architectural Overview

The **Hekma Notification Service** is architected around the **Strategy Pattern (Channel SPI)**, separating channel dispatch orchestration from specific third-party provider integrations:

```mermaid
flowchart TD
    subgraph Clients ["Calling Microservices & Client Apps"]
        Identity["hekma-identity-service<br/>(OTP & Welcome Alerts)"]
        API["hekma_api<br/>(Clinical Alerts & Broadcasts)"]
        WebMobile["Web & Mobile Apps<br/>(In-App Notification Feed)"]
    end

    subgraph Service ["hekma-notification-service (Spring Boot 4.1.1 / Port 8081)"]
        AuthFilter["ApiKeyAuthFilter<br/>(Validates X-Hekma-Service-Key)"]
        DispatcherController["NotificationController<br/>(/api/v1/notifications/*)"]
        InAppController["InAppNotificationController<br/>(/api/v1/in-app-notifications/*)"]
        
        Dispatcher["NotificationDispatcherService<br/>(Idempotency, Template Rendering)"]
        AsyncDispatcher["NotificationAsyncDispatcher<br/>(@Async notificationTaskExecutor)"]
        Registry["NotificationChannelRegistry"]
        
        subgraph ChannelHandlers ["Channel Handlers (Strategy Pattern)"]
            EmailH["EmailChannelHandler"]
            SmsH["SmsChannelHandler"]
            PushH["PushChannelHandler"]
            InAppH["InAppChannelHandler"]
        end
    end

    subgraph Storage ["Persistent Store"]
        Postgres[("PostgreSQL Database<br/>notification_logs<br/>in_app_notifications")]
    end

    subgraph Providers ["Outbound Delivery Providers"]
        SmtpP["SmtpEmailProvider / Mock"]
        TwilioP["TwilioSmsProvider / Mock"]
        FcmP["PushProvider / Mock"]
        DbP["DatabaseInAppProvider"]
    end

    Identity -->|HTTP POST + X-Hekma-Service-Key| AuthFilter
    API -->|HTTP POST + X-Hekma-Service-Key| AuthFilter
    WebMobile -->|HTTP REST| InAppController

    AuthFilter --> DispatcherController
    DispatcherController --> Dispatcher
    Dispatcher --> AsyncDispatcher
    AsyncDispatcher --> Registry

    Registry --> EmailH
    Registry --> SmsH
    Registry --> PushH
    Registry --> InAppH

    EmailH --> SmtpP
    SmsH --> TwilioP
    PushH --> FcmP
    InAppH --> DbP

    Dispatcher -->|Audit Logs| Postgres
    DbP -->|Persist In-App Feed| Postgres
    InAppController --> Postgres
```

---

## 2. Component & Service Responsibilities

### 2.1 Security & Ingestion Layer
- **[ApiKeyAuthFilter.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/config/ApiKeyAuthFilter.java)**:
  - Intercepts incoming requests.
  - Validates the `X-Hekma-Service-Key` header against `hekma.security.service-api-key`.
  - Assigns `ROLE_INTERNAL_SERVICE` to authenticated callers.
  - Rejects unauthorized calls to `/api/v1/notifications/**` with HTTP `401 Unauthorized`.
  - Whitelists `/api/v1/in-app-notifications/**`, Actuator, and Swagger documentation.
- **[SecurityConfig.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/config/SecurityConfig.java)**:
  - Configures stateless session policy (`SessionCreationPolicy.STATELESS`).
  - Disables CSRF, form login, and HTTP basic auth.

### 2.2 Core Dispatching Engine
- **[NotificationDispatcherService.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/service/NotificationDispatcherService.java)**:
  - Orchestrates idempotency checks via `findByIdempotencyKey`.
  - Performs parameter substitution via [TemplateRenderer.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/service/TemplateRenderer.java).
  - Creates the initial `NotificationLog` entry with status `PENDING`.
  - Delegates execution to `NotificationAsyncDispatcher` (for async requests) or invokes channel handlers directly (for synchronous requests).
  - Implements multi-channel broadcasting iterating across requested channels.
- **[NotificationAsyncDispatcher.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/service/NotificationAsyncDispatcher.java)**:
  - Annotated with `@Async("notificationTaskExecutor")`.
  - Executes the target channel handler off the calling thread.
  - Updates the `NotificationLog` status to `SENT` or `FAILED` in an isolated transaction (`@Transactional(propagation = Propagation.REQUIRES_NEW)`).
- **[AsyncConfig.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/config/AsyncConfig.java)**:
  - Configures `ThreadPoolTaskExecutor` (`notificationTaskExecutor`) with core pool size 5, max pool size 20, queue capacity 500, and graceful shutdown (30 seconds await termination).

### 2.3 Channel Handler Strategy Pattern (SPI)
- **[NotificationChannelRegistry.java](file:///D:/coding/hekma/hekma-notification-service/src/main/java/com/hekma/notification/channel/NotificationChannelRegistry.java)**:
  - Discovers all Spring beans implementing `NotificationChannelHandler` at boot time and registers them in an `EnumMap`.
- Handlers:
  - **`EmailChannelHandler`**: Delegates to `EmailProvider` (`SmtpEmailProvider` via `JavaMailSender` or `MockEmailProvider`).
  - **`SmsChannelHandler`**: Delegates to `SmsProvider` (`TwilioSmsProvider` or `MockSmsProvider`).
  - **`PushChannelHandler`**: Delegates to `PushProvider` (`MockPushProvider` or live Firebase FCM).
  - **`InAppChannelHandler`**: Directly persists records in `in_app_notifications` table via `InAppNotificationRepository`.

---

## 3. Communication Patterns & External Integrations

### 3.1 Inter-Service Client Integration (`hekma-identity-service`)
- `hekma-identity-service` invokes `POST http://localhost:8081/api/v1/notifications/send` via its HTTP client `NotificationServiceClient`.
- Includes header: `X-Hekma-Service-Key: hekma-internal-secret-key-2026`.
- Payloads include channel (`EMAIL`, `SMS`, `IN_APP`), recipient address, title, content, priority, and `templateParams`.

### 3.2 External Third-Party Providers
- **SMTP Provider**: Connects to configured SMTP host (e.g. `smtp.gmail.com:587` with TLS authentication).
- **Twilio SMS Provider**: Connects to Twilio REST API using `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`.
- **Firebase FCM Push Provider**: Connects to Google Firebase using service account credentials.

---

## 4. Key Architectural Workflows

### 4.1 Asynchronous Notification Dispatch Flow

```mermaid
sequenceDiagram
    autonumber
    actor Service as Calling Microservice (Identity Service)
    participant Ctrl as NotificationController
    participant Disp as NotificationDispatcherService
    participant DB as PostgreSQL (notification_logs)
    participant Async as NotificationAsyncDispatcher
    participant Handler as NotificationChannelHandler
    participant Prov as Provider (SMTP / Twilio / Mock)

    Service->>Ctrl: POST /api/v1/notifications/send (async=true)
    Ctrl->>Disp: sendNotification(request)
    Disp->>DB: findByIdempotencyKey(key)
    Note over Disp,DB: Key not found, proceed
    Disp->>Disp: render(template, params)
    Disp->>DB: save(NotificationLog[status=PENDING])
    DB-->>Disp: savedLog (UUID)
    Disp->>Async: dispatchAsync(handler, context, logId)
    Disp-->>Ctrl: NotificationResponse(status=PENDING)
    Ctrl-->>Service: HTTP 202 Accepted (Immediately)

    Note over Async,Prov: Background Execution in Worker Thread
    Async->>Handler: handle(context)
    Handler->>Prov: deliver(recipient, content)
    Prov-->>Handler: NotificationResult(success=true)
    Handler-->>Async: NotificationResult
    Async->>DB: updateLogStatus(logId, status=SENT) [REQUIRES_NEW]
```

### 4.2 Multi-Channel Broadcast Flow

```mermaid
sequenceDiagram
    autonumber
    actor Service as Calling Microservice (Emergency Alert)
    participant Disp as NotificationDispatcherService
    participant Email as EmailChannelHandler
    participant SMS as SmsChannelHandler
    participant InApp as InAppChannelHandler

    Service->>Disp: POST /api/v1/notifications/broadcast (channels=[EMAIL, SMS, IN_APP])
    par Email Dispatch
        Disp->>Email: sendNotification(EMAIL, doctor@hekma.com)
    and SMS Dispatch
        Disp->>SMS: sendNotification(SMS, +966501234567)
    and In-App Dispatch
        Disp->>InApp: sendNotification(IN_APP, usr_9988)
    end
    Disp-->>Service: BroadcastNotificationResponse (totalDispatched=3, results=[...])
```

---

## 5. Detailed Channel Flows

For exhaustive lifecycle steps, provider implementations (Mock vs. SMTP vs. Twilio), payload formats, and delivery status tracking for each channel, see **[docs/NOTIFICATION_FLOW.md](file:///D:/coding/hekma/hekma-notification-service/docs/NOTIFICATION_FLOW.md)**.

---

## 6. Support Center Subsystem Architecture

The Support Center module provides end-to-end helpdesk tracking for both public (OTP-verified) and authenticated users:

```mermaid
flowchart TD
    subgraph PublicFlow["Public (Unauthenticated) Helpdesk Flow"]
        PUser["Participant"]
        OtpSend["POST /api/v1/support/public/otp/send"]
        OtpVerify["POST /api/v1/support/public/otp/verify"]
        PreUpload["POST /api/v1/support/public/file-upload"]
        CreateTicket["POST /api/v1/support/public/tickets"]
    end

    subgraph CoreSupport["Support Subsystem"]
        SupportCtrl["SupportPublicController & SupportController"]
        TicketService["SupportTicketService"]
        OtpService["SupportOtpService"]
        StorageSPI["AttachmentStorageProvider (SPI)"]
        S3Provider["AwsS3AttachmentStorageProvider (AWS SDK v2)"]
        MockProvider["MockAttachmentStorageProvider"]
        NotifBridge["SupportNotificationIntegrationService"]
    end

    subgraph InternalServices["Notification Core Engine"]
        Dispatcher["NotificationDispatcherService"]
    end

    subgraph DB["PostgreSQL Database"]
        SupportTables[("support_ticket, comments, attachments,<br/>history, SLA, OTP verification")]
    end

    PUser --> OtpSend --> OtpService
    PUser --> OtpVerify --> OtpService
    PUser --> PreUpload --> SupportCtrl
    PUser --> CreateTicket --> SupportCtrl

    SupportCtrl --> TicketService
    TicketService --> StorageSPI
    StorageSPI --> S3Provider
    StorageSPI --> MockProvider
    TicketService --> NotifBridge
    NotifBridge --> Dispatcher
    TicketService --> DB
    OtpService --> DB
```


