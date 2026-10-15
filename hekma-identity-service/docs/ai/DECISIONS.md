# Architecture Decisions

This document records the architectural decisions made for the `hekma-identity-service`, capturing the context, decision rationale, alternatives considered, and consequences.

---

## ADR-001 — Hybrid Identity Architecture with Firebase Auth & PostgreSQL

Status: Accepted

### Context
The Hekma Platform requires enterprise-grade identity authentication, JWT token issuance, password reset, and session management alongside complex domain requirements such as HIPAA/GDPR clinical consent auditing, multi-tenant site relationships, and administrative role hierarchies. Relying exclusively on an external IdP (like Firebase) restricts relational querying on user metadata and clinical trial linkages. Building a full custom identity provider (OAuth2 server, password hashing, token rotation) increases operational risk and security maintenance burden.

### Decision
Adopt a **hybrid identity architecture**:
- **Google Firebase Authentication**: Central identity provider handling credential verification, custom claims, and JWT token issuance.
- **PostgreSQL**: Authoritative store for user lifecycle statuses, clinical profiles, consent audit trails, OTP states, and administrative hierarchies.

### Alternatives Considered
- *Full Custom Spring Authorization Server*: Rejected due to high development overhead and ongoing maintenance burden for enterprise token rotation.
- *Pure Firebase Auth (Firestore metadata)*: Rejected because clinical trial workflows require ACID transactions, relational foreign keys, and complex SQL filtering.

### Consequences
- Requires maintaining data synchronization across two stores (addressed in ADR-002).
- Provides enterprise-grade token security while preserving relational querying flexibility.

---

## ADR-002 — Dual-Write Saga Pattern with Compensating Rollbacks

Status: Accepted

### Context
During registration, user accounts are created in Firebase Auth first, followed by persistence in PostgreSQL and OTP dispatch. If database insertion fails (e.g., database constraint failure) or OTP dispatch fails, an orphaned account would exist in Firebase Auth, preventing future re-registration with that email.

### Decision
Implement a **compensating transaction rollback pattern**:
- If PostgreSQL user saving fails, catch the exception and immediately execute `firebaseService.deleteUser(uid)`.
- If initial OTP generation or dispatch fails, delete the persisted PostgreSQL record and delete the Firebase user before rethrowing the exception.

### Alternatives Considered
- *Outbox Pattern with Asynchronous Sync*: Rejected for real-time user registration because users expect immediate verification feedback and cannot wait for asynchronous queue reconciliation.
- *PostgreSQL First, Firebase Second*: Rejected because Firebase generates the globally unique `firebaseUid` needed for the PostgreSQL foreign key constraint.

### Consequences
- Eliminates orphaned accounts across distributed components.
- Ensures clean error propagation back to client applications (`500 Internal Server Error` with rollback).

---

## ADR-003 — Hierarchical Role-Based Access Control & Immutable System Admin

Status: Accepted

### Context
The platform encompasses five roles: `SYSTEM_ADMIN`, `ADMIN`, `SPONSOR`, `SITE`, and `PATIENT`. Allowing operational administrators to modify the root system admin or modify peer administrators creates privilege escalation and accidental lockout vulnerabilities.

### Decision
Enforce a strict role hierarchy in `UserManagementService`:
- `SYSTEM_ADMIN` is automatically bootstrapped at startup with a cryptographically secure random password and can never be modified or deactivated.
- `SYSTEM_ADMIN` is the only role authorized to invite or provision `ADMIN` users.
- `ADMIN` can manage `SPONSOR`, `SITE`, and `PATIENT`, but cannot modify peer `ADMIN` users or `SYSTEM_ADMIN`.
- Public self-registration is strictly restricted to `SPONSOR`, `SITE`, and `PATIENT`.

### Alternatives Considered
- *Flat Permission Set*: Rejected due to lack of safeguard against administrator lockout and unauthorized privilege grants.

### Consequences
- Prevents privilege escalation and administrative deadlock.
- Operator identity is taken from the verified access token (superseded the former `X-Operator-Id` header; see ADR-009).

---

## ADR-004 — Multi-Mode OTP Engine with BCrypt Hashing & Lockout Protection

Status: Accepted

### Context
Patient onboarding and authentication require SMS and Email One-Time Password (OTP) verification. Plaintext OTP storage in databases exposes users to database leak vulnerabilities. Unlimited OTP requests allow SMS toll fraud and brute-force guessing attacks.

### Decision
Build an internal OTP lifecycle engine (`OtpService`):
- Generate 6-digit numeric OTPs.
- Store OTPs exclusively as BCrypt hashes (`hashedOtp`).
- Enforce 5-minute expiry per code.
- Limit verification attempts to maximum 5 (after 5 failures, attempt is `INVALIDATED`).
- Limit resends to maximum 3 per attempt ID.
- Enforce rate limit of 5 requests per hour per destination; trigger a 30-minute lockout on violation (`OtpLockoutEntity`).
- Log all lifecycle events to `OtpAuditLogEntity`.

### Alternatives Considered
- *Third-party Auth0 / Twilio Verify*: Rejected to maintain full sovereignty over patient data, clinical audit logs, and on-premise deployment portability.

