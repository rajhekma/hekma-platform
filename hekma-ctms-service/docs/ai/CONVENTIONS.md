# Coding Standards & Conventions (`hekma-ctms-service`)

## 1. Package Structure
- `com.hekma.ctms.config`: Security, OpenAPI, and JPA Auditing configuration.
- `com.hekma.ctms.controller.rest`: REST API endpoints.
- `com.hekma.ctms.controller.graphql`: GraphQL query and mutation handlers.
- `com.hekma.ctms.controller.webhook`: EDC inbound webhook receiver.
- `com.hekma.ctms.domain`: JPA Entities and BaseAuditEntity.
- `com.hekma.ctms.dto`: Request/Response data transfer objects and ApiResponse.
- `com.hekma.ctms.exception`: Domain exceptions (`ResourceNotFoundException`, `AccessDeniedException`) and `GlobalExceptionHandler`.
- `com.hekma.ctms.repository`: Spring Data JPA repositories.
- `com.hekma.ctms.security`: Security filter, `CtmsPrincipal`, and `IdentityServiceClient`.
- `com.hekma.ctms.service`: Business service layer.

---

## 2. Coding Patterns & Rules
- **Entities**:
  - Always inherit from `BaseAuditEntity`.
  - Use `@SQLRestriction("is_deleted = false")` for soft deletion.
  - Never execute raw SQL `DELETE`.
  - Auditing fields and optimistic locking `@Version` are automatically managed.
- **DTOs & Controllers**:
  - All REST endpoints wrap payloads in `ApiResponse<T>`.
  - Path variables override or populate request DTO fields before validation/service call.
  - Method security annotations (`@PreAuthorize("hasAuthority('...')")`) are declared on all protected methods.
- **Error Handling**:
  - Centralized in `GlobalExceptionHandler`.
  - Responses format as standard `ApiErrorResponse` with timestamp, status, error, and message.
