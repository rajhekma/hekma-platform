# Development Log: Hekma Identity Service (`hekma-identity-service`)

This log maintains a chronological record of significant milestones, completed features, architectural additions, and upcoming work.

---

## Chronological Milestone Log

### 2026-10-14: Authority Resolution Resilience, Differential Role Authority Updates & Dynamic UI Counts
- **Type**: Bugfix & Resilience Hardening
- **Description**:
  - Resolved `JpaSystemException: Error attempting to apply AttributeConverter` on `POST /api/v1/auth/register-tenant` caused by unknown prototype authority key (`role:manage`) present in remote database tables.
  - Hardened `AuthorityConverter.convertToEntityAttribute` to log a warning and return `null` instead of throwing `IllegalStateException`.
  - Added null-safe stream filtering across `RoleAuthorityService`, `AuthorityService`, `FirebaseAuthenticationFilter`, and `CustomRoleService`.
  - Added Flyway migration `V11__cleanup_stale_role_manage_authority.sql` to purge obsolete `role:manage` entries from `identity_user_authorities`, `identity_role_authorities`, `identity_custom_role_authorities`, and `identity_authorities`.
  - Fixed `PUT /api/v1/system-admin/roles/{role}/authorities` HTTP 500 error: replaced bulk `deleteByRole` + `saveAll` with differential add/remove logic, eliminating Hibernate `ActionQueue` insert-before-delete unique constraint collisions on `identity_uq_role_authorities`.
  - Frontend (`hekma-test-app`): Replaced all static `12` permission counters with dynamic counts derived from the backend authority catalogue and fallback dictionary (expanded with all 17 platform authorities).
  - Verified tests: 295 / 295 tests passing in `hekma-identity-service`, Next.js production build passing with 0 errors.

### 2026-10-13: Custom Roles & Role Governance Authorities (RBAC Phase 8 / Flyway V10)
- **Type**: IAM & Custom Role Governance
- **Description**:
  - Expanded platform authority catalogue with 5 new fine-grained permissions: `role:read`, `role:create`, `role:update`, `role:delete`, `role:assign` (total platform authorities expanded to 17).
  - Flyway migration `V10__custom_roles.sql`:
    - Cleaned up pre-Flyway legacy prototype tables (`identity_custom_role_groups`, `identity_permission_group_authorities`, `identity_permission_groups`, `identity_user_custom_roles`, `identity_custom_role_authorities`, `identity_custom_roles`).
    - Created normalized tables `identity_custom_roles`, `identity_custom_role_authorities`, and `identity_user_custom_roles` with partial unique index on `(COALESCE(tenant_id, ...), code) WHERE is_deleted = FALSE`.
    - Seeded 7 standard global system role templates (`SPONSOR_ADMIN`, `STUDY_MANAGER`, `SPONSOR_VIEWER`, `SITE_ADMIN`, `PRINCIPAL_INVESTIGATOR`, `STUDY_COORDINATOR`, `SITE_VIEWER`) with their corresponding bundled authorities.
    - Updated `identity_role_authorities` and backfilled active staff users in `identity_user_authorities`.
  - Implemented domain entities (`CustomRoleEntity`, `CustomRoleAuthorityEntity`, `UserCustomRoleEntity`) and Spring Data repositories.
  - Implemented `CustomRoleService` enforcing: **Grant $\le$ Own** non-elevation checks, **Subtree Isolation** validation, **No Self-Assignment** restrictions, and safe soft deletion.
  - Dynamic granted authorities aggregation in `FirebaseAuthenticationFilter`: effective authorities = direct user authorities $\cup$ custom role authorities.
  - Added REST APIs: `/api/v1/custom-roles/**` and `/api/v1/users/{userId}/custom-roles`.
  - Verified against shared PostgreSQL database (`87.106.50.234:5432/common`) and local test suite. Tests: 294 / 294 passing (16 new).

