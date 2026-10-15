# Current Project State

## Current Focus
**Authority Resolution Resilience, Differential Role Authority Updates & Stale Key Cleanup (Flyway V11) — Completed (2026-10-14)**.
- **Root Cause & Fix**: Resolved `JpaSystemException: Error attempting to apply AttributeConverter` on `register-tenant` caused by legacy prototype authority key `'role:manage'` in remote DB tables.
- **Resilience**: Hardened `AuthorityConverter.convertToEntityAttribute` to warn and return `null` instead of throwing `IllegalStateException`. Updated `RoleAuthorityService`, `AuthorityService`, `FirebaseAuthenticationFilter`, and `CustomRoleService` to filter `Objects::nonNull` before constructing `EnumSet` or mapping keys.
- **Differential Role Authority Updates**: Resolved HTTP 500 error on `PUT /api/v1/system-admin/roles/{role}/authorities` caused by bulk `deleteByRole` + `saveAll` triggering unique constraint collision (`identity_uq_role_authorities`) due to Hibernate `ActionQueue` executing INSERTs before DELETEs. Replaced with differential add/remove logic for both role templates and user cascade.
- **Flyway V11 Migration**: `V11__cleanup_stale_role_manage_authority.sql` purges obsolete `'role:manage'` rows across `identity_user_authorities`, `identity_role_authorities`, `identity_custom_role_authorities`, and `identity_authorities`.
- **Dynamic UI Counts (`hekma-test-app`)**: Replaced all static `12` permission counters in `Navbar`, `ProfileModal`, `AdminPage`, `InvestigatorPage`, and `AuthContext` with dynamic counts driven by `/api/v1/authorities` and the expanded 17-authority dictionary.
- **Verification**: 295 / 295 automated tests passing in `hekma-identity-service`, Next.js build passing with 0 errors.

**Custom Roles & Role Governance Authorities (RBAC Phase 8 / Flyway V10) — Completed (2026-10-13)**.
- **Authority Catalogue Expansion**: Added 5 new granular authorities under `"Role Governance"` category: `role:read`, `role:create`, `role:update`, `role:delete`, `role:assign` (total platform authorities expanded to 17).
- **Flyway Migration `V10__custom_roles.sql`**: Created tables `identity_custom_roles`, `identity_custom_role_authorities`, `identity_user_custom_roles` with partial unique indexes, seeded authorities into catalogue and role defaults, and backfilled active staff users.
- **Domain, Repositories & Security**:
  - Implemented `CustomRoleEntity` (with `isDeleted = false`), `CustomRoleAuthorityEntity`, `UserCustomRoleEntity`.
  - Implemented `CustomRoleRepository`, `CustomRoleAuthorityRepository`, `UserCustomRoleRepository`.
  - Updated `HekmaPrincipal` with assigned `customRoles` set and `hasCustomRole(code)`.
  - Updated `FirebaseAuthenticationFilter` to dynamically aggregate direct authorities $\cup$ custom role authorities on each request.
  - Updated `MeResponse` and `UserManagementService.me()` to expose assigned custom roles.
- **Service Layer (`CustomRoleService`)**: Enforced core invariants: **Grant $\le$ Own** (users cannot bundle/assign permissions they do not hold), **Tenant Subtree Isolation** (`tenantPath` validation), **No Self-Elevation** (cannot assign to self), and soft deletion safety guard.
- **REST APIs**:
  - `POST /api/v1/custom-roles` (`role:create`)
  - `GET /api/v1/custom-roles` (`role:read`)
  - `GET /api/v1/custom-roles/{roleId}` (`role:read`)
  - `PUT /api/v1/custom-roles/{roleId}` (`role:update`)
  - `DELETE /api/v1/custom-roles/{roleId}` (`role:delete`)
  - `GET /api/v1/users/{userId}/custom-roles` (`role:read`)
  - `PUT /api/v1/users/{userId}/custom-roles` (`role:assign`)
- **Verification**: All 294 automated tests in `hekma-identity-service` passing with 0 failures, 0 errors.

