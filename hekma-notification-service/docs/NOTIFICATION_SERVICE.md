# Notification & Support Service

**Service:** `hekma-notification-service` · **Port:** 8083 · **Role:** Multi-Channel Messaging, Templates & Help Desk

This is the centralized communications hub and customer support desk microservice for the Hekma platform. It handles delivery of SMS, Email, Push notifications, and In-App alerts, as well as the support ticket lifecycle with SLA tracking.

It is **not** Identity (does not authenticate credentials), **not** CTMS, and **not** Appointment (does not decide when a visit occurs; it only delivers the notification message requested by other services).

---

## What it supports

| Component | What the user sees | Owns |
|-----------|--------------------|------|
| **1 · Multi-Channel Dispatch** | SMS codes, emails, push alerts, in-app bell | Delivery pipelines (SendGrid, Twilio, FCM, In-App database store) |
| **2 · Dynamic Template Rendering** | Branded email & SMS text with user names | Template catalog, parameter substitution, multi-language rendering |
| **3 · Support Ticket Desk** | "Submit a ticket / Contact Support" | Public & staff support tickets, comments, assignment workflows |
| **4 · SLA Tracking & Audit Log** | Ticket response timers, resolution metrics | SLA compliance tracking, full chronological timeline of ticket events |
| **5 · Secure Attachment Storage** | Screenshots / diagnostic files attached to tickets | S3 Presigned upload URLs, attachment metadata storage |

---

## High-level architecture

```mermaid
flowchart TB
    APP[Patient / Staff / External] --> GW[API Gateway :9080]
    GW --> NOTIF

    subgraph NOTIF ["hekma-notification-service :8083"]
        DISPATCH[Notification Dispatcher]
        TEMPLATES[Template Renderer]
        SUPPORT[Support Ticket Engine]
        SLA[SLA Tracker]
        ATTACH[Attachment Storage Provider]
        
        DISPATCH --> TEMPLATES
        SUPPORT --> SLA & ATTACH
    end

    ID[Identity :8080] -->|Send OTP SMS/Email| DISPATCH
    APPT[Appointment :8082] -->|Send Visit Reminders| DISPATCH
    
    DISPATCH -->|Email| SG[(SendGrid API)]
    DISPATCH -->|SMS| TW[(Twilio / Mock SMS)]
    DISPATCH -->|Push| FCM[(Firebase Cloud Messaging)]
    NOTIF -->|Tables: notification_*| PG[(PostgreSQL · hekma_platform)]
    ATTACH -->|File uploads| S3[(Amazon S3 Storage)]
```

**Rule:** Other microservices never talk directly to email or SMS gateways. All communication requests must flow through this service so audit logs, delivery statuses, and templates are centrally managed.

---

## Request path (every call)

```mermaid
flowchart LR
    R[Request] --> PUB{Public Endpoint?<br/>e.g. /support/public/**}
    PUB -->|yes| OTP{Public Ticket OTP Valid?}
    OTP -->|no| U[401 / 400]
    OTP -->|yes| C[Execute Public Support Action]
    PUB -->|no| AUTH{Has Valid Bearer Token?}
    AUTH -->|no| U2[401 Unauthorized]
    AUTH -->|yes| PERM{Has Staff Permission?}
    PERM -->|no| F[403 Forbidden]
    PERM -->|yes| C2[Execute Staff / Dispatch Action]
```

---

## 1 · Multi-Channel Notification Dispatch

Accepts notification payloads from internal services or staff operators and delivers them across configured channels.

```mermaid
sequenceDiagram
    participant Caller as Caller (Identity / Appointment)
    participant API as NotificationController
    participant Svc as NotificationDispatcherService
    participant SG as SendGrid / Twilio
    participant DB as PostgreSQL

    Caller->>API: POST /api/v1/notifications/send { channel: "EMAIL", recipient, templateId, params }
    API->>Svc: dispatch(request)
    Svc->>Svc: Render template with parameters
    Svc->>SG: Send message payload
    Svc->>DB: Log delivery attempt & status (SENT / FAILED)
    API-->>Caller: 200 OK { messageId, status: "SENT" }
```

| API | Purpose |
|-----|---------|
| `POST /api/v1/notifications/send` | Generic multi-channel notification dispatch |
| `GET /api/v1/notifications/in-app/{userId}` | Fetch in-app notifications for bell icon dropdown |
| `PUT /api/v1/notifications/in-app/{id}/read` | Mark in-app alert as read |

---

## 2 · Support Ticket Desk & Lifecycle

Complete customer support and bug reporting engine. Supports both authenticated staff and unauthenticated public visitors (via email OTP).

```mermaid
stateDiagram-v2
    [*] --> OPEN: Ticket Created
    OPEN --> IN_PROGRESS: Assigned to staff agent
    IN_PROGRESS --> PENDING_CUSTOMER: Awaiting info from user
    PENDING_CUSTOMER --> IN_PROGRESS: User responded
    IN_PROGRESS --> RESOLVED: Fix or answer provided
    RESOLVED --> CLOSED: Confirmed closed
```

| API | Purpose |
|-----|---------|
| `POST /api/v1/support/public/otp/send` | Send OTP to verify email before submitting public ticket |
| `POST /api/v1/support/public/tickets` | Submit verified public support ticket |
| `GET /api/v1/support/tickets` | Staff view and filter ticket queue (`support:read`) |
| `GET /api/v1/support/tickets/{id}` | Detailed ticket view with comments & timeline |
| `POST /api/v1/support/tickets/{id}/comments` | Add public reply or internal staff note |
| `PATCH /api/v1/support/tickets/{id}` | Update status, priority, or assigned agent |

---

## 3 · Attachment Storage (S3 Presigned URLs)

Allows uploading screenshots and diagnostic attachments without routing heavy file bytes through the backend server.

| API | Purpose |
|-----|---------|
| `POST /api/v1/support/attachments/presigned-url` | Generate secure S3 PUT upload URL |

---

## Where it sits on the platform

```mermaid
flowchart LR
    ID[1 Identity :8080] -->|Dispatch OTP & invites| NOTIF[Notification :8083]
    APPT[Appointment :8082] -->|Dispatch visit reminders| NOTIF
    CTMS[2 CTMS :8081] -.->|Dispatch trial alerts| NOTIF
```

| This service does | Another service does |
|-------------------|----------------------|
| Multi-channel messaging (Email, SMS, Push, In-App) | Identity: Auth, login, tenant hierarchy |
| Customer support desk & ticket SLAs | Appointment: Calendar slots & conflict detection |
| Communications audit log | CTMS: Studies, protocols, adverse events |

---

## Data stores

| Store | Used for |
|-------|----------|
| PostgreSQL (`hekma_platform`) | `notification_logs`, `notification_templates`, `support_tickets`, `support_comments`, `support_sla_tracking` |
| Amazon S3 | Ticket attachments, screenshots, and crash logs |

---

## Run & Test

```powershell
cd hekma-notification-service
$env:JAVA_HOME="C:\Users\Acer_PTS\.jdks\graalvm-jdk-25"; $env:Path="$env:JAVA_HOME\bin;" + $env:Path
.\mvnw.cmd test
.\mvnw.cmd spring-boot:run
```