### 2026-10-13: Universal Trace Correlation, Single traceId Contract & API Access Logging
- **Type**: Observability & Distributed Tracing
- **Description**:
  - Implemented high-precedence `TraceIdFilter` across all backend services (`hekma-identity-service`, `hekma-notification-service`, `hekma-ctms-service`) capturing incoming `X-Trace-Id`, `trace-id`, or `X-Request-Id`, or generating a new UUID v4.
  - Standardized JSON response payload contract to output a single camelCase `traceId` property across both positive (2xx) and error (4xx/5xx) responses, removing duplicate `trace-id` fields.
  - Preserved dual outgoing HTTP response headers `X-Trace-Id` and `trace-id` with full CORS exposure (`Access-Control-Expose-Headers`).
  - Added structured HTTP request lifecycle logging in `TraceIdFilter`:
    - Entry: `HTTP API Request Started: <METHOD> <URI> | traceId=<id>`
    - Completion: `HTTP API Request Completed: <METHOD> <URI> | status=<status> | duration=<ms>ms | traceId=<id>`
    - Static assets (`/swagger-ui/**`, `/webjars/**`, `/favicon.ico`) bypass info logging.
  - Verified test suites across all 3 services: 278 / 278 (`identity`), 40 / 40 (`notification`), 16 / 16 (`ctms`).

### 2026-10-13: System Admin Authority Catalogue & Dynamic Role Authorities (ADR-014)
- **Type**: IAM & Authorization Feature (RBAC Phase 4 Enhancement)
- **Description**:
  - Flyway migration `V9__role_authorities.sql`: Created `identity_role_authorities` table with unique constraint on `(role, authority_key)`. Seeded baseline authorities for `ADMIN`, `SPONSOR`, and `SITE`. Backfilled non-deleted `ADMIN` users into `identity_user_authorities`.
  - Implemented `RoleAuthorityEntity`, `RoleAuthorityRepository`, and extended `Authority` enum with display names, descriptions, and functional categories (*Tenant Governance*, *User Management*, *Clinical & Patients*).
  - Implemented `RoleAuthorityService` providing catalogue lookup, role defaults resolution, and cascade updates (`applyToExistingUsers: boolean`) with audit event `ROLE_AUTHORITIES_CHANGED`.
  - Added REST endpoints under `/api/v1/authorities` and `/api/v1/system-admin/roles/**`.
  - Built frontend "Role Permissions & Authorities" tab in `hekma-test-app` under `/admin`.
  - Tests: 278 passing in `hekma-identity-service`.

### 2026-10-07: RBAC Phase 3 — Per-User Authorities, Staff Invitations & Audit
- **Type**: Authorization Feature (see [RBAC_PLAN.md](RBAC_PLAN.md))
- **Description**:
  - Migrations V5–V8: authority catalogue + `identity_user_authorities`, owner-bundle backfill for existing SPONSOR/SITE users, single-`SYSTEM_ADMIN` partial unique index, patient invitation expiry/used columns, `identity_user_invitations`, append-only `identity_authz_audit_log`.
  - 12 authorities (`Authority` enum); loaded from the database into `HekmaPrincipal` and Spring granted authorities on every request; platform admins hold all, patients none. Endpoints now use `hasAuthority('…')`.
  - Grant ≤ own and no self-change for `PUT /api/v1/users/{id}/authorities`; `GET /api/v1/users/{id}/authorities`; `GET /api/v1/users` (scoped); SPONSOR/SITE with `user:manage` manage users in their subtree.
  - Staff invitations: `POST /api/v1/users/invite` (role = tenant type, authorities capped by inviter, 72 h single-use hashed token) and public `POST /api/v1/users/accept-invite`.
  - `GET /api/v1/me`, `GET /api/v1/me/authorities`; `PATCH /api/v1/patients/{id}`; patient invitations expire after 72 h and are single-use.
  - Audit entries for authority, user-status, tenant, invitation and patient-assignment actions.
  - Build guard `AuthorizationGuardTest`: every REST/GraphQL handler must declare `@PreAuthorize` or be on the public list.
  - Tests: 265 passing (14 new).