**Distributed Tracing & Standardized API Request Logging across all backend microservices — Completed (2026-10-13)**.
- **Single `traceId` Contract**: Response body payloads across both positive (2xx) and error (4xx/5xx) responses carry only a single camelCase `traceId` property (removed redundant `trace-id` JSON key).
- **Dual Response Headers**: `X-Trace-Id` and `trace-id` headers are returned on all HTTP responses and exposed via CORS `Access-Control-Expose-Headers`.
- **Request Lifecycle Access Logging (`TraceIdFilter`)**:
  - Implemented high-precedence servlet filter in `hekma-identity-service`, `hekma-notification-service`, and `hekma-ctms-service`.
  - Emits `log.info("HTTP API Request Started: {} {} | traceId={}", method, fullPath, traceId)` on request start.
  - Emits `log.info("HTTP API Request Completed: {} {} | status={} | duration={}ms | traceId={}", method, fullPath, response.getStatus(), duration, traceId)` in `finally` block with execution duration.
  - Static asset noise filter bypasses swagger-ui/webjars/favicon.
  - Formatted in `application.yml` via `logging.pattern.level: "%5p [traceId=%X{traceId:-}]"`.

**System Admin Authority Catalogue & Configurable Role Default Authorities (RBAC Phase 4 Enhancement / ADR-014) — Completed**.
- **Flyway Migration `V9__role_authorities.sql`**:
  - Created `identity_role_authorities` table (`id`, `role`, `authority_key`, audit columns, unique `(role, authority_key)`).
  - Seeded baseline default authorities (all 12) for `ADMIN`, `SPONSOR`, `SITE`.
  - Backfilled existing non-deleted `ADMIN` users into `identity_user_authorities`.
  - Updated `identity_authorities.allowed_roles` to `'ADMIN,SPONSOR,SITE'`.
- **Domain & Service Layer**:
  - Implemented `RoleAuthorityEntity`, `RoleAuthorityRepository`, and extended `Authority` enum with `displayName`, `category`, and descriptions.
  - Implemented `RoleAuthorityService` providing catalogue lookup, role defaults resolution, cascade logic (`applyToExistingUsers: boolean`), and structured audit logging (`ROLE_AUTHORITIES_CHANGED`).
  - Updated `AuthorityService` to resolve `ADMIN` authorities from stored user authorities or role defaults, and allow `SYSTEM_ADMIN` to manage `ADMIN` authorities.
  - Updated `AuthService` (`registerTenant`, `inviteAdmin`) and `TenantService` (`createOwner`) to use dynamic role defaults from `RoleAuthorityService`.
- **REST Endpoints**:
  - `GET /api/v1/authorities`: Public catalogue for authenticated clients.
  - `GET /api/v1/system-admin/authorities`: Metadata catalogue for `SYSTEM_ADMIN`.
  - `GET /api/v1/system-admin/roles/authorities`: All role mappings for `SYSTEM_ADMIN`.
  - `GET /api/v1/system-admin/roles/{role}/authorities`: Single role mapping.
  - `PUT /api/v1/system-admin/roles/{role}/authorities`: Update role template with optional cascade flag (`applyToExistingUsers: boolean`). Rejects `SYSTEM_ADMIN` (immutable root) and `PATIENT` (restricted).
- **Frontend Management UI (`hekma-test-app`)**:
  - Extended `lib/types.ts` and `lib/api.ts` with authority catalogue and role authority endpoints.
  - Added dedicated "Role Permissions & Authorities" 4th tab to `app/admin/page.tsx` for `SYSTEM_ADMIN`:
    - Role selector pills (`ADMIN`, `SPONSOR`, `SITE`) showing authority count badges (`count / 12`).
    - 3 functional category grouping cards (*Tenant Governance*, *User Management*, *Clinical & Patients*) with "Select All" / "Clear" buttons and authority checkboxes.
    - Cascade configuration card (`applyToExistingUsers` toggle switch, optional audit reason input, and "Save Permissions" button).
- **Verification**:
  - All 275 backend tests in `hekma-identity-service` passing (0 failures, 0 errors).
  - Next.js production build (`npm run build`) in `hekma-test-app` passing cleanly (0 TypeScript errors).

- **Dynamic JPA Specification for Tenant Search (2026-10-12)**:
  - Fixed HTTP 500 error on `GET /api/v1/tenants` when queried by `SYSTEM_ADMIN` / `ADMIN` with no filters (`prefix = null`, `type = null`, `status = null`).
  - Replaced static JPQL query `(:pathPrefix IS NULL OR ...) AND (:type IS NULL OR ...) AND (:status IS NULL OR ...)` in `TenantRepository.java` (which caused PostgreSQL parameter type inference failure `ERROR: could not determine data type of parameter $1`) with Spring Data `JpaSpecificationExecutor<TenantEntity>` and dynamic `Specification<TenantEntity>` in `TenantService.java`.
  - Added test coverage in `TenantHierarchyIntegrationTest` verifying platform admin tenant listings without filters and with filters.

