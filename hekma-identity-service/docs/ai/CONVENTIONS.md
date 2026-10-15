# Project Conventions: Hekma Identity Service

This document defines the verified architectural, coding, testing, and operational conventions enforced in `hekma-identity-service`.

---

## 1. Naming Conventions

| Component | Convention | Example |
| :--- | :--- | :--- |
| **JPA Entities** | PascalCase ending with `Entity`, extending `BaseAuditEntity` | `UserEntity`, `PatientDetailEntity`, `OtpRequestEntity` |
| **Spring Repositories** | PascalCase ending with `Repository`, extending `JpaRepository` | `UserRepository`, `OtpLockoutRepository` |
| **Service Layer** | PascalCase ending with `Service` | `AuthService`, `OtpService`, `UserManagementService` |
| **REST Controllers** | PascalCase ending with `Controller` | `AuthController`, `UserController`, `OtpController` |
| **GraphQL Controllers** | PascalCase ending with `GraphQlController` | `UserGraphQlController` |
| **DTOs (Requests)** | PascalCase ending with `Request` | `RegisterRequest`, `LoginRequest`, `SendOtpRequest` |
| **DTOs (Responses)** | PascalCase ending with `Response` | `RegisterResponse`, `LoginResponse`, `VerifyOtpResponse` |
| **Exceptions** | PascalCase ending with `Exception`, extending `RuntimeException` | `UserAlreadyExistsException`, `OtpLockoutException` |
| **Enums** | PascalCase type, `UPPER_SNAKE_CASE` values | `Role.SYSTEM_ADMIN`, `UserStatus.ACTIVE` |
| **Database Tables** | Microservice prefix first: `<service>_<table_name>` | `identity_users`, `identity_patient_details`, `notification_logs` |
| **Database Indexes** | Microservice prefix first: `<service>_idx_<table_or_concept>_<columns>` | `identity_idx_users_email`, `notification_idx_logs_recipient` |
| **Flyway History Table** | Microservice prefix first: `<service>_flyway_schema_history` | `identity_flyway_schema_history`, `notification_flyway_schema_history` |
| **Database Columns** | `snake_case` | `firebase_uid`, `phone_number`, `is_deleted` |

---


## 2. Package Structure & Layering

Strict unidirectional layering: `Controller -> Service -> Repository / Integration -> Database`.

```text
com.hekma.identity
├── config/         # SecurityFilterChain, OpenAPI, JPA auditing & initializers
├── controller/     # REST controllers (@RestController) & GraphQL resolvers (@Controller)
├── domain/         # JPA entities, enums (Role, UserStatus) & sub-packages (domain.otp)
├── dto/            # REST and GraphQL request/response DTOs (and dto.otp)
├── exception/      # Domain exceptions and centralized GlobalExceptionHandler
├── firebase/       # FirebaseAuthService, MockFirebaseService & token response DTOs
├── notification/   # NotificationServiceClient (HTTP REST client for notification-svc)
├── repository/     # Spring Data JPA interfaces
└── service/        # Core business service layer
```

---

## 3. Dependency Injection
- **Constructor Injection Only**: Always inject dependencies via explicit constructor or Lombok `@RequiredArgsConstructor`.
- **Field Injection Prohibited**: Never use `@Autowired` on private class fields.

```java
@Service
@Slf4j
public class AuthService {
    private final UserRepository userRepository;
    private final FirebaseService firebaseService;

    public AuthService(UserRepository userRepository, FirebaseService firebaseService) {
        this.userRepository = userRepository;
        this.firebaseService = firebaseService;
    }
}
```

---

## 4. DTO Conventions & Validation
- **Jakarta Bean Validation**: Apply `@Valid` on all controller `@RequestBody` parameters.
- **Constraints**: Use `@NotBlank`, `@Email`, `@Size`, `@Pattern`, `@NotNull` on DTO attributes.
- **Lombok Usage**: Use `@Getter`, `@Setter`, `@Builder`, `@NoArgsConstructor`, `@AllArgsConstructor` on DTOs.
- **No Entities in API Contracts**: Controllers must never accept or return JPA entities directly. Always map to/from DTOs.

---