### 2026-10-07: RBAC Phase 2 — Tenant Hierarchy & Tenant Self-Registration
- **Type**: Multi-Tenancy Feature (see [RBAC_PLAN.md](RBAC_PLAN.md))
- **Description**:
  - Flyway `V4__tenant_hierarchy.sql`: `parent_tenant_id`, materialized `path`, `depth`; tenant IDs are now application-assigned so the path can be computed on insert.
  - `POST /api/v1/auth/register-tenant` (public): new top-level SPONSOR/SITE tenant + owner (role = type), `PENDING_VERIFICATION` until OTP verification activates both; Firebase rollback on failure. Admin-side `POST /api/v1/tenants` removed (OD-1).
  - `POST /api/v1/tenants/{id}/sub-tenants` (any type, any depth, optional owner), `GET /api/v1/tenants/{id}/children`; tenant, user and patient reads scoped to the caller's subtree; staff may suspend only strict descendants.
  - Suspension cascade: the auth filter and login reject users whose tenant or any ancestor is not `ACTIVE`.
  - Patient invitations can target a sub-tenant and assign a user from an ancestor tenant; assignments require the assignee's tenant to contain the patient's tenant.
  - Fixed pre-existing bugs: patient invitation failed on real databases (`firebase_uid` NULL on the staged user); 405/404/bad-parameter errors returned 500; login read the lazily loaded tenant outside a transaction.
  - Tests: 251 passing (21 new), incl. `TenantHierarchyIntegrationTest`.

### 2026-10-07: Password Management Through the Java API
- **Type**: Authentication Feature
- **Description**:
  - Added `POST /api/v1/auth/change-password` (authenticated): current password validated via Firebase, new password stored via Admin SDK, all sessions revoked, fresh tokens returned.
  - Added `@StrongPassword` (`validation` package): 8–128 chars, upper, lower, digit, special, no edge whitespace; applied to register, admin invitation, invitation acceptance, reset and change password.
  - Tests: 230 passing (17 new).

### 2026-10-07: RBAC Phase 1 — Authentication Containment
- **Type**: Security Hardening (see [RBAC_PLAN.md](RBAC_PLAN.md))
- **Description**:
  - Added `FirebaseAuthenticationFilter`: every non-public request must carry `Authorization: Bearer <Firebase ID token>`, verified with revocation checks; role/tenant are loaded from PostgreSQL into `HekmaPrincipal`.
  - Rewrote `SecurityConfig` to deny by default with an exact list of public `POST` endpoints; added `@EnableMethodSecurity` and `@PreAuthorize` on every protected REST/GraphQL handler.
  - Removed client-supplied identity (`X-Operator-Id` header, `operatorId` body/query/GraphQL arguments). `TenantFilter` now derives tenant context from the principal and rejects foreign `X-Tenant-ID` values with `404`.
  - Closed critical gaps found during implementation: unauthenticated `invite-admin`; `reset-password` ignoring the OTP; phone-only login and missing-Web-API-key fallback issuing tokens without a password check; silent fallback to the mock Firebase service when credentials were missing; `PATIENT` callers listing all patients.
  - Public self-registration restricted to `PATIENT` (no more joining an existing tenant via `tenantId`/`tenantSlug`).
  - Phone-only accounts get a synthetic Firebase login email (`identity_users.auth_email`, migration V3) so all passwords are validated through Firebase by the Java API.
  - Sessions are revoked on deactivation, soft deletion and password reset; `otp/verify` now returns a Firebase ID token.
  - Removed the in-code notification service key default; OTP console output gated behind `app.otp.console-echo`; CORS origins, API docs, GraphiQL and introspection are configuration-driven and off by default.
  - Tests: 213 passing (33 new), including a full-filter-chain access matrix (`SecurityAccessIntegrationTest`).