- **Public GraphiQL IDE & Schema Documentation (2026-10-13)**:
  - Enabled GraphiQL and schema introspection by default in `application.yml` (`GRAPHIQL_ENABLED:true`, `GRAPHQL_INTROSPECTION_ENABLED:true`).
  - Configured `SecurityConfig` to permit `/graphiql` and `/graphiql/**` publicly without authentication across all HTTP methods.
  - Added filter bypass in `FirebaseAuthenticationFilter.shouldNotFilter()` ensuring browser requests to `/graphiql` are never blocked by missing or stale tokens.
  - Documented GraphiQL usage and header configuration in `docs/API_DOCUMENTATION.md` and repository READMEs across microservices.

- **Client-Side Auth State Clean-Up on Logout (`hekma-test-app`) (2026-10-13)**:
  - Updated `Navbar.tsx` and `authContext.tsx` to wipe all authentication tokens and credentials from `localStorage` (`hekma_auth_user`, `token`, `idToken`, etc.) and redirect immediately to `/login`.

- **Password management via Java API only (2026-10-07)**: added `POST /api/v1/auth/change-password` (authenticated; validates the current password through Firebase, stores the new one via Admin SDK, revokes sessions, returns new tokens) and a shared `@StrongPassword` policy on every password-setting DTO. Passwords live only in Firebase.
- **RBAC Phase 1 — Authentication Containment (2026-10-07)**:
  - `FirebaseAuthenticationFilter` verifies `Authorization: Bearer <Firebase ID token>` (revocation-checked) and builds `HekmaPrincipal` from PostgreSQL; `SecurityConfig` is deny-by-default with an exact public `POST` endpoint list and `@EnableMethodSecurity`; every protected REST/GraphQL handler has `@PreAuthorize`.
  - Removed `X-Operator-Id` / `operatorId` everywhere; `TenantFilter` derives tenant from the principal (foreign `X-Tenant-ID` → 404).
  - Fixed: unauthenticated `invite-admin`; `reset-password` not checking the OTP; phone-only and missing-Web-API-key login paths issuing tokens without a password check; silent mock-Firebase fallback in production; PATIENT callers listing all patients; JPA auditor writing the principal `toString()`.
  - Public registration is PATIENT-only (no `tenantId`/`tenantSlug`); phone-only accounts get a synthetic Firebase login email (`auth_email`, Flyway V3).
  - Session revocation on deactivation/soft delete/password reset; `otp/verify` returns an ID token; uniform forgot-password response.
  - Config: `NOTIFICATION_SERVICE_KEY` required (no default), `OTP_CONSOLE_ECHO`, `APP_CORS_ALLOWED_ORIGINS`, `APP_EXPOSE_API_DOCS`, `GRAPHIQL_ENABLED`, `GRAPHQL_INTROSPECTION_ENABLED` (all off by default); live mode requires `FIREBASE_WEB_API_KEY`.

- **Pending Account Verification & Self-Service OTP Activation Flow**:
  - Implemented client-side detection in `hekma-test-app` (`app/login/page.tsx`) for `403 Forbidden` (`pending_verification`) authentication errors.
  - Displayed an interactive, accessible amber notification card featuring a **"Verify & Activate Account"** button that invokes `authApi.resendOtp(...)` using the input email or phone.
  - Opened the unified `<OtpModal>` with `purpose="REGISTRATION"`, enabling seamless 6-digit code entry, account activation, token receipt, and automatic dashboard redirection upon successful verification.
  - Enhanced backend resilience in `OtpService` (`verifyOtp` and `resendOtp`) with fallback resolution by `targetUserId`, `email`, and `phoneNumber` whenever an initial `attemptId` is missing or passed as a user UUID.
  - Resolved `UserInactiveException` by scoping activation logic for `PENDING_VERIFICATION` users before inactive account assertions.
  - Avoided Firebase Admin SDK reserved key rejection (`developerClaims must not contain a reserved key: tenant_id`) by mapping custom token claims to camelCase `tenantId`.
- **Production-Ready Web Application UI Transition (`hekma-test-app`)**:
  - Eliminated mock/sandbox impersonation mechanism (`DEMO_USERS` and `impersonate()`) from `lib/authContext.tsx`.
  - Removed quick demo role switcher dropdown from `Navbar.tsx` and replaced it with an authentic user profile display and direct navigation link to the user's role-specific workspace (`/admin`, `/investigator`, `/patient`).
  - Removed developer sandbox 1-click preset logins from `app/login/page.tsx` and sanitized all demo OTP tips (`123456`) from `OtpModal.tsx`, `login/page.tsx`, and `forgot-password/page.tsx`.
  - Refactored `app/page.tsx` home page from an interactive dummy sandbox launcher into authentic platform capability cards with role-aware action buttons.
  - Added strict authentication and authorization route guards across `/admin`, `/investigator`, and `/patient` displaying dedicated authentication-required and access-restricted views when unauthenticated or unauthorized.
  - Replaced hardcoded fallback mock patient/user/tenant data arrays in console tables with real error handling and empty states.
  - Successfully verified production build (`next build`) across all 9 App Router routes with zero TypeScript errors or regressions.
