# Architecture Decision Records (ADRs) (`hekma-ctms-service`)

## ADR-001: Standalone CTMS Extraction from Monolith
- **Date**: 2026-10-12
- **Status**: Accepted & Implemented
- **Context**: The legacy `hekma_api` contained mixed domains (CTMS, Identity/Cognito/Firebase, SupportCenter, Patient-360). CTMS operations require independent scalability, clinical protocol versioning, and EDC integration.
- **Decision**: Extract all CTMS tables, repositories, services, REST controllers, EDC webhooks, and GraphQL schemas into `hekma-ctms-service` on Spring Boot 4.1.1 and Java 25.
- **Consequences**: CTMS runs independently on port 8082 with dedicated Flyway migration history `ctms_flyway_schema_history`.

## ADR-002: Token Introspection over Shared Secrets or Keycloak
- **Date**: 2026-10-12
- **Status**: Accepted & Implemented
- **Context**: CTMS needs caller authentication and tenant context. Keycloak was explicitly removed from the stack in favor of native `hekma-identity-service`.
- **Decision**: Use RFC 7662 style Token Introspection against `hekma-identity-service` with 60-second in-memory SHA-256 token caching.
- **Consequences**: CTMS remains decoupled from identity storage and Firebase Admin SDK while verifying user identity and authorities in real time.

## ADR-003: Subtree Multi-Tenancy Boundary Enforcement
- **Date**: 2026-10-12
- **Status**: Accepted & Implemented
- **Context**: Multiple sponsors and sites share the platform. Sponsors must only access their clinical studies and allocated sites.
- **Decision**: Implement `tenantPath` materialized path matching. `CtmsPrincipal.isWithinSubtree(targetTenantPath)` enforces that sponsors can only view/modify studies within their hierarchy, while `ADMIN` and `SYSTEM_ADMIN` have global access.
- **Consequences**: Strict regulatory data isolation across clinical trial sponsors and hospital sites.

## ADR-004: Dual API Interface (REST + GraphQL)
- **Date**: 2026-10-12
- **Status**: Accepted & Implemented
- **Context**: Legacy web clients use GraphQL queries and mutations (`/graphql`), while new integration clients use OpenAPI REST endpoints (`/api/v1/studies/**`).
- **Decision**: Support both REST (via `@RestController` and SpringDoc OpenAPI 3.1) and GraphQL (via `spring-boot-starter-graphql` and `schema.graphqls`).
- **Consequences**: Backward compatibility with existing frontend applications while providing clean REST APIs for third-party integrations.
