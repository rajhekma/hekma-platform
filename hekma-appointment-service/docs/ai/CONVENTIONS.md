# Coding Conventions & Standards (`hekma-appointment-service`)

## 1. Naming & Database Standards
- **Tables**: Microservice prefix required: `appointment_<entity>` (e.g. `appointment_appointments`, `appointment_requests`, `appointment_notification_preferences`, `appointment_web_notifications`).
- **Indexes**: Format: `appointment_idx_<table_or_concept>_<columns>`.
- **Flyway Schema History**: Co-located on shared database via `appointment_flyway_schema_history` with `baseline-version: 0`.
- **Entities**: All domain entities inherit `BaseAuditEntity` (`id` UUID, `createdAt`, `updatedAt`, `createdBy`, `updatedBy`, `@Version Long version`, `isDeleted` soft-delete).

## 2. Distributed Tracing & Logging
- **MDC Key**: `traceId` (UUID v4).
- **HTTP Headers**: Both `X-Trace-Id` and `trace-id` are accepted on incoming requests; propagated on all outgoing responses.
- **Log Pattern**: Every request logs entry and completion with HTTP method, URI, status, duration ms, and traceId.
- **JSON Response Format**: Unified envelope containing `"traceId"` (camelCase only, never duplicate snake/kebab trace keys).

## 3. Error Handling
- Exceptions are caught by `GlobalExceptionHandler`.
- Standard response body: `ApiErrorResponse` (`status`, `error`, `message`, `path`, `timestamp`, `traceId`, `details`).
- No raw stack traces are returned to clients.

## 4. API & GraphQL Conventions
- **REST Endpoints**: `/api/v1/appointments/**`.
- **GraphQL Schema**: Defined in `src/main/resources/graphql/appointments.graphqls`.
- Field names in GraphQL match domain/DTO property getters.