- **Self-Service Password Reset & Console Logging Enhancements**:
  - Implemented `/api/v1/auth/forgot-password` and `/api/v1/auth/reset-password` endpoints supporting email/phone identifier dispatch with OTP verification and Firebase password updates.
  - Enabled Spring MVC CORS configuration in `SecurityConfig.java` with `CorsConfigurationSource` to support seamless browser requests from `http://localhost:3000`.
  - Added high-visibility terminal banners (`System.out.println` and `log.info`) in `AuthController.java`, `AuthService.java`, and `OtpService.java` for password reset OTP generation (`>>> [PASSWORD_RESET OTP - EMAIL / PHONE]`), requests, and completions.
  - Configured `OtpService` to unconditionally echo plaintext OTPs to stdout/logger for `PASSWORD_RESET` requests (`/api/v1/auth/forgot-password`) to streamline local development testing.
  - Added structured browser console logging (`console.log`, `console.error`) in `hekma-test-app` across `lib/api.ts`, `/login`, and `/forgot-password`.
- **Multi-Tenancy Subsystem Complete Implementation**:
  - **Database Migration (`V2__create_tenants_and_multitenancy.sql`)**: Created `identity_tenants` table with partial unique index on `default_tenant = TRUE`, seeded default tenant (`00000000-0000-0000-0000-000000000001`, `default-tenant`), added `tenant_id` to `identity_users`, enforced role-tenancy invariant check constraint `identity_chk_users_tenant_role`, and added `assigned_user_id` to `identity_patient_details`.
  - **Domain & Repository Layer**: Created `TenantEntity`, `TenantType` (`SPONSOR`, `SITE`, `GENERAL`), `TenantStatus` (`ACTIVE`, `SUSPENDED`, `INACTIVE`), and `TenantRepository` with `findByDefaultTenantTrue()`. Updated `UserEntity` with `@ManyToOne TenantEntity tenant` and `PatientDetailEntity` with `@ManyToOne UserEntity assignedUser`.
  - **Administrative Bootstrap Alignment**: Created `PlatformAdminProperties` and `AdminInitializer` (`@Order(20)`) to auto-bootstrap platform operational administrator (`admin@hekma.com`, `Role.ADMIN`, `tenant = null`) alongside root `SYSTEM_ADMIN` (`system.admin@hekma.com`), generating cryptographically secure random passwords.
  - **Tenant Request Resolution & Security Context**: Created `TenantContext` (ThreadLocal with `setSystemBypass`) and `TenantFilter` (resolving `X-Tenant-ID` header, enforcing active status for organizational roles, bypassing for platform administrators).
  - **Tenant & Role Custom Claims**: Added `assignClaims(uid, role, tenantId)` across `FirebaseService`, `FirebaseAuthService`, and `MockFirebaseService`.
  - **Registration & Default Tenant Fallback**: Updated `AuthService.register` to validate and resolve tenants for `SPONSOR`, `SITE`, and `PATIENT`. Directly registering patients without an invitation automatically associate with the Default Tenant (`default-tenant`, Hekma) and generate a `PatientDetailEntity` in the unassigned pool.
  - **Tenant Management REST API (`/api/v1/tenants`)**: Implemented `TenantController`, `TenantService`, DTOs (`TenantCreateRequest`, `TenantUpdateRequest`, `TenantStatusUpdateRequest`, `TenantResponse`), and protected the Default Tenant from suspension or deactivation.
  - **Patient Recruitment, Invitation & Mapping API (`/api/v1/patients`)**: Implemented `PatientController`, `PatientService`, DTOs (`PatientInviteRequest`, `PatientInviteResponse`, `PatientAcceptInviteRequest`, `PatientAssignRequest`, `PatientResponse`):
    - `POST /invite`: Staging user, mapping `assigned_user_id`, adopting caller tenant, dispatching invitation email via `NotificationServiceClient`.
    - `POST /accept-invite`: Public activation validating HIPAA/GDPR consents, creating Firebase user with custom claims, activating profile.
    - `GET /patients`: Scoped to caller tenant for `SPONSOR`/`SITE`; supports `assignedToMe=true`. Unassigned pool visible to platform admins.
    - `PATCH /patients/{patientId}/assign`: Reassignment to another investigator within tenant.
  - **Standardized Pagination Wrapper**: Implemented `PagedResponse<T>` for clean JSON serialization and Swagger documentation.
  - **Test Suite Verification**: Complete test suite increased to 174 automated tests (100% passing without regressions).