### Consequences
- Strong resistance to brute-force attacks and SMS pumping abuse.
- Complete regulatory audit trail for compliance verification.

---

## ADR-005 — Soft Deletion Strategy Using Hibernate `@SQLRestriction`

Status: Accepted

### Context
In clinical trial environments (GxP, 21 CFR Part 11, HIPAA), permanent deletion (`DELETE FROM users`) destroys audit history, invalidating regulatory trial records. Manual filtering (`WHERE is_deleted = false`) across all repository methods is prone to human error and developer omission.

### Decision
Apply Hibernate `@SQLRestriction("is_deleted = false")` on `UserEntity`:
- Soft deletion sets `isDeleted = true`, `isActive = false`, and `status = INACTIVE`.
- Hibernate automatically appends `AND is_deleted = false` to all standard JPA queries, preventing soft-deleted users from being inadvertently accessed or authenticated.

### Alternatives Considered
- *Manual Repository Query Filters*: Rejected due to risk of accidental data leakage if a developer writes a custom query without the filter.
- *PostgreSQL Views or Triggers*: Rejected to keep database logic testable in H2 and transparent in application code.

### Consequences
- Guarantees zero unintentional leaks of deleted records.
- Preserves full audit history in the database.

---

## ADR-006 — Dual Query Interface (Spring REST OpenAPI & Spring for GraphQL)

Status: Accepted

### Context
Client applications require traditional, deterministic REST APIs for core authentication workflows (registration, login, OTP verification), while back-office administrative dashboards and trial portals require flexible querying across nested clinical user profiles without over-fetching or multiple round-trip HTTP requests.

### Decision
Support a **dual interface strategy**:
- **REST Endpoints (`/api/v1/**`)**: Handle all state-changing operational mutations, authentication, OTP flows, and user status updates, fully documented via SpringDoc OpenAPI.
- **GraphQL Endpoint (`/graphql`)**: Provide flexible, schema-driven queries and batch resolution for administrative user exploration, filtering by role, status, and patient consent details.

### Alternatives Considered
- *REST-Only with Dynamic Query Parameters*: Proved rigid and led to over-fetching when displaying composite clinical user dashboards.
- *GraphQL-Only*: Difficult for mobile clients and webhook callers executing strict authentication handshakes and file/token operations.

### Consequences
- Optimal developer experience across both simple authentication clients and complex administrative dashboards.

---

## ADR-007 — Direct HTTP REST Communication with Notification Service

Status: Accepted

### Context
The identity service requires sending real-time SMS OTPs, Email OTPs, and welcome messages via `hekma-notification-service`.

### Decision
Use a synchronous HTTP REST client (`NotificationServiceClient`) secured with a shared service key (`X-Hekma-Service-Key`):
- For registration OTPs, synchronous dispatch ensures immediate validation before concluding registration.
- For non-critical welcome emails, errors are caught and logged without aborting registration.

### Alternatives Considered
- *Message Broker (Kafka / RabbitMQ)*: Deferred to future roadmap when transaction volume warrants asynchronous event-driven streaming.

### Consequences
- Simple, lightweight inter-service integration with minimal infrastructure footprint.

---

## ADR-009 — Firebase Token Verification with Database-Sourced Authorization

Status: Accepted (2026-10-07)

### Context
All business endpoints were `permitAll`; caller identity came from the client header `X-Operator-Id` and tenant from `X-Tenant-ID`. The RBAC SRS recommends Keycloak, but the product decision is to keep Firebase with all password validation through the Java API.

### Decision
Verify a Firebase ID token on every protected request (`verifyIdToken(token, checkRevoked=true)`), load role/tenant/status from PostgreSQL into `HekmaPrincipal`, deny by default with an explicit public endpoint list, and declare `@PreAuthorize` rules per handler. Revoke sessions on deactivation, soft deletion and password reset. Fail startup when Firebase credentials or Web API key are missing outside mock mode.

### Alternatives Considered
- *Keycloak*: Deferred (large rewrite).
- *Trust token claims for role/tenant*: Rejected (stale claims, no per-user authorities).

### Consequences
Clients must send `Authorization: Bearer <idToken>`; `X-Operator-Id`/`operatorId` were removed. See [docs/RBAC_PLAN.md](../RBAC_PLAN.md).

---

## ADR-010 — Synthetic Firebase Login Email for Phone-Only Accounts

Status: Accepted (2026-10-07)

### Context
Firebase only verifies passwords for email/password accounts; phone-only users previously received tokens without any password check.

### Decision
Store a Firebase login email in `identity_users.auth_email` (real email, or `phone-<uuid>@phone.hekma.internal`). Login always validates the password through Firebase with it; legacy phone-only accounts obtain one through the password reset flow.

### Consequences
Credentials remain in Firebase; the synthetic address is internal only.

---

## ADR-011 — Hierarchical Tenants via Materialized Path

Status: Accepted (2026-10-07)

### Context
Tenants create sub-tenants of any type at any depth; SPONSOR/SITE users see their tenant and every descendant only.