## 5. Error Handling & Exceptions
- **Domain Exceptions**: Throw semantic runtime exceptions extending `RuntimeException` (e.g. `UserNotFoundException`, `InvalidRoleException`).
- **Centralized Advice**: All domain exceptions are intercepted by `GlobalExceptionHandler` (`@RestControllerAdvice`).
- **Standardized Payload**: Return standardized `ApiErrorResponse` containing correlation trace ID:
  ```json
  {
    "status": 404,
    "error": "Not Found",
    "message": "User with ID '...' not found.",
    "timestamp": "2026-10-06T00:00:00Z",
    "traceId": "c8b4172f-f442-43ce-9a3b-c2e82506e938"
  }
  ```
- **Zero Raw Traces**: Never return raw Java exception stack traces or internal SQL constraint messages to clients.

---

## 5a. Security & Authorization Conventions
- **Caller identity**: Obtain the caller with `@AuthenticationPrincipal HekmaPrincipal` (REST and GraphQL). Never read operator or tenant identity from headers, query params or request bodies.
- **Method security**: Every protected controller handler declares `@PreAuthorize`, preferably an authority (`hasAuthority('patient:read')`; admins hold all), roles only for platform-only actions (`hasRole('SYSTEM_ADMIN')`), or `isAuthenticated()` with scoping in the service. `AuthorizationGuardTest` fails the build otherwise.
- **Authorities**: New capabilities are a new `Authority` constant **plus** a Flyway migration seeding `identity_authorities`. Granting code must enforce grant ≤ own (`AuthorityService`). Privileged changes call `AuditService.record(...)` with identifiers only (no PHI).
- **Public endpoints**: Must be added explicitly (exact method + path) to `SecurityConfig.PUBLIC_POST_ENDPOINTS`; never use wildcards for business routes.
- **Scoping**: Resources outside the caller's scope throw a not-found exception (`404`), not `403`, to avoid confirming existence.
- **Passwords**: Stored only in Firebase, never in PostgreSQL. Always validated through `FirebaseService.signInWithPassword(authEmail, …)` and set through the Admin SDK (`createUser` / `updatePassword`); never issue tokens without a password or OTP check. Every DTO field that sets a password carries `@NotBlank` + `@StrongPassword` (8–128 chars, upper, lower, digit, special). Password reset and change revoke sessions (`revokeRefreshTokens`).
- **Tests**: Standalone controller tests register `AuthenticationPrincipalArgumentResolver` and use `TestAuthentication.authenticate(...)`; full-context tests apply `springSecurity()` and send `TestAuthentication.bearer(user)` (mock ID token).

---

## 6. Logging & Distributed Tracing Standards
- **Distributed Trace ID**:
  - Every backend microservice must configure `TraceIdFilter` (`@Order(Ordered.HIGHEST_PRECEDENCE)`).
  - Ingests incoming `X-Trace-Id`, `trace-id`, or `X-Request-Id`; falls back to generating a random UUID.
  - Sets `traceId` in SLF4J MDC (`MDC.put("traceId", traceId)`).
  - Always writes both `X-Trace-Id` and `trace-id` headers on `HttpServletResponse` (for success and error responses).
  - Automatically injected into `ApiErrorResponse` (REST error payloads) and `SecurityErrorWriter` (raw security 401/403 responses).
  - All outbound inter-service HTTP clients (e.g., `NotificationServiceClient`, `IdentityServiceClient`) must propagate `X-Trace-Id` and `trace-id` from MDC.
- **Logging Level Pattern**:
  - All services configure `logging.pattern.level: "%5p [traceId=%X{traceId:-}]"` in `application.yml` so every log line is tagged with `[traceId=<id>]`.
- **SLF4J**: Annotate classes with `@Slf4j` and use structured parameter injection:
  ```java
  log.info("Creating user in Firebase Auth with email: {} and role: {}", email, role);
  log.error("Failed to persist user to database: {}", e.getMessage());
  ```
- **No System.out**: Do not use `System.out.println` in production code. The sole exception is `OtpService.echoOtp`, active only when `app.otp.console-echo=true` (local dev). Never log OTP codes otherwise.
- **Masking**: Never log plaintext passwords, full token strings, or sensitive HIPAA/GDPR clinical consent payloads.

---

