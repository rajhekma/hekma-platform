# Hekma Notification Service

A Spring Boot microservice designed to handle and dispatch notifications across the Hekma platform.

## Overview

The **Hekma Notification Service** serves as the centralized notification engine and Support Center for all Hekma microservices (`hekma-identity-service`, `hekma_api`, background pipelines). It supports multi-channel dispatching with a pluggable provider SPI (Strategy Pattern), background asynchronous execution, audit logging, in-app user feed management, and full-lifecycle support ticketing with OTP verification and file attachment storage.

### Supported Channels

| Channel | Description | Providers | Recipient Format |
| :--- | :--- | :--- | :--- |
| **`EMAIL`** | Plain-text & HTML emails | `mock` (default), `smtp` (JavaMailSender) | Email address (e.g. `user@hekma.com`) |
| **`SMS`** | Text messaging & OTPs | `mock` (default), `twilio` | E.164 phone number (e.g. `+966501234567`) |
| **`PUSH`** | Mobile & Web push alerts | `mock` (default), `firebase` (FCM) | Device registration token |
| **`IN_APP`** | Persistent inbox & notification feed | `DatabaseInAppProvider` (PostgreSQL) | User ID (e.g. `usr_12345`) |

---

## Architecture & Features

- **Strategy Pattern (Channel SPI)**: Channels and providers are decoupled into modular handlers (`EmailChannelHandler`, `SmsChannelHandler`, `PushChannelHandler`, `InAppChannelHandler`) managed by a `NotificationChannelRegistry`.
- **Support Center & Ticketing**: Complete ticket lifecycle management (public guest tickets with OTP email/SMS verification, authenticated user tickets, comments, SLA tracking, priority escalation, and timeline audit logs).
- **Pluggable Attachment Storage**: Multi-provider storage SPI for ticket attachments (`MockAttachmentStorageProvider` for zero-credential testing, `AwsS3AttachmentStorageProvider` with presigned S3 URLs).
- **Automated Ticket Notifications**: Bridges ticket events (`TICKET_CREATED`, `ASSIGNED`, `AGENT_REPLY`, `TICKET_ESCALATED`, `STATUS_CHANGED`) directly into the notification dispatcher.
- **Mock & Live Modes**: Runs out-of-the-box in `mock` mode for seamless local development and CI testing without external third-party credentials.
- **Asynchronous Dispatching**: Notifications execute asynchronously via a managed thread pool (`ThreadPoolTaskExecutor`) by default, preventing latency on calling microservices.
- **Idempotency**: Prevents duplicate sends by supplying an `idempotencyKey`.
- **Template Rendering**: Parameterized variable substitution (e.g., `{{name}}`, `{{code}}`).
- **Audit Logging**: Every dispatch attempt is recorded in `notification_logs` with delivery status (`PENDING`, `SENT`, `FAILED`).
- **Service Security**: Inter-service endpoints are secured via the `X-Hekma-Service-Key` header.

---

## Tech Stack

- **Java**: 25 (GraalVM JDK 25)
- **Framework**: Spring Boot 4.x
- **Web & Security**: Spring MVC, Spring Security
- **Data & Migration**: Spring Data JPA, Hibernate, PostgreSQL, Flyway
- **Mailing**: Spring Boot Starter Mail (`JavaMailSender`)
- **API Documentation**: SpringDoc OpenAPI 3.0 (Swagger UI)
- **Build Tool**: Maven Wrapper (`mvnw`)
- **Utilities**: Lombok, Jackson (with `JavaTimeModule`)

---

## Configuration

Service configuration is defined in [`src/main/resources/application.yml`](src/main/resources/application.yml).

### Key Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `SERVER_PORT` | HTTP server port | `8081` |
| `SPRING_DATASOURCE_URL` | PostgreSQL connection URL | `jdbc:postgresql://localhost:5432/hekma-notification` |
| `SPRING_DATASOURCE_USERNAME` | PostgreSQL username | `xatsuser` |
| `SPRING_DATASOURCE_PASSWORD` | PostgreSQL password | `p@ssw0rd` |
| `HEKMA_SERVICE_API_KEY` | Shared secret header (`X-Hekma-Service-Key`) | `hekma-internal-secret-key-2026` |
| `EMAIL_PROVIDER` | Email provider (`mock` or `smtp`) | `mock` |
| `EMAIL_DEFAULT_SENDER` | Default sender address for outgoing emails | `no-reply@hekma.com` |
| `SMS_PROVIDER` | SMS provider (`mock` or `twilio`) | `mock` |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | _empty_ |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | _empty_ |
| `TWILIO_FROM_NUMBER` | Twilio sender phone number | _empty_ |
| `PUSH_PROVIDER` | Push provider (`mock` or `firebase`) | `mock` |

---

## API Reference

### 1. Inter-Service Notification Endpoints
> Header required: `X-Hekma-Service-Key: <your-service-key>`

