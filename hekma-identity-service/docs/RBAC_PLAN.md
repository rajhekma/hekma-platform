# RBAC Implementation Plan — `hekma-identity-service`

> **Status:** Approved (rev 3, 2026-10-07 — OD-1…OD-5 resolved). **Phases 1–4 implemented** (2026-10-07, uncommitted in the working tree). Open follow-ups are listed in §10.
> **Inputs:** Product direction given on 2026-10-07 (this document's §1) and *Hekma RBAC SRS v1.0* (used for guiding principles only — see §9).
> **Supersedes:** rev 1 (SRS persona / Keycloak-oriented draft).

---

## 1. Target Model (agreed)

### 1.1 Authentication
- **Passwords are validated only by the Java API.** `POST /api/v1/auth/login` validates the password through Firebase (`signInWithPassword`) and returns Firebase ID + refresh tokens. Clients never talk to Firebase directly.
- **Tokens are Firebase-issued and Firebase-stored.** Every protected request carries `Authorization: Bearer <Firebase ID token>`. The API verifies the token with the Firebase Admin SDK (`verifyIdToken(token, checkRevoked = true)`: signature, issuer, audience, expiry, revocation).
- **Authorization data comes from PostgreSQL, never from the token.** The token proves *who* the caller is (`uid`). Role, tenant, status and authorities are loaded from the database on each request. Custom claims (`role`, `tenantId`) are kept only as hints for other services.

### 1.2 Roles (fixed — exactly five)

| Role | Level | Tenant | Count | Created by |
|---|---|---|---|---|
| `SYSTEM_ADMIN` | Platform | none | **exactly one** | bootstrapped at startup |
| `ADMIN` | Platform | none | many | `SYSTEM_ADMIN` only |
| `SPONSOR` | Tenant | required | many | tenant self-registration (owner) or invitation by a tenant user with authority |
| `SITE` | Tenant | required | many | tenant self-registration (owner) or invitation by a tenant user with authority |
| `PATIENT` | Self | required | many | self-registration (→ default tenant) or created by a SPONSOR/SITE user |

- `SYSTEM_ADMIN` manages `ADMIN` users (create, deactivate, delete). `ADMIN` cannot manage `ADMIN` or `SYSTEM_ADMIN`.
- Public self-registration has two forms:
  - **Patient registration:** always joins the default tenant Hekma, unless the patient redeems an invitation code.
  - **Tenant registration:** creates a **new top-level tenant** together with its owner user. The owner's role equals the tenant type.
- Nobody can self-register *into an existing tenant*. Additional SPONSOR/SITE users join only by invitation.
- A user's role must match its tenant's type (OD-3).

### 1.3 Tenants
- Multi-tenant; tenant types `SPONSOR` and `SITE` (plus the `GENERAL` default tenant **Hekma**).
- **Top-level tenants are created only by self-registration** (OD-1). `SYSTEM_ADMIN`/`ADMIN` do not create tenants; they view, update and suspend/activate them.
- **Hierarchical:** a tenant can create **sub-tenants of any type, at any depth**. This requires `subtenant:create`.
- **Suspension cascades:** a suspended tenant blocks access for all of its descendants, checked at request time (OD-4).
- **Visibility:** a SPONSOR/SITE user sees data of **its own tenant and all descendant sub-tenants only**. `SYSTEM_ADMIN` and `ADMIN` see **all tenants**.

### 1.4 Authorities (fine-grained permissions)
- A fixed, migration-managed catalogue of authorities (§3.2).
- `SPONSOR`/`SITE` users receive authorities individually. A role provides only the *allowed set*; actual authorities are granted per user.
- **Grant ≤ own:** a user can grant only authorities it holds, only to users in its own tenant or a descendant tenant, and never to itself.
- The **first user of a tenant** (the tenant owner, created together with the tenant) receives **all tenant authorities** and can delegate them, including `subtenant:create` and `authority:assign`.
- `SYSTEM_ADMIN` / `ADMIN` have implicit platform authorities (not stored per user).
- `PATIENT` has no authorities; access is limited to its own profile.

### 1.5 Patients
- **Direct registration** → patient belongs to the default tenant **Hekma** (unassigned pool).
- **Created by a SPONSOR/SITE user** → patient belongs to the creator's tenant (or a descendant tenant chosen by the creator) and `assigned_user_id` = creator.
- Visible to: the patient itself; tenant users with `patient:read` in the patient's tenant or any **ancestor** tenant; platform admins.

---

## 2. Current State vs. Target (verified against code)

| # | Finding | Location | Severity |
|---|---|---|---|
| G-01 | All business routes are `permitAll` (`/users/**`, `/tenants/**`, `/patients/**`, `/system-admin/**`, `/graphql`, `/graphiql`); no ID token is verified anywhere. | `config/SecurityConfig.java` | **Critical** |
| G-02 | Caller identity comes from the `X-Operator-Id` header / `operatorId` body field / GraphQL arg — fully spoofable. | `UserController`, `TenantController`, `PatientController`, `UserGraphQlController`, `UpdateUserStatusRequest` | **Critical** |
| G-03 | `POST /system-admin/invite-admin` has no caller check — anyone can create an `ADMIN`. | `SystemAdminController`, `AuthService.inviteAdmin` | **Critical** |
| G-04 | Tenant context is taken from the client `X-Tenant-ID` header; an invalid value continues unscoped. | `multitenancy/TenantFilter.java` | High |
| G-05 | Public `register` lets SPONSOR/SITE/PATIENT join **any existing tenant** by passing `tenantId`/`tenantSlug`. There is no tenant self-registration flow. | `AuthService.register` (tenant resolution), `RegisterRequest.tenantId/tenantSlug` | High |
| G-06 | No tenant hierarchy (`identity_tenants` has no parent). Tenant visibility is an exact `tenantId` equality check. | `TenantEntity`, `PatientService.listPatients/getPatientById/assignPatient` | Feature gap |
| G-07 | No authority model; all checks are hardcoded `Role` comparisons. | `PatientService`, `TenantService`, `UserManagementService` | Feature gap |
| G-08 | "Exactly one SYSTEM_ADMIN" is enforced only by the initializer, not by the database. | `SystemAdminInitializer`, V1 schema | Medium |
| G-09 | Patient invitation codes never expire. | `PatientService` | Medium |
| G-10 | Notification service key has an in-code default value; OTP/reset codes are printed with `System.out` (24 occurrences). | `application.yml`, `AuthController`, `AuthService`, `OtpService` | Medium |
| G-11 | CORS allows any origin pattern with credentials; GraphiQL enabled. | `SecurityConfig`, `application.yml` | Medium |
| G-12 | Deactivation does not revoke existing Firebase sessions. | `UserManagementService` | Medium |

---

## 3. Design

### 3.1 Request authentication pipeline
```
Request
  └─ FirebaseAuthenticationFilter
       ├─ no Bearer token → anonymous (only public endpoints succeed)
       ├─ verifyIdToken(token, checkRevoked=true) fails → 401 UNAUTHENTICATED
       ├─ load UserEntity by firebase_uid (soft-deleted excluded)
       │    missing / status != ACTIVE → 401 / 403 ACCOUNT_INACTIVE
       ├─ tenant SUSPENDED/INACTIVE (tenant users) → 403 TENANT_SUSPENDED
       └─ SecurityContext ← HekmaPrincipal{userId, role, tenantId, tenantPath, authorities}
  └─ TenantFilter (rewritten): TenantContext ← principal.tenantId (never the header)
  └─ Controller → @PreAuthorize("@authz.can(...)") → Service (scoped queries)
```
- `FirebaseService.verifyIdToken(...)` is added to the interface. `MockFirebaseService` issues and accepts the deterministic token `mock-id-token:{firebaseUid}` so tests can authenticate as any user.
- On deactivation, soft delete or password reset: `FirebaseAuth.revokeRefreshTokens(uid)`. Together with `checkRevoked=true`, existing sessions are cut off.
- `X-Tenant-ID` is **ignored for tenant users**. Platform admins may use it only as an optional *filter* on list endpoints (validated to exist).

### 3.2 Authority catalogue (seeded by migration, read-only at runtime)

| Authority | Meaning | Allowed for |
|---|---|---|
| `tenant:read` | View own tenant and descendant tenants | SPONSOR, SITE |
| `tenant:update` | Edit profile/settings of own or descendant tenant | SPONSOR, SITE |
| `subtenant:create` | Create a sub-tenant under own or a descendant tenant | SPONSOR, SITE |
| `subtenant:manage` | Suspend/activate a descendant tenant (never own or ancestor) | SPONSOR, SITE |
| `user:read` | View users in own/descendant tenants | SPONSOR, SITE |
| `user:invite` | Invite SPONSOR/SITE users into own/descendant tenants | SPONSOR, SITE |
| `user:manage` | Activate/deactivate/soft-delete users in own/descendant tenants | SPONSOR, SITE |
| `authority:assign` | Grant/revoke authorities to users in own/descendant tenants (≤ own) | SPONSOR, SITE |
| `patient:create` | Create/invite patient profiles | SPONSOR, SITE |
| `patient:read` | View patients in own/descendant tenants | SPONSOR, SITE |
| `patient:update` | Update patient profile data | SPONSOR, SITE |
| `patient:assign` | Reassign patient to another user/tenant within own subtree | SPONSOR, SITE |

- **Tenant owner bundle:** all 12 authorities.
- **Default bundle for an invited user** (when the inviter doesn't specify one): `tenant:read`, `patient:read`, `patient:create`. Always capped by the inviter's own authorities.
- Platform roles are implicit (code-defined, not stored):
  - `SYSTEM_ADMIN` = everything + `admin:manage`.
  - `ADMIN` = everything except `admin:manage`.
- The catalogue lives in a table, so adding an authority later is a migration, not a code change to the role model.

### 3.3 Authorization rules (single `AuthorizationService`, bean name `authz`)

`can(principal, authority, target)` evaluates in this order and denies at the first failure:
1. Principal is authenticated and `ACTIVE`; its tenant is `ACTIVE` (tenant users).
2. **Platform role:**
   - `SYSTEM_ADMIN` → allow.
   - `ADMIN` → allow unless the target is an `ADMIN`/`SYSTEM_ADMIN` user or the authority is `admin:manage`.
3. **PATIENT:** allow only self-operations on its own record (profile read, 2FA toggle). Everything else → deny.
4. **SPONSOR/SITE:** the principal holds `authority` **and** the target's tenant is the principal's tenant or a descendant (`target.path LIKE principal.path || '%'`).
5. **Extra rules:**
   - No self-targeting for `user:manage` / `authority:assign`.
   - No granting an authority you don't hold.
   - `subtenant:manage` can't target your own or an ancestor tenant.
   - Default tenant **Hekma** can't be suspended, and tenant users can't create sub-tenants under it.

- Out-of-subtree targets return **404** (don't confirm existence). Missing authority returns **403 `AUTHORITY_MISSING`**.
- List endpoints apply the same rule as a query filter (`tenant.path LIKE :prefix%`), never post-filtering in memory.

### 3.4 Tenant hierarchy storage
- `identity_tenants.parent_tenant_id` (nullable FK), `path` (materialized path, e.g. `/a1…/b2…/`), `depth`.
- Descendant lookup: `WHERE path LIKE :principalPath || '%'`, indexed with `identity_idx_tenants_path`. Works identically on PostgreSQL and H2.
- Re-parenting tenants is **not supported** in this plan (keeps paths immutable).

### 3.5 Endpoint authorization matrix

| Endpoint | SYSTEM_ADMIN | ADMIN | SPONSOR / SITE (own subtree) | PATIENT |
|---|---|---|---|---|
| `POST /system-admin/admins` (renamed `invite-admin`), `PATCH/DELETE` admin | ✅ | ❌ | ❌ | ❌ |
| `POST /auth/register-tenant` (top-level tenant + owner user) | public | public | public | public |
| `POST /tenants` (admin creation) | **removed** (OD-1) | **removed** | ❌ | ❌ |
| `POST /tenants/{id}/sub-tenants` (+ optional owner) | ✅ | ✅ | `subtenant:create` | ❌ |
| `GET /tenants`, `GET /tenants/{id}`, `GET /tenants/{id}/children` | all | all | `tenant:read` | ❌ |
| `PUT /tenants/{id}` | ✅ | ✅ | `tenant:update` | ❌ |
| `PATCH /tenants/{id}/status` | ✅ | ✅ | `subtenant:manage` (descendants only) | ❌ |
| `POST /users/invite` (SPONSOR/SITE into tenant) | ✅ | ✅ | `user:invite` | ❌ |
| `GET /users`, `GET /users/{id}` | all | all | `user:read` | self |
| `PATCH /users/{id}/status`, `DELETE /users/{id}` | all except self | non-admin targets | `user:manage` (not self) | ❌ |
| `GET /users/{id}/authorities` | ✅ | ✅ | `user:read` | ❌ |
| `PUT /users/{id}/authorities` | ✅ | ✅ | `authority:assign` (≤ own, not self) | ❌ |
| `PATCH /users/{id}/2fa` | ✅ | ✅ | ❌ | self |
| `POST /patients/invite` | ✅ | ✅ | `patient:create` | ❌ |
| `GET /patients`, `GET /patients/{id}` | all | all | `patient:read` | self |
| `PATCH /patients/{id}` | ✅ | ✅ | `patient:update` | self (limited fields) |
| `PATCH /patients/{id}/assign` | ✅ | ✅ | `patient:assign` (target user/tenant in subtree) | ❌ |
| `GET /api/v1/me`, `GET /api/v1/me/authorities` | ✅ | ✅ | ✅ | ✅ |
| GraphQL queries & mutations | ✅ | ✅ | same rules, scoped | ❌ |
| Public: `auth/register` (PATIENT → Hekma, or invitation code), `auth/register-tenant`, `login`, `refresh-token`, `forgot-password`, `reset-password`, `otp/*`, `patients/accept-invite`, `users/accept-invite` | — | — | — | — |

### 3.6 Patient association rules
- `POST /patients/invite` accepts an optional `tenantId`:
  - If omitted, the patient joins the creator's tenant.
  - If given, it must be within the creator's subtree.
  - `assigned_user_id` = creator, unless `assignedUserId` is given (must also be in the subtree).
- Self-registered patients stay in **Hekma** (unassigned pool). Only platform admins can see or move them (existing `assignPatient` behaviour, kept).
- Ancestor tenants see descendant tenants' patients through the subtree rule (§3.3).

---

## 4. Database Changes (Flyway)

| Migration | Content |
|---|---|
| `V4__tenant_hierarchy.sql` | `identity_tenants` + `parent_tenant_id UUID NULL REFERENCES identity_tenants(id)`, `path VARCHAR(2048) NOT NULL`, `depth INT NOT NULL DEFAULT 0`. Backfill `path = '/' \|\| id \|\| '/'` for existing rows. Index `identity_idx_tenants_parent`, `identity_idx_tenants_path`. |
| `V5__authorities.sql` | `identity_authorities(key PK, description, allowed_roles VARCHAR, created_at…)`. Seed the 12 authorities. `identity_user_authorities(id, user_id FK, authority_key FK, granted_by FK, granted_at, + audit cols)` with unique `(user_id, authority_key)`. Index `identity_idx_user_authorities_user`. |
| `V6__authority_backfill.sql` | Grant the **tenant-owner bundle** to every existing `SPONSOR`/`SITE` user. This keeps today's behaviour (all tenant staff can manage patients) — see OD-2. |
| `V7__single_system_admin_and_invites.sql` | Partial unique index `identity_uq_users_single_system_admin ON identity_users(role) WHERE role = 'SYSTEM_ADMIN' AND is_deleted = FALSE`. Plus `identity_patient_details.invitation_expires_at`, `invitation_used_at`. New `identity_user_invitations(id, email, role, tenant_id, token_hash, authorities CSV, invited_by, expires_at, accepted_at)` for staff invitations (single-use, 72 h). |
| `V8__authz_audit.sql` | `identity_authz_audit_log(id, ts, actor_id, action, target_type, target_id, tenant_id, before_json, after_json, reason, request_id)`. Append-only; identifiers only, no PHI. Records authority grants/revokes, user status changes, tenant create/status, admin management. |

> The H2 test DB must support the partial index. If H2 rejects `WHERE`, enforce single-SYSTEM_ADMIN in the service layer and keep the partial index in a PostgreSQL-only migration (`db/migration/postgresql`). To be verified during implementation.

---

## 5. Implementation Phases

### Phase 1 — Authentication containment — ✅ IMPLEMENTED (2026-10-07)

**Delivered:** items 1–9 below, plus fixes for issues discovered during implementation:
- `POST /auth/reset-password` ignored `otpCode` (anyone could reset any password) → now verified against the latest pending `PASSWORD_RESET` OTP (`OtpService.verifyPasswordResetOtp`).
- Phone-only login issued a custom token with **no password check**, and `signInWithPassword` fell back to token issuance without the Web API key → password always validated by Firebase; phone-only accounts get a synthetic login email (`identity_users.auth_email`, migration **`V3__add_user_auth_email.sql`**, ADR-010).
- `FirebaseConfig` silently fell back to the mock Firebase service when credentials were missing → startup now fails outside `firebase.mock-mode`.
- `PATIENT` callers of `GET /patients` received **all** patients; null-caller paths returned everything → scoped.
- `otp/verify` returned only a custom token → now also returns an ID token + refresh token (server-side exchange).
- JPA auditor wrote `HekmaPrincipal.toString()` into `updated_by` → writes the user ID.
- Tests: 213 passing, incl. `SecurityAccessIntegrationTest` (full filter chain, 20 cases).

Original scope (fixes G-01…G-05, G-10, G-11, G-12):
1. Add `FirebaseService.verifyIdToken` (live + mock), `FirebaseAuthenticationFilter`, `HekmaPrincipal`, `@CurrentUser` argument resolver.
2. Rewrite `SecurityConfig`:
   - Exact public endpoint list; everything else authenticated.
   - JSON 401/403 handlers.
   - `@EnableMethodSecurity`.
   - CORS origins from config.
   - GraphiQL and introspection only in `dev`.
3. Remove `X-Operator-Id`, `operatorId` (DTO + GraphQL args); services take `HekmaPrincipal`.
4. Rewrite `TenantFilter` to use the principal's tenant; drop the header path for tenant users.
5. Restrict `POST /auth/register` to `PATIENT`:
   - Remove the `tenantId`/`tenantSlug` inputs.
   - The patient joins Hekma, or the tenant of a valid invitation code.
   - SPONSOR/SITE self-registration is temporarily disabled until `register-tenant` ships in Phase 2.
6. Lock `invite-admin` to `SYSTEM_ADMIN`; add admin deactivate/delete for `SYSTEM_ADMIN`.
7. Revoke Firebase refresh tokens on deactivate, soft delete and password reset.
8. Remove the default `NOTIFICATION_SERVICE_KEY`; gate OTP console output behind mock mode.
9. Interim role-only checks (same as today's behaviour, now with the real caller) until Phase 3.

### Phase 2 — Tenant hierarchy — ✅ IMPLEMENTED (2026-10-07)

**Delivered:** items 1–5 below (migration `V4__tenant_hierarchy.sql`, ADR-011), with these interim choices and deviations:
- Until Phase 3, **every** SPONSOR/SITE user may create sub-tenants, update tenants in their subtree, and change the status of strict descendants (this equals the Phase 3 backfill of the full owner bundle, OD-2).
- Sub-tenant owners are created with a temporary password (same pattern as admin invitation); invitation emails/links arrive with Phase 3 staff invitations.
- Patient invitations accept an optional `tenantId` (sub-tenant) and `assignedUserId`; an assignee's tenant must contain the patient's tenant.
- **Deferred:** purging tenants that never complete OTP verification (OD-6, 7 days) — needs a scheduled job and a decision on freeing the slug/email; tracked as a follow-up.
- Pre-existing bugs fixed on the way: patient invitation failed on PostgreSQL (`firebase_uid` NULL), framework 404/405/400 errors returned 500, login accessed the lazy tenant outside a transaction.
- Tests: 251 passing, incl. `TenantHierarchyIntegrationTest`. Migrations V3/V4 are not yet exercised against PostgreSQL in CI (tests use H2 with Hibernate DDL).

Original scope:
1. `V4` migration; `TenantEntity.parent`, `path`, `depth`; `TenantRepository.findByPathStartingWith`.
2. **Tenant self-registration** `POST /api/v1/auth/register-tenant` (public):
   - Body: tenant name, slug, type (`SPONSOR`|`SITE`), contact details; owner email, password, display name, phone, verification mode.
   - Reuses the existing dual-write saga: create the Firebase user, then in **one transaction** the tenant (root, `path=/{id}/`, status `PENDING_VERIFICATION`) and the owner user (role = tenant type, tenant owner bundle), then send the OTP.
   - Compensating rollback deletes the Firebase user and the DB rows if any step fails.
   - OTP verification activates both the owner and the tenant.
   - Remove `POST /tenants` (admin creation); `TenantService.createTenant` becomes internal.
   - Requires a new `TenantStatus.PENDING_VERIFICATION` value. Unverified tenants are purged after N days (see OD-6).
3. `POST /tenants/{id}/sub-tenants` (any type, any depth) with an optional owner invitation.
4. `GET /tenants/{id}/children`, tree listing; scope all tenant/user/patient queries by subtree.
5. Status rules: suspending a parent **suspends access for all descendants** (checked via ancestor statuses in the filter). The Hekma default tenant can't be suspended and can't receive tenant-created sub-tenants.

### Phase 3 — Authorities & enforcement — ✅ IMPLEMENTED (2026-10-07)

**Delivered:** items 1–9 below (migrations V5–V8, ADR-012/013), with these notes:
- Authorities are an `Authority` enum mirrored by the `identity_authorities` table; no separate `@authz` bean — `@PreAuthorize("hasAuthority('…')")` on handlers plus subtree checks in services (`HekmaPrincipal.has`, `canSeeTenant`).
- Platform admins receive every authority key as a granted authority; `SYSTEM_ADMIN`-only actions keep role checks.
- New: `GET /api/v1/users` (scoped list) and `PATCH /api/v1/patients/{id}`; SPONSOR/SITE with `user:manage` manage users in their subtree.
- Staff invitation links point to `https://app.hekma.com/invitations/accept?token=…` (frontend route to be built).
- Legacy patient invitations without an expiry (created before V7) remain valid until used.
- Tests: 265 passing, incl. `AuthorityIntegrationTest` and the `AuthorizationGuardTest` build guard.

Original scope:
1. `V5`/`V6`/`V7`/`V8` migrations; `AuthorityEntity`, `UserAuthorityEntity`, repositories.
2. `AuthorizationService` (`@authz`) implementing §3.3. Per-request authority cache inside `HekmaPrincipal` (loaded once per request — no cross-request cache, so revocations apply on the next request).
3. Apply `@PreAuthorize` to every handler per §3.5. Remove hardcoded `Role` checks from `PatientService`, `TenantService` and `UserManagementService`.
4. Staff invitation flow: `POST /users/invite` (role, tenantId, authorities ≤ inviter's) → `POST /users/accept-invite` (public, single-use token, 72 h).
5. Authority management: `GET/PUT /users/{id}/authorities` (grant ≤ own, no self, audited).
6. `GET /api/v1/me` (profile, role, tenant, tenant path) and `GET /api/v1/me/authorities` so the frontend can render UI from server data.
7. Patient creation with optional `tenantId`/`assignedUserId` within subtree; patient invitation expiry (72 h) and single-use.
8. Audit log writes for all privileged actions.
9. Build guard test: every `@RestController`/GraphQL handler has `@PreAuthorize` or is on the public list.

### Phase 4 — Docs & handover — ✅ DONE (2026-10-07)
Update `docs/ai/*`, `docs/API_DOCUMENTATION.md`, `docs/DATABASE.md`, `docs/DEVELOPMENT_LOG.md`, and add ADRs (§8).

### Phase 8 — Custom Roles & Governance — ✅ IMPLEMENTED (2026-10-13)
**Delivered:** Flyway migration `V10__custom_roles.sql`:
- Catalogue expansion: added 5 new fine-grained authorities under `"Role Governance"`: `role:read`, `role:create`, `role:update`, `role:delete`, `role:assign` (17 total).
- Custom role tables: `identity_custom_roles`, `identity_custom_role_authorities`, `identity_user_custom_roles`.
- Dynamic bundling: Custom roles aggregate granular authorities within tenant subtrees or global templates.
- Enforced invariants: Grant $\le$ Own, Tenant Subtree Isolation, No Self-Elevation, soft deletion checks.
- Dynamic security context: `FirebaseAuthenticationFilter` aggregates direct user authorities with custom role authorities on each request.
- REST endpoints under `/api/v1/custom-roles` and `/api/v1/users/{userId}/custom-roles`.

---

## 6. Test Plan
- **Access matrix suite (MockMvc):** every endpoint × {anonymous, PATIENT self, PATIENT other, tenant user without authority, tenant user with authority in own tenant, same in parent tenant (→ allowed on child), same in child tenant (→ denied on parent), same in sibling tenant (→ 404), ADMIN, SYSTEM_ADMIN}.
- **Hierarchy tests:** 3-level tree (Root → A → A1, plus sibling B); verify visibility, sub-tenant creation at depth, and ancestor-suspension cascade.
- **Authority tests:** grant ≤ own; no self-grant; revoke takes effect on the next request; invited user's authorities are capped by the inviter's.
- **Spoofing tests:** `X-Operator-Id`, `operatorId` and a foreign `X-Tenant-ID` have no effect.
- **Platform tests:**
  - Only one SYSTEM_ADMIN can exist.
  - ADMIN can't modify ADMIN or SYSTEM_ADMIN.
  - SYSTEM_ADMIN can create, deactivate and delete ADMINs.
- **Patient tests:**
  - Self-registration lands in Hekma.
  - A patient created by a SITE user lands in that tenant and is assigned to them.
  - The parent tenant can see the patient; a sibling tenant cannot.
- **Session tests:** a deactivated user's existing token is rejected (mock revocation).
- **Regression:** existing tests migrated to bearer-token authentication.

---

## 7. Breaking Changes & Coordination
- **`hekma-test-app`:**
  - Must send `Authorization: Bearer <idToken>` and stop sending `X-Operator-Id`/`X-Tenant-ID`.
  - Should render menus from `GET /api/v1/me/authorities`.
  - Should replace SPONSOR/SITE "join a tenant" registration with **Register organisation** (`/auth/register-tenant`) and invitation acceptance.
- **Registration gap:** between the Phase 1 and Phase 2 deployments, SPONSOR/SITE sign-up is unavailable. If that's unacceptable, ship Phases 1 and 2 together.
- **API changes:**
  - `operatorId` removed from `UpdateUserStatusRequest` and GraphQL mutations.
  - `invite-admin` renamed to `/system-admin/admins` (old path kept as an alias for one release).
- **Downstream services:** custom claims `role` / `tenantId` are still written. Services that need tenant-subtree or authority decisions should call this service rather than trust claims (follow-up: `/internal/authz/check`).
- **Environment:** `NOTIFICATION_SERVICE_KEY` and `APP_SECURITY_CORS_ALLOWED_ORIGINS` must be set before deploying Phase 1.

---

## 8. ADRs to Record on Approval
- **ADR-009 (recorded):** Firebase token verification with database-sourced authorization (password validation via the Java API; claims are hints only).
- **ADR-010 (recorded):** Synthetic Firebase login email for phone-only accounts.
- **ADR-011:** Hierarchical tenants via materialized path; subtree visibility for tenant users.
- **ADR-012:** Fixed five roles + per-user authority catalogue with grant ≤ own.
- **ADR-013:** Single SYSTEM_ADMIN enforced at the database level.

---

## 9. Relation to the Hekma RBAC SRS v1.0
This plan deliberately implements a **simplified model**: five fixed roles, tenant-subtree scoping and per-user authorities. It does not use the SRS's ~40 personas, scope memberships, Keycloak or the external PolicyService. SRS principles still applied:

| SRS principle | Applied as |
|---|---|
| BR-01 / FR-ENF-03 deny by default | Exact public list; `@PreAuthorize` on every handler; build guard test |
| BR-02 / FR-TOKEN-06 server is the authority; ignore client identity | Identity from the verified token; role/tenant/authorities from the DB |
| BR-03 / FR-ASG-01 grant ≤ own | Authority assignment capped by the grantor's own set and subtree |
| FR-ASG-02 no self-elevation | No self-grant, no self-deactivation |
| FR-ASG-07 patient-only self-registration | **Deviation (OD-1):** tenants also self-register, but only as a *new* top-level tenant + owner. Self-joining an existing tenant is blocked. |
| BR-13 suspended principals/tenants denied | Filter checks user status and the tenant + ancestor statuses |
| BR-20 / FR-MEM-08 no fail-open | Unknown tenant/target → 404, never unscoped |
| FR-AUTHN-07 session revocation | `revokeRefreshTokens` + `checkRevoked=true` |
| FR-AUTHN-09 bounded invitations | 72 h single-use invitations |
| FR-ENF-11 404 for out-of-scope | Applied throughout |
| FR-ROLE-07 / FR-ASG-08 change audit | `identity_authz_audit_log` |

**Not covered (out of scope unless requested):** caregivers, care teams, break-glass, MFA enforcement for admins, study/site memberships, maker-checker, access reviews.

---

## 10. Decisions

### Resolved (2026-10-07)
| ID | Question | Decision |
|---|---|---|
| OD-1 | Who creates top-level tenants? | **Tenants self-register only.** Platform admins don't create tenants; they view, update and suspend them. |
| OD-2 | Backfill for existing SPONSOR/SITE users? | **Full tenant-owner bundle** (no behaviour change). |
| OD-3 | Must a user's role match its tenant's type? | **Yes**, enforced on registration, invitation and sub-tenant owner creation. |
| OD-4 | Does a parent suspension block descendants? | **Yes**, cascade checked at request time; descendant status values are unchanged. |
| OD-5 | Who can move patients out of the Hekma pool? | **Platform admins only** (current behaviour). |

### Open (defaults will be used unless changed)
| ID | Question | Default |
|---|---|---|
| OD-6 | Does a self-registered tenant need platform-admin approval before it becomes active? | No — active after the owner's OTP verification; admins can suspend afterwards. Unverified tenants are deleted after 7 days. |
| OD-7 | A sub-tenant's type may differ from its parent's (e.g. SPONSOR → SITE child). Is that confirmed by "any type"? | Yes; each sub-tenant's users take the sub-tenant's type (OD-3). |
