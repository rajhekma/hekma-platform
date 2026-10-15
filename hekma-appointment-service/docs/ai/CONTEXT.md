# Shared AI Context - Appointment Service (`hekma-appointment-service`)

## 1. Executive Summary
`hekma-appointment-service` is the standalone microservice responsible for Clinical Visit Scheduling, Conflict Detection, Appointment Requests, Reminders, and Notification Preferences within the Hekma Platform. It was extracted and modernized from the monolithic `hekma_api` codebase.

### Scope & Boundaries
- **In Scope**:
  - Clinical appointment lifecycle (scheduled, confirmed, in-progress, completed, cancelled, no-show, rescheduled).
  - Time overlap & double-booking conflict detection for doctors, trial sites, and patients.
  - Appointment change and booking requests (creation, approvals, rejections, cancellation requests).
  - User notification preferences (email, SMS, web notifications).
  - Web in-app notifications and viewed state tracking.
  - Scheduled automated appointment reminders (1 hour, 1 day, 7 days prior).
  - Dual REST API (OpenAPI 3.1) and Spring for GraphQL API (`/graphql`).
- **Out of Scope (Delegated to other microservices)**:
  - Authentication, user management, and roles/authorities -> `hekma-identity-service`.
  - Notification dispatch (email, SMS delivery) -> `hekma-notification-service`.
  - Clinical protocol and trial definition -> `hekma-ctms-service`.

---

## 2. Architectural Guardrails
1. **Token Introspection Pattern**:
   - `hekma-appointment-service` does not hold private RSA keys or manage passwords.
   - Incoming bearer tokens are introspected via `IdentityServiceClient` against `http://localhost:8080/internal/v1/auth/introspect`.
   - Results are cached for 60 seconds with SHA-256 token hashing.
2. **Conflict Detection Engine**:
   - Time intervals are verified using `startTime < other.endTime AND endTime > other.startTime`.
   - Conflicts prevent double-booking unless explicitly flagged.
3. **Automated Reminders**:
   - `AppointmentReminderScheduler` executes periodically.
   - Multi-tier thresholds: 7 days, 1 day, 1 hour before scheduled start time.
   - Reminders are dispatched through `NotificationServiceClient` calling `hekma-notification-service` (`:8081`).
4. **Database & Schema Co-Location**:
   - Tables use prefix `appointment_` and Flyway history is tracked in `appointment_flyway_schema_history`.
   - Entities extend `BaseAuditEntity` (`id`, `createdAt`, `updatedAt`, `createdBy`, `updatedBy`, `version`, `isDeleted`).
5. **Distributed Tracing**:
   - Correlation IDs are captured and injected by `TraceIdFilter` into response headers and responses (`"traceId"`).

---

## 3. Interactive APIs & Exploration
- **REST Swagger UI**: [http://localhost:8083/swagger-ui/index.html](http://localhost:8083/swagger-ui/index.html)
- **Direct GraphQL Endpoint**: `POST http://localhost:8083/graphql`
- **GraphiQL IDE Explorer**: [http://localhost:8083/graphiql](http://localhost:8083/graphiql) *(configured with `{"Authorization": "Bearer <TOKEN>"}`)*