- **Distributed Tracing & Trace ID Across All Backend Microservices (ADR-015 / 2026-10-13)**:
  - Implemented `TraceIdFilter` (`@Order(Ordered.HIGHEST_PRECEDENCE)`) across `hekma-identity-service`, `hekma-notification-service`, and `hekma-ctms-service`.
  - Ingests incoming `X-Trace-Id`, `trace-id`, or `X-Request-Id`; falls back to generating a random UUID.
  - Stores `traceId` in SLF4J MDC, ensuring automatic MDC cleanup in a `finally` block.
  - Returns both `X-Trace-Id` and `trace-id` HTTP response headers on every response (2xx success, 4xx client errors, 5xx failures), and exposes them in CORS `Access-Control-Expose-Headers`.
  - Automatically injects the single `"traceId"` property into positive response bodies (2xx) via Spring `ResponseBodyAdvice<Object>` using robust `LinkedHashMap` transformation, preserving existing DTO attributes and serializations.
  - Automatically injects the single `"traceId"` property into all REST error payloads (`ApiErrorResponse`) and raw security 401/403 responses via `SecurityErrorWriter`.
  - Propagates `X-Trace-Id` and `trace-id` on outbound inter-service HTTP requests (`NotificationServiceClient` in identity service, `IdentityServiceClient` in CTMS service).
  - Enforced structured console log pattern `logging.pattern.level: "%5p [traceId=%X{traceId:-}]"` in `application.yml` across all backend services.
  - Verified test suites: `hekma-identity-service` (278/278 passing), `hekma-notification-service` (40/40 passing), `hekma-ctms-service` (16/16 passing).

- **Authority Catalogue & Role Permissions Visibility in Management UI (`hekma-test-app`) (2026-10-13)**:
  - In `lib/types.ts`: Exported `DEFAULT_AUTHORITIES_CATALOG` with all 12 platform authorities across Tenant Governance, User Management, and Clinical & Patients categories.
  - In `app/admin/page.tsx`:
    - Initialized state with `DEFAULT_AUTHORITIES_CATALOG` and full default authorities map so the list is rendered immediately without waiting or failing.
    - Added an **Active Permissions Roster (Pill Cloud)** under role pills with checkmarks, quick "Select All (12)" / "Deselect All", and `(x)` remove buttons.
    - Added live search filter and status filter tabs (`All`, `Granted`, `Restricted`).
    - Verified production build (`npm run build`) passing cleanly with 0 TypeScript errors.

- **Multi-Tenancy Architecture Plan**: Authored [docs/MULTITENANCY_PLAN.md](file:///D:/coding/hekma/hekma-identity-service/docs/MULTITENANCY_PLAN.md).
- **Fresh Database Consolidation, Table & Index Prefixing**: Consolidated all migrations (V1–V8) into a single baseline migration `V1__init_identity_schema.sql`, prefixed all tables with `identity_` (`identity_users`, `identity_patient_details`, `identity_otp_requests`, `identity_otp_lockouts`, `identity_otp_audit_logs`), and standardized all database indexes to `identity_idx_*`.
- **Shared Database Migration Isolation**: Configured custom Flyway schema history table (`spring.flyway.table = identity_flyway_schema_history`) and `baseline-version: 0`.

## In Progress
- None (current tasks completed and verified).

## Pending
- `hekma-test-app` must send `Authorization: Bearer <idToken>`, stop sending `X-Operator-Id`, and use `idToken` from `otp/verify` (breaking change from RBAC Phase 1).
- Purge of tenant registrations that never verify their OTP (OD-6) is deferred.
- Staff invitation accept page (`/invitations/accept?token=`) does not exist yet in the frontend.
- Alignment with downstream services (`hekma-notification-service`, `hekma-study-service`) to consume `tenant_id` claims and patient mapping.

## Known Issues
- All 278 automated tests passing in `hekma-identity-service`.
- Mock mode (`firebase.mock-mode=true`) is active for local development and CI testing. Mock passwords are now verified; bootstrapped admins have random passwords (use forgot/reset password with `OTP_CONSOLE_ECHO=true`).
- Legacy phone-only accounts (no `auth_email`) must reset their password before password login works.
- `application.yml` still contains a default datasource URL/username/password; these should move to environment configuration.

## Related Jira Issues
- None referenced in Git commit history (repository adheres to Conventional Commits: `feat`, `fix`, `docs`).
