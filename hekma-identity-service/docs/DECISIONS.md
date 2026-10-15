# Architecture Decision Records (ADRs): Hekma Identity Service (`hekma-identity-service`)

This document records the architectural and design decisions made for the Hekma Identity Service in Architecture Decision Record (ADR) format.

---

## ADR-001: Hybrid Identity Architecture with Firebase Auth & PostgreSQL

- **Status**: Accepted
- **Date**: 2026-09-28
- **Context**:
  - The Hekma Platform requires enterprise-grade identity authentication, JWT token issuance, password reset, and session management, alongside complex domain requirements such as HIPAA/GDPR clinical consent auditing, multi-tenant site relationships, and administrative role hierarchies.
  - Relying exclusively on an external IdP (like Firebase) would make relational queries on user metadata, audit trails, and clinical trial linkages inefficient and restricted by IdP query limitations.
  - Building a full custom identity provider (OAuth2 authorization server, password hashing, token rotation, STS) increases operational risk and security maintenance burden.
- **Decision**:
  - Adopt a **hybrid identity architecture**:
    - **Google Firebase Authentication**: Acts as the central identity provider handling credential verification, custom claims, and JWT token issuance.
    - **PostgreSQL**: Acts as the authoritative store for user lifecycle statuses, clinical profiles, consent audit trails, OTP states, and administrative hierarchies.
- **Alternatives Considered**:
  - *Full Custom Spring Authorization Server*: Rejected due to high development overhead and ongoing maintenance burden for enterprise token rotation.
  - *Pure Firebase Auth (Firestore metadata)*: Rejected because clinical trial workflows require ACID transactions, relational foreign keys, and complex SQL filtering.
- **Consequences**:
  - Requires maintaining data synchronization across two stores (addressed in ADR-002).
  - Provides enterprise-grade token security while preserving relational querying flexibility.

---

## ADR-002: Compensating Transactions for Dual-Write Consistency

- **Status**: Accepted
- **Date**: 2026-09-28
- **Context**:
  - During registration, user accounts are created in Firebase Auth first, followed by persistence in PostgreSQL and OTP dispatch.
  - If database insertion fails (e.g., database constraint failure) or OTP dispatch fails, an orphaned account would exist in Firebase Auth, preventing future re-registration with that email.
- **Decision**:
  - Implement a **compensating transaction rollback pattern**:
    - If PostgreSQL user saving fails, catch the exception and immediately execute `firebaseService.deleteUser(uid)`.
    - If initial OTP generation or dispatch fails, delete the persisted PostgreSQL record and delete the Firebase user before rethrowing the exception.
- **Alternatives Considered**:
  - *Outbox Pattern with Asynchronous Sync*: Rejected for real-time user registration because users expect immediate verification feedback and cannot wait for asynchronous queue reconciliation.
  - *PostgreSQL First, Firebase Second*: Rejected because Firebase generates the globally unique `firebaseUid` needed for the PostgreSQL foreign key constraint.
- **Consequences**:
  - Eliminates orphaned accounts across distributed components.
  - Ensures clean error propagation back to client applications (`500 Internal Server Error` with rollback).

---

## ADR-003: Hierarchical Role-Based Access Control & Immutable System Admin

- **Status**: Accepted
- **Date**: 2026-09-28
- **Context**:
  - The platform encompasses five roles: `SYSTEM_ADMIN`, `ADMIN`, `SPONSOR`, `SITE`, and `PATIENT`.
  - Allowing operational administrators to modify the root system admin or modify peer administrators creates privilege escalation and accidental lockout vulnerabilities.
