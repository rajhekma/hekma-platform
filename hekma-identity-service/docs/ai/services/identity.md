# Hekma Identity Service (`hekma-identity-service`)

## Purpose
The **Hekma Identity Service** is the centralized identity, authentication, role-based authorization, tenant governance, clinical profile and regulatory consent microservice for the Hekma Platform (a decentralized clinical trial ecosystem).

---

## Responsibilities
- User registration and credential management synchronized across Google Firebase Auth and PostgreSQL (dual-write saga).
- Authentication of every protected request via Firebase ID token verification; authorization from PostgreSQL data.
- Multi-mode OTP verification over SMS (`PHONE`) and `EMAIL` with attempt limits (5), resend limits (3), hourly limits (5/hour) and 30-minute lockouts.
- Token refresh via Google Secure Token Service (STS); session revocation on deactivation, soft deletion and password reset.
- Multi-tenancy: hierarchical tenant organizations (`SPONSOR`, `SITE`, default `GENERAL` tenant "Hekma"); sub-tenants of any type at any depth; SPONSOR/SITE users see their tenant's subtree; a non-active tenant blocks its subtree.
- Patient recruitment: invitation by SPONSOR/SITE users, invitation acceptance with HIPAA/GDPR consent capture, investigator assignment.
- Role hierarchy enforcement (`SYSTEM_ADMIN`, `ADMIN`, `SPONSOR`, `SITE`, `PATIENT`), patient 2FA, soft deletion.
- Dual API: REST for transactional operations, GraphQL for administrative reporting.

---

## Technology
- **Language**: Java 25 (GraalVM JDK 25 / OpenJDK 25; compiler release 21).
- **Framework**: Spring Boot `4.1.1` (Spring MVC, Spring Security 7.x with method security, Spring Data JPA).
- **Persistence**: PostgreSQL 18 with Flyway `12.4.0` (history table `identity_flyway_schema_history`).
- **Identity Provider**: Google Firebase Admin SDK `9.4.3` and Google STS / Identity Toolkit REST.
- **GraphQL**: Spring for GraphQL `2.0.5` / GraphQL Java `25.0`.
- **API Documentation**: SpringDoc OpenAPI `3.1.0` (exposed only when `APP_EXPOSE_API_DOCS=true`).
- **Testing**: H2 in-memory (`MODE=PostgreSQL`), Spring Boot Test, Spring Security Test, mock Firebase.

---

## Important Components
- **`security.FirebaseAuthenticationFilter`**: Verifies `Authorization: Bearer <Firebase ID token>` (with revocation check), loads the user + tenant from PostgreSQL, rejects inactive users/tenants, and sets `HekmaPrincipal`.
- **`security.HekmaPrincipal`**: Authenticated caller (`userId`, `firebaseUid`, `email`, `role`, `tenantId`) — always sourced from the database.
- **`multitenancy.TenantFilter`**: Sets `TenantContext` from the principal; foreign `X-Tenant-ID` values from tenant users return 404; platform admins may target an existing tenant.
- **`config.SecurityConfig`**: Deny-by-default filter chain, exact public endpoint list, CORS from configuration, `@EnableMethodSecurity`.
- **`service.AuthService`**: Patient registration, login (password always validated by Firebase), token refresh, admin invitation, forgot/reset password (OTP-verified), admin bootstrap.
- **`service.OtpService`**: OTP generation, BCrypt hash verification, lockouts, audit logs, password-reset OTP check, custom-token → ID-token exchange after verification.
- **`service.UserManagementService`**: Role hierarchy, self-protection, status updates, soft deletion, 2FA, scoped user reads.
- **`service.TenantService` / `service.PatientService`**: Tenant CRUD and status; patient invite/accept/list/get/assign with tenant scoping.
- **`service.UserQueryService`**: Read-only GraphQL queries and batch resolvers.
- **`firebase.FirebaseAuthService` / `firebase.MockFirebaseService`**: Live Admin SDK integration / in-memory stand-in (`firebase.mock-mode=true` only).
- **`notification.NotificationServiceClient`**: Outbound REST client for `hekma-notification-service`.
- **`service.RoleAuthorityService`**: Manages default role authority templates (`identity_role_authorities`), catalogue metadata, and cascade propagation (`applyToExistingUsers`).
- **`service.CustomRoleService`**: Custom functional roles governance (RBAC Phase 8), bundling authorities within tenant subtrees, enforcing Grant $\le$ Own, No Self-Elevation, and user assignments.
- **`config.SystemAdminInitializer` / `config.AdminInitializer`**: Bootstrap the root `SYSTEM_ADMIN` and default platform `ADMIN`.