### Decision
`identity_tenants` gains `parent_tenant_id`, an immutable materialized `path` (`/<root-id>/.../<id>/`) and `depth`; subtree = `path LIKE '<caller-path>%'`. IDs are application-assigned so the path is known before insert. A tenant is usable only when it and all ancestors are `ACTIVE`. Top-level tenants come only from `POST /api/v1/auth/register-tenant` (`PENDING_VERIFICATION` until owner OTP).

### Alternatives Considered
- *Recursive CTE*: slower request-path checks, weaker indexing. *Closure table*: supports re-parenting (not required) at higher write cost.

### Consequences
No re-parenting. Until Phase 3, all SPONSOR/SITE users can manage their subtree.

---

## ADR-012 — Fixed Roles plus Per-User Authorities with Grant ≤ Own

Status: Accepted (2026-10-07)

### Decision
12 migration-managed authorities (`patient:read`, …) stored per SPONSOR/SITE user; admins hold all, patients none. Loaded from the DB on every request, enforced with `hasAuthority('…')` + subtree checks in services. Grant ≤ own, no self-change, audited in `identity_authz_audit_log`. Owners get all; invitees a default bundle capped by the inviter. A build guard test requires `@PreAuthorize` on every handler.

### Consequences
One extra indexed query per SPONSOR/SITE request; revocations apply immediately.

---

## ADR-013 — Single SYSTEM_ADMIN Enforced by the Database

Status: Accepted (2026-10-07)

Partial unique index `identity_uq_users_single_system_admin` on non-deleted `SYSTEM_ADMIN` rows.

---

## ADR-014 — Configurable Role Default Authorities with Cascade Flag

Status: Accepted (2026-10-13)

### Context
While the platform provides 12 granular authorities, roles (`ADMIN`, `SPONSOR`, `SITE`) previously relied on in-code static bundles (`OWNER_BUNDLE`, `DEFAULT_INVITE_BUNDLE`). Furthermore, frontends lacked a metadata API to discover available authorities and functional permission categories.

### Decision
1. **Authority Catalogue API**: Expose `GET /api/v1/system-admin/authorities` and `GET /api/v1/authorities` returning the complete 12-authority catalogue categorized into *Tenant Governance*, *User Management*, and *Clinical & Patients*.
2. **Configurable Role Default Authorities**: Introduce `identity_role_authorities` table (migration `V9__role_authorities.sql`) mapping configurable roles (`ADMIN`, `SPONSOR`, `SITE`) to default authorities.
3. **Cascade Flag (`applyToExistingUsers`)**:
   - `PUT /api/v1/system-admin/roles/{role}/authorities` accepts `applyToExistingUsers: boolean`.
   - When `false`: updates role default template for subsequent user registrations/invitations only; existing users retain current authorities.
   - When `true`: updates template and cascades changes to all active users with that role in `identity_user_authorities`.
4. **Role Invariants**:
   - `SYSTEM_ADMIN` remains immutable root holding all authorities permanently.
   - `PATIENT` remains restricted to patient self-service (cannot hold administrative authorities).
   - Privilege changes audited in `identity_authz_audit_log` (`ROLE_AUTHORITIES_CHANGED`).

### Consequences
Role defaults are dynamically configurable without code deployments. Clear separation between template changes and bulk existing-user updates.

---

## ADR-015 — Distributed Tracing and Correlation Context across Backend Microservices

Status: Accepted (2026-10-13)

### Context
With multiple collaborating microservices (`hekma-identity-service`, `hekma-notification-service`, `hekma-ctms-service`), diagnosing issues across service boundaries, tracking asynchronous notifications, and inspecting client error reports required a unified correlation ID standard.

### Decision
1. **High-Precedence Trace Filter**: Every backend microservice registers `TraceIdFilter` (`@Order(Ordered.HIGHEST_PRECEDENCE)`).
2. **Correlation ID Ingestion & Generation**: Ingests incoming `X-Trace-Id`, `trace-id`, or `X-Request-Id` headers; falls back to generating a random UUID.
3. **MDC Storage**: Sets `traceId` in SLF4J MDC for the request lifecycle, ensuring clean removal in a `finally` block.
4. **Dual Response Headers**: Every HTTP response sets both `X-Trace-Id` and `trace-id` response headers across success (2xx) and failure (4xx/5xx) statuses.
5. **Error Body Integration**: All REST error responses (`ApiErrorResponse`) and raw security rejections (401/403 in `SecurityErrorWriter`) include a `traceId` field matching the MDC context.
6. **Outbound Propagation**: All inter-service REST clients (`NotificationServiceClient`, `IdentityServiceClient`) extract `traceId` from MDC and forward `X-Trace-Id` and `trace-id` headers on downstream HTTP calls.
7. **Structured Log Pattern**: Configure `logging.pattern.level: "%5p [traceId=%X{traceId:-}]"` across all services so console log lines output `[traceId=<id>]`.

### Consequences
- Full distributed tracing correlation across client web app, gateway, identity, notification, and CTMS microservices.
- Zero performance overhead, zero third-party agent dependencies.

