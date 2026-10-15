# Shared AI Context - CTMS Service (`hekma-ctms-service`)

## 1. Executive Summary
`hekma-ctms-service` is the standalone microservice responsible for Clinical Trial Management within the Hekma Platform. It was extracted and modernized from the monolithic `hekma_api` codebase.

### Scope & Boundaries
- **In Scope**:
  - Clinical trial protocol lifecycle (studies, phases, arms, events, milestones).
  - Investigator site management, personnel, monitoring notes, and discrepancy queries.
  - Patient adverse events logging, severity, causality, and outcomes.
  - Visit schedules, segment definitions, and patient progress tracking.
  - EDC webhook ingestion with site-specific AES decryption.
  - Dual REST API (OpenAPI 3.1) and Spring for GraphQL API.
- **Out of Scope (Delegated to other microservices)**:
  - Authentication, user management, and roles/authorities -> `hekma-identity-service`.
  - Notifications, SMS, emails, OTP -> `hekma-notification-service`.
  - Clinical EHR, Patient-360 health records -> `hekma-patient-service` / EHR microservice.

---

## 2. Architectural Guardrails
1. **Token Introspection Pattern**:
   - `hekma-ctms-service` does not hold private RSA keys or manage passwords.
   - Incoming bearer tokens are introspected via `IdentityServiceClient` against `http://localhost:8080/api/v1/auth/introspect`.
   - Results are cached for 60 seconds with SHA-256 token hashing.
2. **Tenant Hierarchy & Subtree Isolation**:
   - Every study records an owning `tenantPath`.
   - The caller's principal has a `tenantPath`.
   - Principal method `isWithinSubtree(targetTenantPath)` guarantees tenant boundaries across sponsors and sites.
3. **Database & Schema Co-Location**:
   - Tables use prefix `ctms_` and Flyway history is tracked in `ctms_flyway_schema_history`.
   - Entities extend `BaseAuditEntity` (`createdAt`, `updatedAt`, `createdBy`, `updatedBy`, `version`, `isDeleted`).
4. **Soft Deletes**:
   - Entities are filtered with `@SQLRestriction("is_deleted = false")`.

---

## 3. Interactive APIs & Exploration
- **REST Swagger UI**: [http://localhost:8082/swagger-ui/index.html](http://localhost:8082/swagger-ui/index.html)
- **Direct GraphQL Endpoint**: `POST http://localhost:8082/graphql`
- **GraphiQL IDE Explorer**: [http://localhost:8082/graphiql](http://localhost:8082/graphiql) *(configured with `{"Authorization": "Bearer <TOKEN>"}`)*