---

## APIs / Interfaces

### Public endpoints (no token; all `POST`)
`/api/v1/auth/register` (PATIENT only), `/register-tenant` (new top-level SPONSOR/SITE tenant + owner), `/login`, `/refresh-token`, `/forgot-password`, `/reset-password`, `/otp/send`, `/otp/verify`, `/otp/resend`, `/api/v1/patients/accept-invite`.

### Protected REST endpoints (`Authorization: Bearer <idToken>`)
| Endpoint | Allowed |
|---|---|
| `POST /api/v1/auth/change-password` | any authenticated user (own password; current password required) |
| `GET /api/v1/me`, `GET /api/v1/me/authorities` | any authenticated user |
| `GET /api/v1/authorities` | any authenticated user (catalogue with metadata & categories) |
| `GET /api/v1/users` | `user:read` (scoped) |
| `POST /api/v1/users/invite` / `POST /api/v1/users/accept-invite` (public) | `user:invite` (authorities ≤ inviter's) |
| `GET /api/v1/users/{id}/authorities` / `PUT …/authorities` | self, `user:read` / `authority:assign` (grant ≤ own, no self-change) |
| `GET /api/v1/users/{id}/custom-roles` / `PUT …/custom-roles` | `role:read` / `role:assign` (grant ≤ own, no self-change) |
| `GET /api/v1/custom-roles`, `POST /api/v1/custom-roles` | `role:read` / `role:create` |
| `GET /api/v1/custom-roles/{id}`, `PUT …/{id}`, `DELETE …/{id}` | `role:read` / `role:update` / `role:delete` |
| `GET /api/v1/system-admin/authorities` | `SYSTEM_ADMIN` (catalogue) |
| `GET /api/v1/system-admin/roles/authorities`, `GET/PUT …/roles/{role}/authorities` | `SYSTEM_ADMIN` (default role templates; cascade flag `applyToExistingUsers`) |
| `POST /api/v1/system-admin/admins` (alias `/invite-admin`) | `SYSTEM_ADMIN` |
| `PATCH /api/v1/users/{id}/status`, `DELETE /api/v1/users/{id}` | `user:manage` + hierarchy (admins) or subtree (staff), never self |
| `PATCH /api/v1/users/{id}/2fa` | self, platform admins |
| `GET /api/v1/users/{id}` | self, platform admins, same-tenant SPONSOR/SITE (else 404) |
| `POST /api/v1/tenants/{id}/sub-tenants` | `subtenant:create` within subtree |
| `GET /api/v1/tenants`, `GET /api/v1/tenants/{id}/children` | `tenant:read` within subtree |
| `PUT /api/v1/tenants/{id}` | `tenant:update` within subtree |
| `PATCH /api/v1/tenants/{id}/status` | `subtenant:manage`; staff only for strict descendants |
| `GET /api/v1/tenants/{id}` | platform admins; SPONSOR/SITE within subtree; patients own tenant (else 404) |
| `GET /api/v1/tenants/slug/{slug}` | platform admins |
| `POST /api/v1/patients/invite` | SPONSOR/SITE with `patient:create` (72 h single-use code) |
| `GET /api/v1/patients`, `GET /api/v1/patients/{id}` | patient (self) or `patient:read` (subtree) |
| `PATCH /api/v1/patients/{id}` | patient (self) or `patient:update` (subtree) |
| `PATCH /api/v1/patients/{id}/assign` | `patient:assign` (subtree) |

### GraphQL API (`/graphql`)
- Restricted to `SYSTEM_ADMIN`/`ADMIN`. Queries: `users(role)`, `userById(id)`, `userByEmail(email)`, `userCount(role)`. Mutations: `updateUserActiveStatus(userId, isActive)`, `softDeleteUser(userId)`, `updateUserTwoFactor(userId, twoFactorEnabled)`.
- GraphiQL and introspection are disabled unless `GRAPHIQL_ENABLED` / `GRAPHQL_INTROSPECTION_ENABLED` are set.

---

## Database
- Flyway migrations: `V1__init_identity_schema.sql` through `V10__custom_roles.sql`.
- Tables: `identity_users` (incl. `tenant_id`, `auth_email`), `identity_patient_details` (incl. `assigned_user_id`), `identity_tenants` (incl. `parent_tenant_id`, `path`, `depth`), `identity_otp_requests`, `identity_otp_lockouts`, `identity_otp_audit_logs`, `identity_authorities`, `identity_role_authorities`, `identity_user_authorities`, `identity_user_invitations`, `identity_custom_roles`, `identity_custom_role_authorities`, `identity_user_custom_roles`, `identity_authz_audit_log`.
- Details: [docs/DATABASE.md](../../DATABASE.md).

---

## Communication With Other Services
- **`hekma-notification-service`**: Synchronous HTTP POST `/api/v1/notifications/send`, header `X-Hekma-Service-Key` (required config `NOTIFICATION_SERVICE_KEY`, no default). Channels: `EMAIL` (OTP, welcome, invitation), `IN_APP` (welcome). PHONE OTPs have no SMS integration yet.
- **Google Firebase**: Admin SDK (user management, token verification, revocation, custom tokens) and Identity Toolkit / STS REST (`signInWithPassword`, `signInWithCustomToken`, token refresh) — requires `FIREBASE_WEB_API_KEY`.

---

## Authentication / Authorization
- **Passwords**: created, changed, reset and validated only through this API; stored only in Firebase. Policy `@StrongPassword` (8–128, upper/lower/digit/special). `change-password` revokes other sessions and returns new tokens.
- **Login**: The Java API validates every password via Firebase (`signInWithPassword` with `auth_email`) and returns Firebase ID + refresh tokens. Phone-only accounts use a synthetic `auth_email`.
- **Requests**: Firebase ID token verified on each request; role/tenant/status from PostgreSQL; custom claims (`role`, `tenantId`) are hints for other services only.
- **Authorities (Phase 3 & Phase 4 & Phase 8)**: 17 granular authorities grouped into *Tenant Governance*, *User Management*, *Clinical & Patients*, and *Role Governance*. Role default templates (`ADMIN`, `SPONSOR`, `SITE`) are dynamically configured in `identity_role_authorities` by `SYSTEM_ADMIN` via `RoleAuthorityService` and can cascade to active users (`applyToExistingUsers: boolean`). Dynamic custom functional roles (`identity_custom_roles`) allow bundling authorities per tenant subtree. Direct user authorities and custom role authorities are merged dynamically on every request by `FirebaseAuthenticationFilter`. Admins hold all or configured authorities, patients none; loaded from DB each request; grant ≤ own; audited in `identity_authz_audit_log`.
- **Roles**: exactly five — `SYSTEM_ADMIN` (single root), `ADMIN` (managed by `SYSTEM_ADMIN`), `SPONSOR`/`SITE` (tenant roles), `PATIENT`.
- **Plan & status**: [docs/RBAC_PLAN.md](../../RBAC_PLAN.md) (all phases implemented).

---

## Important Rules
1. **Dual-Write Rollback**: If PostgreSQL or OTP dispatch fails after creating a Firebase user, invoke `firebaseService.deleteUser(uid)`.
2. **Soft Deletion**: Never run physical `DELETE` on users; `@SQLRestriction("is_deleted = false")`.
3. **No client-supplied identity**: Never read operator/tenant identity from headers or bodies; use `@AuthenticationPrincipal HekmaPrincipal`.
4. **Every protected handler declares `@PreAuthorize`**; new public endpoints must be added explicitly to `SecurityConfig.PUBLIC_POST_ENDPOINTS`.
5. **No plaintext secrets**: OTPs are BCrypt-hashed; OTP console echo only with `OTP_CONSOLE_ECHO=true` in local dev.

---

## Current Status
- RBAC Phases 1–4 and Phase 8 implemented (authentication, password management, tenant hierarchy, per-user authorities, invitations, custom functional roles, audit); 294 automated tests passing.
- Next: PostgreSQL migration run, commit, frontend alignment.

---

## Known Issues
- Requires `FIREBASE_MOCK_MODE=true`, or a valid service account file **and** `FIREBASE_WEB_API_KEY`, to start; `NOTIFICATION_SERVICE_KEY` is always required.
- In mock mode, bootstrapped admins get random passwords; use forgot/reset password with `OTP_CONSOLE_ECHO=true` to set one.
- `hekma-test-app` must send `Authorization: Bearer <idToken>` and stop sending `X-Operator-Id`.