### 2026-10-06: Pending Account Verification & Self-Service OTP Activation Flow
- **Type**: Authentication Flow Enhancement & Error Handling UX
- **Description**:
  - Implemented automatic detection in `hekma-test-app` (`app/login/page.tsx`) when login fails with `403 Forbidden` (`pending_verification`).
  - Added interactive amber alert card with an immediate **"Verify & Activate Account"** action triggering `authApi.resendOtp(...)` using the entered identifier (email or phone).
  - Wired the `<OtpModal>` with `purpose="REGISTRATION"` to verify 6-digit OTP, activate the user to `ACTIVE`, receive authentication tokens, and route immediately to the role workspace.
  - Hardened backend `OtpService` in `hekma-identity-service` with multi-strategy resolution (`targetUserId`, `email`, `phoneNumber`) on both `/otp/verify` and `/otp/resend`, preventing `401 Unauthorized (Authentication attempt not found)` when client callers pass `userId` or miss initial `attemptId`.
  - Maintained 100% test coverage: all 174 automated tests passing.

### 2026-10-06: Production-Ready Web Application UI Transition (`hekma-test-app`)
- **Type**: Frontend Production Hardening & Security Guards
- **Description**:
  - Removed developer sandbox impersonation (`DEMO_USERS`, `impersonate()`) and quick demo role switchers from the UI.
  - Replaced demo launchers with authentic platform capability cards and direct, role-scoped links to `/admin`, `/investigator`, and `/patient`.
  - Added strict authentication and authorization route guards with dedicated access-restricted and signin-prompt views.
  - Sanitized mock demo OTP bypasses (`123456`) and tips across all authentication modals.
  - Verified production build (`next build`) across all 9 App Router routes with zero TypeScript or bundling errors.

### 2026-10-06: Self-Service Password Reset & Unified Portal Integration
- **Type**: Authentication Feature & Frontend Integration
- **Description**:
  - Implemented `/api/v1/auth/forgot-password` and `/api/v1/auth/reset-password` endpoints supporting email/phone identifier dispatch with OTP verification and Firebase password updates.
  - Added `PASSWORD_RESET` to `OtpPurpose` and `updatePassword` to `FirebaseService`, `FirebaseAuthService`, and `MockFirebaseService`.
  - Added "Forgot password?" self-service option on the signin page in `hekma-test-app` with 3-step interactive modal and dedicated `/forgot-password` route.
  - Verified backend test suite: 174 tests passing with zero regressions.

