# API Documentation: Hekma Notification Service (`hekma-notification-service`)

## 1. API Design Conventions & Protocols

The **Hekma Notification Service** exposes two distinct API groups on port **`8081`**:
1. **Inter-Service Dispatch APIs (`/api/v1/notifications/*`)**: Protected endpoints used exclusively by internal microservices (`hekma-identity-service`, `hekma_api`) to queue and broadcast notifications.
2. **In-App Feed APIs (`/api/v1/in-app-notifications/*`)**: Public/gateway-exposed REST endpoints used by frontend web and mobile applications to retrieve and manage user inboxes.

### 1.1 Authentication & Header Requirements
- **Inter-Service Endpoints**: Must include the header:
  ```http
  X-Hekma-Service-Key: hekma-internal-secret-key-2026
  ```
  Missing or invalid keys reject requests with HTTP `401 Unauthorized`.
- **In-App Endpoints**: Whitelisted from API key requirements to enable direct user client consumption.

### 1.2 HTTP Status Codes
- `200 OK`: Request succeeded (synchronous dispatch, broadcast result, status fetch, or inbox feed query).
- `202 Accepted`: Asynchronous dispatch request accepted and queued for background execution.
- `204 No Content`: Resource deleted (e.g. notification deletion from inbox).
- `400 Bad Request`: Input validation failure or unsupported channel/provider.
- `401 Unauthorized`: Missing or invalid `X-Hekma-Service-Key` header.
- `404 Not Found`: Notification log or in-app notification not found.
- `500 Internal Server Error`: Unhandled server exception.

---

## 2. Inter-Service Dispatch Endpoints (`/api/v1/notifications`)

### 2.1 Send Single Notification
- **Endpoint**: `POST /api/v1/notifications/send`
- **Security**: Requires `X-Hekma-Service-Key` header.
- **Description**: Queues a notification for delivery over a single channel (`EMAIL`, `SMS`, `PUSH`, or `IN_APP`). Executes asynchronously by default (`async: true`), returning `202 Accepted`.
- **Request Body**:
  ```json
  {
    "channel": "EMAIL",
    "recipient": "patient@hekma.com",
    "title": "Welcome {{name}}",
    "content": "Your verification code is {{code}}. Valid for 5 minutes.",
    "priority": "HIGH",
    "templateParams": {
      "name": "Sarah",
      "code": "84729"
    },
    "sourceService": "hekma-identity-service",
    "idempotencyKey": "otp-297cc5f6-8726-4771-942f-4e3efa93685c",
    "async": true
  }
  ```
- **Response `202 Accepted`**:
  ```json
  {
    "id": "e8a93a10-2b1c-4b5f-9e67-0c7f66a87b92",
    "channel": "EMAIL",
    "recipient": "patient@hekma.com",
    "status": "PENDING",
    "providerMessageId": null,
    "errorMessage": null,
    "createdAt": "2026-10-01T12:00:00Z"
  }
  ```

### 2.2 Broadcast Notification to Multiple Channels
- **Endpoint**: `POST /api/v1/notifications/broadcast`
- **Security**: Requires `X-Hekma-Service-Key` header.
- **Description**: Dispatches an alert simultaneously across multiple channels for a user.
- **Request Body**:
  ```json
  {
    "channels": ["EMAIL", "SMS", "IN_APP"],
    "email": "doctor@hekma.com",
    "phone": "+966501234567",
    "userId": "usr_9988",
    "title": "Urgent Patient Vitals Alert",
    "content": "Patient vitals in Room 304 have exceeded safe thresholds.",
    "priority": "URGENT",
    "sourceService": "hekma_api"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "totalDispatched": 3,
    "results": [
      {
        "id": "11111111-2b1c-4b5f-9e67-0c7f66a87b92",
        "channel": "EMAIL",
        "recipient": "doctor@hekma.com",
        "status": "PENDING",
        "createdAt": "2026-10-01T12:00:00Z"
      },
      {
        "id": "22222222-2b1c-4b5f-9e67-0c7f66a87b92",
        "channel": "SMS",
        "recipient": "+966501234567",
        "status": "PENDING",
        "createdAt": "2026-10-01T12:00:00Z"
      },
      {
        "id": "33333333-2b1c-4b5f-9e67-0c7f66a87b92",
        "channel": "IN_APP",
        "recipient": "usr_9988",
        "status": "PENDING",
        "createdAt": "2026-10-01T12:00:00Z"
      }
    ]
  }
  ```

