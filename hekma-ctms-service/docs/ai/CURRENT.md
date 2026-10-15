# Current Project State (`hekma-ctms-service`)

## Current Focus
Maintaining production-grade Clinical Trial Management (CTMS) microservice functionality, verifying token introspection and tenant subtree authorization with `hekma-identity-service`, and supporting UI testing from `hekma-test-app`.

## Recently Completed
- **Microservice Extraction & Baseline Migration**:
  - Implemented standalone Spring Boot 4.1.1 / Java 25 microservice on port 8082.
  - Baseline migration `V1__init_ctms_schema.sql` with table prefix `ctms_` and isolated Flyway table `ctms_flyway_schema_history`.
  - Configured optimistic locking and soft deletion via `@SQLRestriction("is_deleted = false")`.
- **Token Introspection & Security Layer**:
  - Configured `IntrospectionAuthenticationFilter` communicating with `hekma-identity-service` (`POST /api/v1/auth/introspect`).
  - Implemented in-memory SHA-256 token caching with 60-second TTL.
  - Enforced tenant subtree security boundaries (`CtmsPrincipal.isWithinSubtree`).
- **Clinical Trial Management Domain Services**:
  - Study lifecycle (`StudyService`, `StudyEntity`, phases, arms, milestones).
  - Site operations (`StudySiteService`, `StudySiteEntity`, investigators, monitoring notes).
  - Safety & Adverse Event reporting (`AdverseEventService`, `AdverseEventEntity`).
  - Study visit schedules (`StudyScheduleService`, `StudyScheduleEntity`).
  - EDC webhook ingestion with AES decryption (`CmtsWebhookService`).
- **Dual API Surface & Public GraphiQL IDE**:
  - RESTful OpenAPI 3.1 endpoints with Swagger UI at `/swagger-ui/index.html`.
  - Spring for GraphQL queries and mutations (`/graphql`).
  - Permitted `/graphiql` and `/graphiql/**` publicly without authentication in `SecurityConfig` and bypassed `IntrospectionAuthenticationFilter` for GraphiQL paths.
- **Postman Collection**:
  - Created standalone Postman collection `Hekma_CTMS_Service.postman_collection.json` and local environment file.

## In Progress
- Parallel AI context synchronization with `hekma-identity-service`, `hekma-notification-service`, and `hekma-test-app`.
- UI end-to-end integration with `hekma-test-app` for study protocol and site monitoring workflows.

## Pending
- Comprehensive test coverage expansions for edge-case EDC webhook payloads.
- Integration tests against live PostgreSQL container testbed.

## Known Issues / Invariants
- `hekma-identity-service` must be reachable at `http://localhost:8080` for token introspection cache misses.
- Shared PostgreSQL database `hekmaai` uses dedicated table prefix `ctms_`.