### 2026-10-05: Planning Boundary & Documentation Synchronization Governance
- **Type**: Agent Governance & Workflow Invariant
- **Description**:
  - Enforced a strict plan-only boundary in [AGENTS.md](file:///D:/coding/hekma/hekma-identity-service/AGENTS.md): when asked to prepare a plan, agents must ONLY produce planning documentation and must NEVER execute implementation code or modify application source code directly.
  - Formalized documentation synchronization rules and multi-developer collaboration invariants.

### 2026-10-01: Centralized Project Context & Documentation Infrastructure
- **Type**: Documentation & Agent Governance
- **Description**:
  - Established persistent, shared project context across Git to support multiple developers and AI coding agents.
  - Expanded [AGENTS.md](file:///D:/coding/hekma/hekma-identity-service/AGENTS.md) with comprehensive tech stack, architectural rules, coding standards, and workflow instructions.
  - Created standardized documentation suite:
    - [docs/PROJECT_CONTEXT.md](file:///D:/coding/hekma/hekma-identity-service/docs/PROJECT_CONTEXT.md): Core business requirements, roles, consent tracking, and limitations.
    - [docs/ARCHITECTURE.md](file:///D:/coding/hekma/hekma-identity-service/docs/ARCHITECTURE.md): Component diagrams, dual-write saga with compensating rollbacks, and communication flows.
    - [docs/DATABASE.md](file:///D:/coding/hekma/hekma-identity-service/docs/DATABASE.md): PostgreSQL schema specifications, ERD, and Flyway migrations (V1–V8).
    - [docs/API_DOCUMENTATION.md](file:///D:/coding/hekma/hekma-identity-service/docs/API_DOCUMENTATION.md): REST endpoints, GraphQL queries/mutations, schemas, and error responses.
    - [docs/DEVELOPMENT_LOG.md](file:///D:/coding/hekma/hekma-identity-service/docs/DEVELOPMENT_LOG.md): Chronological development history.
    - [docs/DECISIONS.md](file:///D:/coding/hekma/hekma-identity-service/docs/DECISIONS.md): Architecture Decision Records (ADRs).
  - Verified test suite: 139 tests passing with GraalVM JDK 25.

### 2026-10-01: README Streamlining & OpenAPI Tag Grouping
- **Git Commit**: `c05ff83` ("docs: streamline README.md to high-level features, tools, and versions")
- **Git Commit**: `72c9666` ("feat(docs): group all authentication and OTP endpoints under Authentication tag")
- **Description**:
  - Streamlined root `README.md` to high-level feature overviews, explicit dependency version matrices, and interactive UI pointers.
  - Grouped all authentication and OTP REST endpoints under the unified `Authentication` OpenAPI tag.

### 2026-09-30: Login API & Conditional 2FA for Patient Profiles
- **Git Commit**: `a5e4b86` ("feat: add login API and conditional 2FA for patient profiles")
- **Description**:
  - Implemented `/api/v1/auth/login` endpoint supporting dual identifier formats (email or phone).
  - Introduced conditional Two-Factor Authentication (2FA) for `PATIENT` role:
    - If `twoFactorEnabled == true`, triggers OTP challenge, returning `twoFactorRequired: true` and withholding JWT tokens until verified.
    - If `twoFactorEnabled == false` or non-patient role, grants direct login with Firebase ID and refresh tokens.
  - Added Flyway migration `V8__add_two_factor_enabled_to_users.sql` and `PATCH /api/v1/users/{userId}/2fa`.

### 2026-09-30: Verification Modes & Verification Flags
- **Git Commit**: `4968fea` ("feat: replace OTP channel with verification mode and add phoneVerified/emailVerified/verificationMode flags")
- **Description**:
  - Replaced legacy OTP channel with enum `VerificationMode` (`PHONE`, `EMAIL`).
  - Added `phone_verified`, `email_verified`, and `verification_mode` columns across database entities via migration `V7`.
  - Allowed nullable email in `users` and nullable phone in `otp_requests` to support phone-first and email-first onboarding.

### 2026-09-29: Security Auditing, OTP Subsystem & Soft Deletion
- **Git Commit**: `c3599d0` ("feat: add audit entity, otp flow, user status hierarchy and soft deletion with SQLRestriction")
- **Description**:
  - Introduced `BaseAuditEntity` with `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy`, and optimistic locking `@Version`.
  - Implemented complete OTP engine (`OtpService`): 6-digit numeric generation, BCrypt hash storage, 5-minute expiry, max 5 attempts, max 3 resends.
  - Implemented rate limiting and lockout mechanism (`OtpLockoutEntity`) enforcing max 5 OTPs per hour and 30-minute lockout.
  - Introduced immutable security audit logging (`OtpAuditLogEntity`).
  - Implemented user status transitions (`ACTIVE`, `INACTIVE`, `PENDING_VERIFICATION`, `SUSPENDED`) and administrative role hierarchy enforcement.
  - Implemented soft deletion using Hibernate `@SQLRestriction("is_deleted = false")`.
  - Added Flyway migrations `V3`, `V4`, `V5`, and `V6`.

### 2026-09-29: Token Refresh & Google STS Integration
- **Git Commit**: `fb2c8d9` ("feat: add token refresh endpoint and Google STS integration")
- **Description**:
  - Implemented `/api/v1/auth/refresh-token` exchanging OAuth2 refresh tokens for new Firebase ID tokens via Google Secure Token Service (`securetoken.googleapis.com`).
  - Added PostgreSQL verification ensuring the user exists and is active before returning refreshed tokens.

### 2026-09-29: GraphQL Admin Directory & Batch Mapping
- **Git Commit**: `77f7294` ("feat(graphql): add GraphQL API for System Admin to query all users with role filtering")
- **Description**:
  - Implemented Spring for GraphQL endpoint (`/graphql`) and GraphiQL IDE (`/graphiql`).
  - Added queries: `users(role: Role)`, `userById(id: ID!)`, `userByEmail(email: String!)`, `userCount(role: Role)`.
  - Added mutations: `updateUserActiveStatus`, `softDeleteUser`, `updateUserTwoFactor`.
  - Implemented `@BatchMapping` for `patientDetails` to eliminate N+1 queries.

### 2026-09-28: Core Identity Setup, Patient Onboarding & System Admin Bootstrap
- **Git Commit**: `8b564ef` ("feat(auth): implement Firebase registration, patient onboarding, system admin separation, and OpenAPI docs")
- **Git Commit**: `9c04d99` ("initial commit")
- **Description**:
  - Established project structure using Spring Boot 4.1.1 and Java 25.
  - Configured Firebase Admin SDK and `MockFirebaseService` for offline development.
  - Implemented public self-registration (`/api/v1/auth/register`) for `SPONSOR`, `SITE`, and `PATIENT` roles.
  - Implemented `SystemAdminInitializer` for auto-bootstrapping `SYSTEM_ADMIN` with cryptographically secure random password.
  - Implemented `POST /api/v1/system-admin/invite-admin` for administrative delegation.
  - Created Flyway migrations `V1__create_users_table.sql` and `V2__create_patient_details_table.sql`.
  - Integrated SpringDoc OpenAPI with Swagger UI (`/swagger-ui.html`).

---

---

## 2026-10-06: Milestone – Complete Multi-Tenancy Subsystem Implementation

- **Database Migration (`V2__create_tenants_and_multitenancy.sql`)**:
  - Provisioned `identity_tenants` table with partial unique index on `default_tenant = TRUE`.
  - Bootstrapped Default Organization (`00000000-0000-0000-0000-000000000001`, `default-tenant`, `default_tenant = TRUE`).
  - Added `tenant_id` to `identity_users` with foreign key constraint to `identity_tenants(id)`.
  - Added database check constraint `identity_chk_users_tenant_role` enforcing:
    `((role IN ('SPONSOR', 'SITE', 'PATIENT') AND tenant_id IS NOT NULL) OR (role IN ('SYSTEM_ADMIN', 'ADMIN') AND tenant_id IS NULL))`.
  - Added `assigned_user_id` to `identity_patient_details` linking patients directly to their inviting `SITE` or `SPONSOR` investigator.
- **Tenant Entity & Repository Layer**:
  - Created `TenantEntity` extending `BaseAuditEntity`.
  - Created `TenantType` (`SPONSOR`, `SITE`, `GENERAL`) and `TenantStatus` (`ACTIVE`, `SUSPENDED`, `INACTIVE`).
  - Created `TenantRepository` with `findByDefaultTenantTrue()`, `findBySlug()`, and pagination queries.
  - Updated `UserEntity` with `@ManyToOne TenantEntity tenant` and helper `getTenantId()`.
  - Updated `PatientDetailEntity` with `@ManyToOne UserEntity assignedUser` and helper `getAssignedUserId()`.
- **Administrative Bootstrap Alignment**:
  - Added `PlatformAdminProperties` and `AdminInitializer` (`@Order(20)`), bootstrapping platform operational admin `admin@hekma.com` (`Role.ADMIN`, `tenant = null`) with a 20-character secure random password and Firebase password reset capabilities.
- **Tenant Context & Request Resolution**:
  - Implemented `TenantContext` (ThreadLocal with `setSystemBypass`).
  - Implemented `TenantFilter` registered before `UsernamePasswordAuthenticationFilter`.
  - Updated `FirebaseService` with `assignClaims(uid, role, tenantId)` across live and mock implementations.
- **Tenant Management REST API (`/api/v1/tenants`)**:
  - Implemented `TenantController`, `TenantService`, DTOs (`TenantCreateRequest`, `TenantUpdateRequest`, `TenantStatusUpdateRequest`, `TenantResponse`).
  - Protected the Default Platform Organization (`default_tenant = TRUE`) from suspension or deactivation.
- **Patient Recruitment, Invitation & Mapping API (`/api/v1/patients`)**:
  - `POST /invite`: Authorized for `SPONSOR`/`SITE`; stages user profile, maps `assigned_user_id`, inherits caller tenant, and dispatches invitation email via `NotificationServiceClient`.
  - `POST /accept-invite`: Public endpoint validating regulatory consents (Terms, Privacy, Health Data), provisioning Firebase user with custom claims, and activating profile.
  - `GET /patients`: Scoped to caller tenant for `SPONSOR`/`SITE`; supports `assignedToMe=true`. Platform admins can view default tenant unassigned pool.
  - `PATCH /patients/{patientId}/assign`: Reassigns patient to another investigator within tenant.
- **Direct Patient Public Self-Registration Fallback**:
  - Patients self-registering without an invitation code automatically associate with the Default Tenant (`default-tenant`, Hekma) and are staged in the unassigned pool.
- **Standardized Pagination (`PagedResponse<T>`)**:
  - Created `PagedResponse<T>` for clean JSON serialization across REST listing endpoints.
- **Automated Verification**:
  - 174 automated tests passing (including full unit and integration test coverage for `TenantService`, `TenantController`, `PatientService`, and `PatientController`).

---

## Milestone: System Admin Role Authority Templates & Catalogue API (Flyway V9 & Management UI)
**Date**: October 13, 2026  
**Focus**: Configurable role default authorities, metadata catalogue discovery, cascade propagation, and administrative management console.

### Key Deliverables & Changes
1. **Flyway Migration `V9__role_authorities.sql`**:
   - Created table `identity_role_authorities` (`id`, `role`, `authority_key`, audit columns, unique constraint `(role, authority_key)`).
   - Seeded baseline default authorities (all 12) for `ADMIN`, `SPONSOR`, `SITE`.
   - Backfilled existing non-deleted `ADMIN` users into `identity_user_authorities`.
   - Updated `identity_authorities.allowed_roles` to `'ADMIN,SPONSOR,SITE'`.
2. **Domain & Service Layer**:
   - Created `RoleAuthorityEntity` extending `BaseAuditEntity` and `RoleAuthorityRepository`.
   - Extended `Authority` enum with `displayName`, `category` (*Tenant Governance*, *User Management*, *Clinical & Patients*), and getters.
   - Created `RoleAuthorityService` providing catalogue lookup, role default resolution, dynamic cascade (`applyToExistingUsers: boolean`), and structured audit logging (`ROLE_AUTHORITIES_CHANGED`).
   - Updated `AuthorityService` to resolve `ADMIN` authorities from stored user authorities or role defaults, and allow `SYSTEM_ADMIN` to manage `ADMIN` authorities.
   - Updated `AuthService` (`registerTenant` & `inviteAdmin`) and `TenantService` (`createOwner`) to use dynamic role defaults from `RoleAuthorityService`.
3. **REST Endpoints**:
   - `GET /api/v1/authorities`: Public catalogue for authenticated clients.
   - `GET /api/v1/system-admin/authorities`: Metadata catalogue for `SYSTEM_ADMIN`.
   - `GET /api/v1/system-admin/roles/authorities`: All role mappings for `SYSTEM_ADMIN`.
   - `GET /api/v1/system-admin/roles/{role}/authorities`: Single role mapping.
   - `PUT /api/v1/system-admin/roles/{role}/authorities`: Update role template with optional cascade flag (`applyToExistingUsers: boolean`). Rejects `SYSTEM_ADMIN` (immutable root) and `PATIENT` (restricted).
4. **Management UI in `hekma-test-app` (`/admin`)**:
   - Added `AuthorityDefinition`, `RoleAuthoritiesResponse`, and `UpdateRoleAuthoritiesRequest` to `lib/types.ts`.
   - Extended `authApi` and `systemAdminApi` in `lib/api.ts`.
   - Added "Role Permissions & Authorities" 4th tab to `app/admin/page.tsx` for `SYSTEM_ADMIN`, featuring role selector pills (`ADMIN`, `SPONSOR`, `SITE`), category grouping cards with "Select All" / "Clear" buttons, authority checkboxes with monospace keys and descriptions, cascade toggle switch, and optional audit reason input.
5. **Verification**:
   - All 275 tests in `hekma-identity-service` passing with 0 failures, 0 errors.
   - Production build (`npm run build`) in `hekma-test-app` passing cleanly with 0 TypeScript errors.

---

## Milestone: Custom Roles & Role Governance Authorities (Flyway V10 & RBAC Phase 8)
**Date**: October 13, 2026  
**Focus**: Dynamic custom functional roles, authority bundling, effective authority aggregation, and operational role assignment.

### Key Deliverables & Changes
1. **Authorities Catalogue Expansion**:
   - Added 5 new fine-grained authorities under `"Role Governance"` category: `role:read`, `role:create`, `role:update`, `role:delete`, `role:assign` (total platform authorities expanded to 17).
   - Included new authorities in `Authority.OWNER_BUNDLE`.
2. **Flyway Migration `V10__custom_roles.sql`**:
   - Seeded the 5 new authorities into `identity_authorities`.
   - Created `identity_custom_roles` (`id`, `tenant_id`, `tenant_path`, `name`, `code`, `description`, `is_system`, `is_active`, `is_deleted`, audit fields).
   - Created `identity_custom_role_authorities` (`id`, `custom_role_id`, `authority_key`, unique constraint).
   - Created `identity_user_custom_roles` (`id`, `user_id`, `custom_role_id`, `assigned_by`, unique constraint).
   - Partial unique index on role code: `(COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), code)` where `is_deleted = false`.
   - Seeded new authorities into `identity_role_authorities` defaults for `ADMIN`, `SPONSOR`, `SITE` and backfilled active staff users.
3. **Domain, Repositories & Security**:
   - Entities: `CustomRoleEntity`, `CustomRoleAuthorityEntity`, `UserCustomRoleEntity`.
   - Repositories: `CustomRoleRepository`, `CustomRoleAuthorityRepository`, `UserCustomRoleRepository`.
   - Updated `HekmaPrincipal` with `customRoles` set and helper `hasCustomRole(code)`.
   - Updated `FirebaseAuthenticationFilter` to query direct user authorities $\cup$ assigned custom role authorities on every request, establishing dynamic effective permission evaluation.
   - Updated `MeResponse` and `UserManagementService.me()` to expose assigned `customRoles`.
4. **Service & REST Controllers**:
   - Implemented `CustomRoleService` enforcing:
     - **Grant $\le$ Own**: Users can only bundle or assign authorities they personally hold.
     - **Tenant Subtree Isolation**: Global roles managed by platform admins; tenant roles scoped by `tenantPath`.
     - **No Self-Elevation**: Users cannot assign or modify custom roles for themselves.
     - Soft deletion with active user assignment guard check.
   - Created `CustomRoleController` (`POST /api/v1/custom-roles`, `GET /api/v1/custom-roles`, `GET /api/v1/custom-roles/{roleId}`, `PUT /api/v1/custom-roles/{roleId}`, `DELETE /api/v1/custom-roles/{roleId}`).
   - Added user custom role endpoints in `UserController` (`GET /api/v1/users/{userId}/custom-roles`, `PUT /api/v1/users/{userId}/custom-roles`).
5. **Audit Logging**:
   - Added actions to `AuditService`: `CUSTOM_ROLE_CREATED`, `CUSTOM_ROLE_UPDATED`, `CUSTOM_ROLE_DELETED`, `CUSTOM_ROLE_ASSIGNED` under target type `CUSTOM_ROLE`.
6. **Verification**:
   - 294 automated tests passed with 0 failures, 0 errors, including service, controller, and security guard suites.

---

## Upcoming & Pending Work

1. **Stateless JWT Interceptor Filter**:
   - Introduce a Spring Security filter (`FirebaseAuthenticationFilter`) to intercept and validate Bearer ID tokens on protected endpoints when moving beyond gateway-managed security.
2. **Production SMS Gateway Integration**:
   - Integrate direct Twilio / AWS SNS / Infobip SMS dispatch within `hekma-notification-service` or enable production webhook callbacks for delivery status tracking.
3. **Downstream Service Alignment**:
   - Align `hekma-notification-service` and `hekma-study-service` to consume `tenant_id` claims and patient mapping.
