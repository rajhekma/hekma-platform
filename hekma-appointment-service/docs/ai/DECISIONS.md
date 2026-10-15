# Architecture Decision Records (ADRs) (`hekma-appointment-service`)

## ADR-001: Standalone Microservice Extraction
- **Status**: Accepted
- **Context**: The appointment, request, and scheduling modules were tightly coupled inside legacy monolithic `hekma_api`.
- **Decision**: Extract into a dedicated Spring Boot microservice `hekma-appointment-service` running on port 8083.
- **Consequences**: Independent lifecycle, horizontal scaling, isolated database migrations.

## ADR-002: Token Introspection over Shared Keys
- **Status**: Accepted
- **Context**: Service needs to authenticate requests without duplicating Firebase credentials or private signing keys.
- **Decision**: Use `IntrospectionAuthenticationFilter` communicating via HTTP with `hekma-identity-service` (`POST /internal/v1/auth/introspect`) with 60-second SHA-256 token caching.
- **Consequences**: Centralized RBAC and tenant evaluation in identity service, minimal overhead due to local caching.

## ADR-003: Delegation of Email/SMS Dispatch to Notification Service
- **Status**: Accepted
- **Context**: Appointments require reminders, confirmations, and alerts sent across email and SMS.
- **Decision**: `hekma-appointment-service` delegates all outbound message dispatch to `hekma-notification-service` (`POST /api/v1/notifications/send`).
- **Consequences**: Single responsibility, unified notification provider handling.