## 7. Testing Standards
- **Frameworks**: JUnit 5 (`org.junit.jupiter.api.Test`), Mockito (`@Mock`, `@InjectMocks`, `when().thenReturn()`), Spring Boot Test (`@SpringBootTest`, `@AutoConfigureMockMvc`).
- **Test Database**: Run automated tests against H2 In-Memory DB using PostgreSQL compatibility mode (`jdbc:h2:mem:testdb;MODE=PostgreSQL`).
- **Mock Mode**: Enable `firebase.mock-mode=true` in `src/test/resources/application.yml` for deterministic, offline testing.
- **JDK Prerequisite**: GraalVM JDK 25 or OpenJDK 21 required to execute tests cleanly.

---

## 8. Database Migrations & Multi-Service Co-Location (Flyway)
- **Path**: `src/main/resources/db/migration/`
- **Naming Pattern**: `V{version}__{description}.sql` (e.g. `V1__init_identity_schema.sql`).
- **History Table Isolation**: When multiple microservices share the same PostgreSQL database (`hekmaai`), each service MUST configure its own Flyway schema history table with the service prefix first:
  ```yaml
  spring:
    flyway:
      table: ${FLYWAY_TABLE:<service>_flyway_schema_history}
      baseline-on-migrate: true
      baseline-version: 0
  ```
  Examples: `identity_flyway_schema_history`, `notification_flyway_schema_history`.
- **Baseline Version**: Always set `baseline-version: 0` so that if Flyway baselines an existing shared database, migration `V1` is executed rather than skipped.
- **Table & Index Prefixing**: All database objects created by a service MUST be prefixed with `<service>_` (tables: `<service>_*`, indexes: `<service>_idx_*`).
- **Immutability**: Never modify or rename a migration script that has already been executed.
- **Soft Deletion & Audit Columns**: Tables representing entities must include audit columns (`created_at`, `updated_at`, `created_by`, `updated_by`, `version`) and `is_deleted` where soft deletion applies.

---


## 9. API Conventions
- **Base Path**: REST endpoints are versioned under `/api/v1/` (e.g., `/api/v1/auth/login`, `/api/v1/users/{userId}`).
- **OpenAPI Documentation**: Annotate endpoints with `@Operation`, `@ApiResponses`, `@Tag`, and `@Schema` examples.
- **HTTP Status Codes**:
  - `200 OK`: Successful read or update.
  - `201 Created`: Resource successfully created.
  - `400 Bad Request`: Validation failure.
  - `401 Unauthorized`: Missing or invalid authentication token.
  - `403 Forbidden`: Role hierarchy violation or inactive account.
  - `404 Not Found`: Target entity not found.
  - `409 Conflict`: Unique constraint violation (email/phone already registered).
  - `429 Too Many Requests`: Rate limit exceeded / lockout active.
  - `500 Internal Server Error`: Unhandled server failure.

---

## 10. Distributed Tracing & Observability (`trace-id` / `traceId`)
Every HTTP request entering any Hekma backend service must have observable and traceable correlation context:
- **Trace Ingestion & Propagation**:
  - `TraceIdFilter` (`OncePerRequestFilter` with `@Order(Ordered.HIGHEST_PRECEDENCE)`) resolves incoming `X-Trace-Id`, `trace-id`, or `X-Request-Id`, or generates a fresh UUID.
  - Puts `traceId` in SLF4J MDC (`MDC.put("traceId", traceId)`) and cleans up in `finally`.
  - Injects response headers:
    - `X-Trace-Id: <UUID>`
    - `trace-id: <UUID>`
  - CORS configuration must expose `X-Trace-Id` and `trace-id` (`setExposedHeaders`).
  - Inter-service HTTP clients forward `X-Trace-Id`.
- **Response Payloads**:
  - **Error Responses**: `ApiErrorResponse` and `SecurityErrorWriter` provide the single `"traceId"` property.
  - **Positive Responses (2xx)**: `GlobalExceptionHandler` implements Spring `ResponseBodyAdvice<Object>`, enriching JSON object/DTO responses with the single `"traceId"` property without altering existing DTO contracts.

---

## 11. Git & Agent Workflow Invariants
- **Strict Commit & Push Restriction**: Never execute `git commit` or `git push` unless explicitly ordered in the user prompt.
- **Working Tree by Default**: Keep all modifications uncommitted in the working tree for user review.
- **Strict Plan-Only Rule**: When asked to prepare a plan, produce ONLY planning documentation. Never modify application source code directly.