### 2.3 Get Notification Delivery Status
- **Endpoint**: `GET /api/v1/notifications/{id}/status`
- **Security**: Requires `X-Hekma-Service-Key` header.
- **Description**: Retrieves delivery status (`PENDING`, `SENT`, `DELIVERED`, `FAILED`) and error message if delivery failed.
- **Response `200 OK`**:
  ```json
  {
    "id": "e8a93a10-2b1c-4b5f-9e67-0c7f66a87b92",
    "channel": "EMAIL",
    "recipient": "patient@hekma.com",
    "status": "SENT",
    "providerMessageId": "<mock-msg-123>",
    "errorMessage": null,
    "createdAt": "2026-10-01T12:00:00Z"
  }
  ```

---

## 3. In-App Notification Feed Endpoints (`/api/v1/in-app-notifications`)

### 3.1 Get User Notification Feed
- **Endpoint**: `GET /api/v1/in-app-notifications?userId={userId}&unreadOnly={true|false}&page=0&size=20`
- **Description**: Returns paginated list of notifications for a user, ordered by creation date descending.
- **Response `200 OK`**:
  ```json
  {
    "content": [
      {
        "id": "990e8400-e29b-41d4-a716-446655440000",
        "userId": "usr_12345",
        "title": "Welcome to Hekma!",
        "content": "Welcome Sarah, your clinical account is active.",
        "category": "GENERAL",
        "actionUrl": "/dashboard",
        "dataJson": null,
        "isRead": false,
        "readAt": null,
        "createdAt": "2026-10-01T12:00:00Z"
      }
    ],
    "page": 0,
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "last": true
  }
  ```

### 3.2 Get Unread Notification Count
- **Endpoint**: `GET /api/v1/in-app-notifications/unread-count?userId={userId}`
- **Response `200 OK`**:
  ```json
  {
    "userId": "usr_12345",
    "unreadCount": 3
  }
  ```

### 3.3 Mark Single Notification as Read
- **Endpoint**: `PATCH /api/v1/in-app-notifications/{id}/read`
- **Response `200 OK`**:
  ```json
  {
    "id": "990e8400-e29b-41d4-a716-446655440000",
    "userId": "usr_12345",
    "title": "Welcome to Hekma!",
    "content": "Welcome Sarah, your clinical account is active.",
    "isRead": true,
    "readAt": "2026-10-01T12:05:00Z",
    "createdAt": "2026-10-01T12:00:00Z"
  }
  ```

### 3.4 Mark All Notifications as Read
- **Endpoint**: `PATCH /api/v1/in-app-notifications/read-all?userId={userId}`
- **Response `200 OK`**:
  ```json
  {
    "userId": "usr_12345",
    "markedAsReadCount": 3
  }
  ```

### 3.5 Delete Notification from Inbox
- **Endpoint**: `DELETE /api/v1/in-app-notifications/{id}`
- **Response `204 No Content`**

---

## 4. Support Tickets Center Endpoints

The Support Center module provides public unauthenticated flows secured via email OTP session tokens, alongside authenticated endpoints for participant summary stats and attachments.

### 4.1 Public Helpdesk Endpoints (`/api/v1/support/public/**`)
All endpoints except `/otp/send` and `/otp/verify` require the session header:
```http
X-Support-Otp-Token: <otp-session-token>
```

| HTTP Method | Route | Description | Request Body / Params |
| :--- | :--- | :--- | :--- |
| **`POST`** | `/api/v1/support/public/otp/send` | Request email OTP code | `{"email": "patient@example.com"}` |
| **`POST`** | `/api/v1/support/public/otp/verify` | Verify OTP code & receive session token | `{"challengeId": "uuid", "otpCode": "123456"}` |
| **`POST`** | `/api/v1/support/public/file-upload` | Request presigned S3 PUT URL for pre-submit file | `{"filename": "screenshot.png"}` |
| **`POST`** | `/api/v1/support/public/tickets` | Create support ticket with optional staged attachments | `CreatePublicTicketRequest` |
| **`GET`** | `/api/v1/support/public/tickets` | List tickets for verified email | `?email=patient@example.com&status=&searchText=&page=0&pageSize=20` |
| **`GET`** | `/api/v1/support/public/tickets/{ticketId}` | Get ticket detail, SLA, conversation & attachments | Path `{ticketId}` |
| **`POST`** | `/api/v1/support/public/tickets/{ticketId}/comments` | Add participant reply to ticket | `{"commentText": "Update details..."}` |
| **`POST`** | `/api/v1/support/public/tickets/{ticketId}/escalate` | Escalate ticket for priority handling | `{"reason": "Urgent trial impact"}` |
| **`POST`** | `/api/v1/support/public/tickets/{ticketId}/attachments` | Upload image files directly (`multipart/form-data`) | Form part `files` |
| **`POST`** | `/api/v1/support/public/tickets/{ticketId}/attachments/metadata` | Register metadata for an uploaded attachment | `UploadAttachmentRequest` |