#### Send a Notification
`POST /api/v1/notifications/send`

**Request Body:**
```json
{
  "channel": "EMAIL",
  "recipient": "patient@hekma.com",
  "title": "Welcome {{name}}",
  "content": "Your appointment is confirmed for tomorrow. Code: {{code}}",
  "priority": "HIGH",
  "templateParams": {
    "name": "Sarah",
    "code": "84729"
  },
  "sourceService": "hekma-identity-service",
  "idempotencyKey": "req-98234-uuid",
  "async": true
}
```

**Response (HTTP 202 Accepted):**
```json
{
  "id": "e8a93a10-2b1c-4b5f-9e67-0c7f66a87b92",
  "channel": "EMAIL",
  "recipient": "patient@hekma.com",
  "status": "PENDING",
  "createdAt": "2026-09-30T01:00:00Z"
}
```

#### Broadcast to Multiple Channels
`POST /api/v1/notifications/broadcast`

**Request Body:**
```json
{
  "channels": ["EMAIL", "SMS", "IN_APP"],
  "email": "doctor@hekma.com",
  "phone": "+966501234567",
  "userId": "usr_9988",
  "title": "Critical Emergency Alert",
  "content": "Patient vitals threshold exceeded in Room 304.",
  "priority": "URGENT",
  "sourceService": "hekma_api"
}
```

#### Get Delivery Status
`GET /api/v1/notifications/{id}/status`

---

### 2. In-App Notification Feed Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/in-app-notifications?userId={userId}&unreadOnly=false&page=0&size=20` | Get paginated notification feed for a user |
| `GET` | `/api/v1/in-app-notifications/unread-count?userId={userId}` | Get unread badge count |
| `PATCH` | `/api/v1/in-app-notifications/{id}/read` | Mark a notification as read |
| `PATCH` | `/api/v1/in-app-notifications/read-all?userId={userId}` | Mark all notifications as read |
| `DELETE` | `/api/v1/in-app-notifications/{id}` | Delete notification from user inbox |

---

## Getting Started

### Prerequisites

- **JDK 25** (GraalVM or OpenJDK 25)
- **PostgreSQL** 14+ (or in-memory H2 during testing)

### Build & Run Tests

```powershell
# Set JAVA_HOME (Windows)
$env:JAVA_HOME = "C:\Users\Acer_PTS\.jdks\graalvm-jdk-25"

# Run all automated unit and integration tests
.\mvnw.cmd clean test
```

### Run Locally

```powershell
.\mvnw.cmd spring-boot:run
```

The application starts on port **8081**:
- **Base URL**: `http://localhost:8081`
- **Swagger UI**: [http://localhost:8081/swagger-ui.html](http://localhost:8081/swagger-ui.html)
- **OpenAPI Docs**: [http://localhost:8081/v3/api-docs](http://localhost:8081/v3/api-docs)

---

## Directory Structure

```text
hekma-notification-service/
├── src/
│   ├── main/
│   │   ├── java/com/hekma/notification/
│   │   │   ├── channel/
│   │   │   │   ├── email/           # Email handlers & providers (Mock, SMTP)
│   │   │   │   ├── inapp/           # In-App notification channel handler
│   │   │   │   ├── push/            # Push notification handlers (Mock, Firebase)
│   │   │   │   ├── sms/             # SMS handlers & providers (Mock, Twilio)
│   │   │   │   ├── NotificationChannelHandler.java
│   │   │   │   └── NotificationChannelRegistry.java
│   │   │   ├── config/              # Security, Async, Jackson, GlobalExceptionHandler
│   │   │   ├── controller/          # REST Controllers
│   │   │   ├── domain/
│   │   │   │   ├── entity/          # JPA Entities (NotificationLog, InAppNotification)
│   │   │   │   ├── model/           # Enums (Channel, Status, Priority)
│   │   │   │   └── repository/      # Spring Data Repositories
│   │   │   ├── dto/                 # Request & Response DTOs
│   │   │   ├── service/             # Dispatcher, InApp, Async, Template services
│   │   │   ├── support/             # Support Center & Ticket Module
│   │   │   │   ├── controller/      # Support REST controllers (Public & Admin/Authenticated)
│   │   │   │   ├── domain/          # Ticket, Comment, Attachment entities & repos
│   │   │   │   ├── dto/             # Ticket, OTP, Category, SLA DTOs
│   │   │   │   ├── service/         # Ticket, OTP, Catalog, Dispatch integration
│   │   │   │   └── storage/         # Pluggable attachment storage SPI (Mock, AWS S3)
│   │   │   └── HekmaNotificationServiceApplication.java
│   │   └── resources/
│   │       ├── db/migration/        # Flyway SQL migrations
│   │       └── application.yml
│   └── test/                        # Automated unit and integration test suite
├── pom.xml
└── README.md
```