- **Decision**:
  - Enforce a strict role hierarchy in [UserManagementService.java](file:///D:/coding/hekma/hekma-identity-service/src/main/java/com/hekma/identity/service/UserManagementService.java):
    - `SYSTEM_ADMIN` is automatically bootstrapped at startup with a cryptographically secure random password and can never be modified or deactivated.
    - `SYSTEM_ADMIN` is the only role authorized to invite or provision `ADMIN` users.
    - `ADMIN` can manage `SPONSOR`, `SITE`, and `PATIENT`, but cannot modify peer `ADMIN` users or `SYSTEM_ADMIN`.
    - Public self-registration is strictly restricted to `SPONSOR`, `SITE`, and `PATIENT`.
- **Alternatives Considered**:
  - *Flat Permission Set*: Rejected due to lack of safeguard against administrator lockout and unauthorized privilege grants.
- **Consequences**:
  - Prevents privilege escalation and administrative deadlock.
  - Requires operators to pass their identity via `X-Operator-Id` header for auditability.

---

## ADR-004: Multi-Mode OTP Engine with BCrypt Hashing & Lockout Protection

- **Status**: Accepted
- **Date**: 2026-09-29
- **Context**:
  - Patient onboarding and authentication require SMS and Email One-Time Password (OTP) verification.
  - Plaintext OTP storage in databases exposes users to database leak vulnerabilities.
  - Unlimited OTP requests allow SMS toll fraud and brute-force guessing attacks.
- **Decision**:
  - Build an internal OTP lifecycle engine ([OtpService.java](file:///D:/coding/hekma/hekma-identity-service/src/main/java/com/hekma/identity/service/OtpService.java)):
    - Generate 6-digit numeric OTPs.
    - Store OTPs exclusively as BCrypt hashes (`hashedOtp`).
    - Enforce 5-minute expiry per code.
    - Limit verification attempts to maximum 5 (after 5 failures, attempt is `INVALIDATED`).
    - Limit resends to maximum 3 per attempt ID.
    - Enforce rate limit of 5 requests per hour per destination; trigger a 30-minute lockout on violation (`OtpLockoutEntity`).
    - Log all lifecycle events to `OtpAuditLogEntity`.
- **Alternatives Considered**:
  - *Third-party Auth0 / Twilio Verify*: Rejected to maintain full sovereignty over patient data, clinical audit logs, and on-premise deployment portability.
- **Consequences**:
  - Strong resistance to brute-force attacks and SMS pumping abuse.
  - Complete regulatory audit trail for compliance verification.

---

## ADR-005: Soft Deletion Strategy Using Hibernate `@SQLRestriction`

- **Status**: Accepted
- **Date**: 2026-09-29
- **Context**:
  - In clinical trial environments (GxP, 21 CFR Part 11, HIPAA), permanent deletion (`DELETE FROM users`) destroys audit history, invalidating regulatory trial records.
  - Manual filtering (`WHERE is_deleted = false`) across all repository methods is prone to human error and developer omission.
- **Decision**:
  - Implement soft deletion via Hibernate `@SQLRestriction("is_deleted = false")` on [UserEntity.java](file:///D:/coding/hekma/hekma-identity-service/src/main/java/com/hekma/identity/domain/UserEntity.java).
  - Deletion sets `isDeleted = true`, `isActive = false`, and `status = INACTIVE`.
- **Alternatives Considered**:
  - *Spring Data JPA `@Query` manual filtering*: Rejected due to developer friction and risk of missing clauses in joined queries.
  - *Hard Delete with Archive Table*: Rejected due to schema synchronization overhead across archive and primary tables.
- **Consequences**:
  - Soft-deleted users are automatically excluded from all standard JPA queries and foreign key lookups without cluttering business logic.
  - Hard records remain preserved in PostgreSQL for compliance auditing.

---

## ADR-006: Dual API Exposure: REST for Transactions, GraphQL for Administrative Search

- **Status**: Accepted
- **Date**: 2026-09-29
- **Context**:
  - Mobile applications and registration web forms require predictable, standardized REST endpoints for authentication and OTP operations.
  - Administrative dashboards require flexible querying of the user directory with dynamic role filters, counts, and nested patient details without incurring N+1 database queries.
- **Decision**:
  - Expose REST endpoints under `/api/v1/**` for transactional commands (login, register, OTP, status updates).
  - Expose Spring for GraphQL under `/graphql` for administrative queries and mutations, utilizing `@BatchMapping` for eager batch loading of `patientDetails`.
- **Alternatives Considered**:
  - *Pure REST with complex query parameters*: Led to either over-fetching or under-fetching for complex admin dashboards.
  - *Pure GraphQL*: Increased client complexity for simple mobile authentication and OTP exchanges.
- **Consequences**:
  - Best of both worlds: Simple, hardened REST contracts for public authentication and flexible, batch-optimized GraphQL for administrative reporting.

---

## ADR-007: Integration with `hekma-notification-service`

- **Status**: Accepted
- **Date**: 2026-09-30
- **Context**:
  - The identity service needs to dispatch OTP emails, welcome emails, and in-app notifications.
  - Embedding email/SMS transport protocols directly inside `hekma-identity-service` creates tight coupling with third-party messaging providers and complicates template management.
- **Decision**:
  - Delegate outbound messaging to the dedicated `hekma-notification-service` via HTTP REST client [NotificationServiceClient.java](file:///D:/coding/hekma/hekma-identity-service/src/main/java/com/hekma/identity/notification/NotificationServiceClient.java).
  - Authenticate requests using an internal service key header `X-Hekma-Service-Key`.
  - Include fail-soft handling to ensure offline resilience during local development.
- **Alternatives Considered**:
  - *Direct SMTP / SendGrid in Identity Service*: Rejected to avoid duplicating notification infrastructure across multiple microservices.
- **Consequences**:
  - Decoupled messaging architecture; centralized notification templates and delivery analytics in `hekma-notification-service`.

---

## ADR-008: Strict Git Workflow Governance in `AGENTS.md`

- **Status**: Accepted
- **Date**: 2026-10-01
- **Context**:
  - Autonomous AI agents working on codebases risk committing unverified changes or pushing broken states directly to remote branches without human review.
- **Decision**:
  - Mandate in [AGENTS.md](file:///D:/coding/hekma/hekma-identity-service/AGENTS.md) that agents **NEVER** run `git commit` or `git push` unless explicitly asked by the user in the prompt.
  - All modifications must remain in the working tree for the developer to inspect.
- **Alternatives Considered**:
  - *Automatic Commits*: Rejected due to potential unreviewed changes polluting Git history.
- **Consequences**:
  - Total developer control over Git branch history and release cadence.

---

## ADR-009: Firebase Token Verification with Database-Sourced Authorization

- **Status**: Accepted
- **Date**: 2026-10-07
- **Context**:
  - All business endpoints were `permitAll`; the caller's identity came from a client header (`X-Operator-Id`) and tenant from `X-Tenant-ID`.
  - The RBAC SRS v1.0 recommends Keycloak; the product decision is to keep Firebase, with all password validation performed by the Java API.
- **Decision**:
  - Every protected request carries a Firebase ID token verified with the Admin SDK (`verifyIdToken(token, checkRevoked=true)`).
  - Role, tenant and status are loaded from PostgreSQL (`HekmaPrincipal`); custom claims are hints for other services only.
  - Deny by default: only an explicit list of `POST` endpoints is public; handlers declare `@PreAuthorize` rules.
  - Sessions are revoked (`revokeRefreshTokens`) on deactivation, soft deletion and password reset.
  - Outside explicit mock mode, missing Firebase credentials or Web API key fail application startup.
- **Alternatives Considered**:
  - *Keycloak (per SRS)*: Deferred; would require rewriting registration, login and OTP flows.
  - *Trusting token claims for role/tenant*: Rejected; claims go stale until token refresh and cannot express future per-user authorities.
- **Consequences**:
  - Clients must send `Authorization: Bearer <idToken>`; `X-Operator-Id` / `operatorId` were removed (breaking change for `hekma-test-app`).
  - Deviations from the SRS (password accepted by the API, 60-minute Firebase ID tokens) are documented in [RBAC_PLAN.md](RBAC_PLAN.md).

---

## ADR-010: Synthetic Firebase Login Email for Phone-Only Accounts

- **Status**: Accepted
- **Date**: 2026-10-07
- **Context**:
  - Firebase can only verify passwords for email/password accounts. Phone-only users were logged in with a custom token and no password check.
- **Decision**:
  - Every account has a Firebase login email stored in `identity_users.auth_email`: the real email, or `phone-<uuid>@phone.hekma.internal` for phone-only accounts.
  - Login always validates the password through Firebase with `auth_email`. Legacy phone-only accounts without one must complete the password reset flow, which assigns it.
- **Alternatives Considered**:
  - *OTP-only login for phone users*: Rejected by product decision.
  - *Require email for everyone*: Rejected by product decision.
- **Consequences**:
  - Credentials stay in Firebase; the synthetic address is internal and never shown to users.

---

## ADR-011: Hierarchical Tenants via Materialized Path

- **Status**: Accepted
- **Date**: 2026-10-07
- **Context**:
  - Tenants must be able to create sub-tenants of any type at any depth, and SPONSOR/SITE users must see their own tenant and every descendant only.
- **Decision**:
  - Store `parent_tenant_id` plus an immutable materialized `path` (`/<root-id>/.../<id>/`) and `depth` on `identity_tenants`. Subtree queries use `path LIKE '<caller-path>%'` (indexed with `varchar_pattern_ops`); ancestry checks parse the path.
  - Tenant IDs are assigned by the application so the path can be computed before insert.
  - A tenant is usable only when it and all ancestors are `ACTIVE` (checked on every request and at login).
  - Top-level tenants are created only by self-registration (`POST /api/v1/auth/register-tenant`), `PENDING_VERIFICATION` until the owner's OTP is verified.
- **Alternatives Considered**:
  - *Recursive CTE on `parent_tenant_id`*: Rejected for request-path checks (one query per lookup, harder to index for subtree listing, H2 test parity).
  - *Closure table*: More flexible (supports re-parenting) but more writes and joins; re-parenting is not a requirement.
- **Consequences**:
  - Re-parenting a tenant is not supported (paths are immutable).
  - Until RBAC Phase 3, every SPONSOR/SITE user can manage tenants in their subtree; authorities will narrow this.

---

## ADR-012: Fixed Roles plus Per-User Authorities with Grant ≤ Own

- **Status**: Accepted
- **Date**: 2026-10-07
- **Context**:
  - The platform keeps exactly five roles, but tenants must be able to give individual SPONSOR/SITE users different capabilities.
- **Decision**:
  - A migration-managed catalogue of 12 authorities (`domain.resource:action` keys, e.g. `patient:read`) stored per user in `identity_user_authorities`; platform admins hold all implicitly, patients none.
  - Authorities are loaded from the database on every request (no cross-request cache), exposed as Spring granted authorities, and checked with `@PreAuthorize("hasAuthority('…')")`; scope (tenant subtree) is checked in services.
  - Grant ≤ own: a user can add or remove only authorities it holds, never on itself. Tenant owners receive all authorities; invitees a default bundle capped by the inviter.
  - Every privileged change is written to the append-only `identity_authz_audit_log`.
  - A build guard test fails when a handler declares no authorization rule.
- **Alternatives Considered**:
  - *Custom roles per tenant*: More flexible but harder to reason about; deferred.
  - *Authorities in Firebase custom claims*: Rejected; claims go stale until token refresh and revocations would not apply immediately.
- **Consequences**:
  - One extra indexed query per authenticated request for SPONSOR/SITE users.

---

## ADR-013: Single SYSTEM_ADMIN Enforced by the Database

- **Status**: Accepted
- **Date**: 2026-10-07
- **Decision**: A partial unique index `identity_uq_users_single_system_admin` (`role = 'SYSTEM_ADMIN' AND is_deleted = FALSE`) guarantees at most one root administrator, in addition to the startup initializer's check.
- **Consequences**: Any attempt to create a second `SYSTEM_ADMIN` fails at the database level.

---

## ADR-014: Configurable Role Default Authorities with Cascade Flag

- **Status**: Accepted
- **Date**: 2026-10-13
- **Context**:
  - The platform provides 12 fine-grained authorities, but default roles (`ADMIN`, `SPONSOR`, `SITE`) relied on static in-code bundles (`OWNER_BUNDLE`, `DEFAULT_INVITE_BUNDLE`).
  - There was no metadata endpoint returning available authorities and categories for frontend clients.
- **Decision**:
  - Expose `GET /api/v1/system-admin/authorities` and `GET /api/v1/authorities` returning the complete 12-authority catalogue categorized into *Tenant Governance*, *User Management*, and *Clinical & Patients*.
  - Create table `identity_role_authorities` (Flyway `V9__role_authorities.sql`) mapping configurable roles (`ADMIN`, `SPONSOR`, `SITE`) to default authorities.
  - Expose `PUT /api/v1/system-admin/roles/{role}/authorities` accepting `applyToExistingUsers: boolean`.
  - When `applyToExistingUsers == false`: Updates role default template for subsequent registrations/invitations only.
  - When `applyToExistingUsers == true`: Cascades the updated authorities to all existing active users of that role in `identity_user_authorities`.
  - `SYSTEM_ADMIN` remains immutable root holding all authorities permanently; `PATIENT` cannot hold administrative authorities.
  - Audited in `identity_authz_audit_log` (`ROLE_AUTHORITIES_CHANGED`).
- **Consequences**:
  - Dynamic runtime configuration of role authority templates without modifying code.