### 4.2 Authenticated & Common Support Endpoints (`/api/v1/support/**`)

| HTTP Method | Route | Auth Requirement | Description |
| :--- | :--- | :--- | :--- |
| **`GET`** | `/api/v1/support/categories` | Public (None) | Returns list of issue categories (`APP_CRASH`, `LOGIN_ISSUE`, etc.) |
| **`GET`** | `/api/v1/support/summary` | Bearer JWT / `X-User-Id` | Returns user's open and resolved ticket counts |
| **`POST`** | `/api/v1/support/tickets/{ticketId}/attachments` | Bearer JWT / `X-User-Id` | Uploads multipart image files for an authenticated user |

## 5. Platform GraphQL & GraphiQL Topology & Roadmap

Across the Hekma Platform microservice architecture:
- **`hekma-identity-service` (Port `8080`)**: Exposes an active **Spring for GraphQL** endpoint (`POST /graphql`) and **GraphiQL IDE** (`http://localhost:8080/graphiql`) for administrative user directory queries, role counts, and `@BatchMapping` patient consent resolution.
- **`hekma-ctms-service` (Port `8082`)**: Exposes an active **Spring for GraphQL** endpoint (`POST /graphql`) and **GraphiQL IDE** (`http://localhost:8082/graphiql`) for clinical study protocols, investigator sites, adverse safety events, and visit schedule timelines.
- **`hekma-notification-service` (Port `8081`)**: Currently operates as a specialized asynchronous REST message router (`POST /api/v1/notifications/send`, `/api/v1/in-app-notifications`, `/api/v1/support`).

### 5.1 Notification GraphQL Roadmap & Schema Contract
To align with `identity` and `ctms` for unified frontend consumption (such as `hekma-test-app`), the planned Spring for GraphQL schema definition on port `8081` is structured as:

```graphql
type NotificationLog {
    id: ID!
    channel: NotificationChannel!
    recipient: String!
    title: String
    content: String!
    status: NotificationStatus!
    sourceService: String
    createdAt: String!
}

enum NotificationChannel {
    EMAIL
    SMS
    PUSH
    IN_APP
}

enum NotificationStatus {
    PENDING
    SENT
    DELIVERED
    FAILED
}

type InAppFeed {
    id: ID!
    userId: ID!
    title: String!
    message: String!
    isRead: Boolean!
    createdAt: String!
}

type Query {
    getNotificationLogs(recipient: String, channel: NotificationChannel): [NotificationLog!]!
    getInAppNotifications(userId: ID!, unreadOnly: Boolean): [InAppFeed!]!
    getSupportTickets(email: String!): [SupportTicket!]!
}

type Mutation {
    markNotificationAsRead(notificationId: ID!): Boolean!
}
```

---

## 6. Interactive Documentation & Testing Tools

### 6.1 Service Tools (`:8081`)
When running `hekma-notification-service` locally:
- **Swagger UI (REST OpenAPI 3)**: [http://localhost:8081/swagger-ui.html](http://localhost:8081/swagger-ui.html)
- **OpenAPI 3 JSON Specification**: [http://localhost:8081/v3/api-docs](http://localhost:8081/v3/api-docs)

### 6.2 Platform GraphiQL & Swagger Quick Reference
| Service | Port | REST Swagger UI | GraphQL Endpoint | GraphiQL IDE Explorer |
|---|---|---|---|---|
| **`hekma-identity-service`** | `8080` | [http://localhost:8080/swagger-ui.html](http://localhost:8080/swagger-ui.html) | `POST /graphql` | [http://localhost:8080/graphiql](http://localhost:8080/graphiql) |
| **`hekma-notification-service`** | `8081` | [http://localhost:8081/swagger-ui.html](http://localhost:8081/swagger-ui.html) | *REST-first (Roadmap)* | *Roadmap (:8081/graphiql)* |
| **`hekma-ctms-service`** | `8082` | [http://localhost:8082/swagger-ui/index.html](http://localhost:8082/swagger-ui/index.html) | `POST /graphql` | [http://localhost:8082/graphiql](http://localhost:8082/graphiql) |


