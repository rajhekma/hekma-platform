# Current Status & Active Focus (`hekma-appointment-service`)

## 1. Current State
- **Status**: Microservice extracted, fully implemented, and test-verified.
- **Port**: `8083`
- **Database Schema**: V1 Flyway migration (`appointment_flyway_schema_history`).
- **Tests**: 14 / 14 passing automated unit & integration tests.

## 2. Completed Milestones
- **Architecture & Foundation**:
  - Spring Boot 4.1.1 configured on Java 25 (compiler release 21 target).
  - Maven Wrapper 3.9.16 (fully compatible with IntelliJ IDEA 2025.x).
  - PostgreSQL datasource + Flyway co-located schema history.
  - Trace correlation filter emitting `trace-id` / `X-Trace-Id` headers and single `"traceId"` responses.
  - OpenAPI 3.1 & Spring for GraphQL 2.0.5 setup.
- **Security & Introspection**:
  - Stateless security filter with token introspection caching calling `hekma-identity-service` (`:8080`).
- **Domain & Persistence**:
  - Entities: `AppointmentEntity`, `AppointmentRequestEntity`, `NotificationPreferenceEntity`, `WebNotificationEntity`.
  - Repositories with conflict interval queries and reminder lookups.
- **Business Logic**:
  - `ConflictDetectionService`: Temporal overlap query and conflict prevention.
  - `AppointmentService`: CRUD, filtering, rescheduling, status management.
  - `AppointmentRequestService`: Booking requests, approval/rejection.
  - `NotificationPreferenceService`: Channel toggles (email, SMS, web).
  - `WebNotificationService`: Web notifications and mark-as-viewed.
  - `AppointmentReminderScheduler`: Automated multi-tier reminder engine communicating with `hekma-notification-service` (`:8081`).
- **Interfaces**:
  - REST Controllers for appointments, requests, preferences, and reminders.
  - GraphQL schema and data fetchers with 0 unmapped schema fields.
