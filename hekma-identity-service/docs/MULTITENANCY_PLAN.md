# Architecture & Implementation Plan: Multi-Tenancy in Hekma Platform

**Target Service**: `hekma-identity-service`  
**Status**: Proposal / Revised Draft (Restricted Tenant Roles: `SPONSOR` & `SITE` Only; Patient-to-Site/Sponsor Association & Default Tenant Fallback)  
**Author**: Antigravity AI Agent  
**Date**: 2026-10-06  

---

## 1. Executive Summary & Objectives

The **Hekma Platform** is expanding to support a **multi-tenant architecture** designed specifically for a decentralized clinical trial (DCT) and digital health ecosystem.

### Core Architectural Principle: Role Scoping & Patient Association

Across the platform's five canonical roles (`SYSTEM_ADMIN`, `ADMIN`, `SPONSOR`, `SITE`, `PATIENT`), tenancy is governed by three foundational rules:

1. **Tenant Organizational Staff are Strictly Restricted to `SPONSOR` and `SITE`**:
   - **`SPONSOR`**: Pharmaceutical companies, biotechnology firms, or clinical trial sponsor organizations.
   - **`SITE`**: Healthcare institutions, clinical trial sites, academic hospitals, and principal investigator networks.
   - *Invariant*: The organizational staff/members within a tenant organization can **ONLY** hold the role `SPONSOR` or `SITE`. Tenants cannot have staff with role `ADMIN`, `SYSTEM_ADMIN`, or `PATIENT`.

2. **Platform-Global Roles (`tenant_id IS NULL`)**:
   - **`SYSTEM_ADMIN`**: Root platform super-administrator (`system.admin@hekma.com`), managing infrastructure, tenant provisioning, and global policies.
   - **`ADMIN`**: Platform operational administrator (`admin@hekma.com`), governing tenants, clinical workflows, and system coordinators.

3. **Patient Association & Mapping Model (`PATIENT`)**:
   - A `PATIENT` is **always associated with a tenant and mapped to a `SITE` or `SPONSOR` user**:
     - **Pathway A (Invited / Created by `SITE` or `SPONSOR` User)**: A `SITE` or `SPONSOR` user can create a patient's profile and dispatch an email invitation link/code. Upon registration, the patient is mapped directly to that `SITE`/`SPONSOR` user (`patient_details.assigned_user_id`) and associated with their tenant (`users.tenant_id = inviter.tenant_id`).
     - **Pathway B (Direct Public Registration)**: If a patient registers directly without a site or sponsor invitation code/link, they are **always automatically associated with the Default Tenant (`default-tenant`, Hekma)** (`tenant_id = defaultTenant.getId()`, where `default_tenant = TRUE`). In the default tenant, the patient belongs to the general Hekma recruitment cohort and can subsequently be assigned to a specific clinical site or trial coordinator.

---

## 2. Role-to-Tenancy Architecture Matrix

| Role | Tenancy Scope | `tenant_id` Requirement | User Mapping Requirement | Registration Pathway | Description & Responsibilities |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`SYSTEM_ADMIN`** | Platform Global | `NULL` (Always) | None | Startup Auto-Bootstrap | Root governance superuser. Provisions tenants, assigns platform policies, invites platform `ADMIN` users. |
| **`ADMIN`** | Platform Global | `NULL` (Always) | None | Startup Auto-Bootstrap (`admin@hekma.com`) / Invited by `SYSTEM_ADMIN` | Platform operational coordinator. Governs tenants, manages coordinators, and oversees unassigned patients in the default tenant. |
| **`SPONSOR`** | **Tenant Member** | **UUID (Mandatory)** | None | Public Self-Registration / Tenant Invitation | Organizational member of a pharmaceutical sponsor tenant. Can create patient profiles and invite patients to studies. |
| **`SITE`** | **Tenant Member** | **UUID (Mandatory)** | None | Public Self-Registration / Tenant Invitation | Organizational member of a clinical trial site / hospital tenant. Can create patient profiles and invite patients to clinical trials. |
| **`PATIENT`** | **Tenant Associated** | **UUID (Mandatory)** | **Mapped to `SITE` or `SPONSOR` user** (or Default Tenant pool) | Invited by `SITE`/`SPONSOR` via email, OR direct self-registration | Clinical trial participant. Always associated with the tenant of their mapped `SITE`/`SPONSOR` user; if registered directly, associated with Default Tenant (Hekma). |

```
                                +-----------------------------------+
                                |            Hekma Platform         |
                                |       Platform Global Scope       |
                                +-----------------+-----------------+
                                                  |
                         +------------------------+------------------------+
                         |                                                 |
                         v                                                 v
        +---------------------------------+               +---------------------------------+
        |          SYSTEM_ADMIN           |               |              ADMIN              |
        |   (system.admin@hekma.com)      |               |       (admin@hekma.com)         |
        |        tenant_id = NULL         |               |        tenant_id = NULL         |
        +----------------+----------------+               +----------------+----------------+
                         |                                                 |
                         +------------------------+------------------------+
                                                  | Governs & Provisions
                                                  v
        +-----------------------------------------------------------------------------------+
        |                                TENANT ORGANIZATIONS                               |
        |                                                                                   |
        |  +-----------------------------------------------------------------------------+  |
        |  |            Default Tenant (Hekma)  [default_tenant = TRUE, UUID_DEFAULT]    |  |
        |  |  - Staff Roles: SPONSOR, SITE                                               |  |
        |  |  - Direct Self-Registered Patients fall here:                               |  |
        |  |      * PATIENT (tenant_id = UUID_DEFAULT, assigned_user_id = Coordinator)   |  |
        |  +-----------------------------------------------------------------------------+  |
        |                                                                                   |
        |  +-------------------------------------+   +-----------------------------------+  |
        |  |         Sponsor Tenant (A)          |   |          Site Tenant (B)          |  |
        |  |      (e.g., Pfizer / Roche)         |   |    (e.g., Mayo Clinic / Site)     |  |
        |  |  - Staff Roles: SPONSOR             |   |  - Staff Roles: SITE              |  |
        |  |  - Member: SPONSOR User (User 1)    |   |  - Member: SITE User (User 2)     |  |
        |  |       |                             |   |       |                           |  |
        |  |       | Creates Profile &           |   |       | Creates Profile &         |  |
        |  |       | Sends Email Invite          |   |       | Sends Email Invite        |  |
        |  |       v                             |   |       v                           |  |
        |  |    PATIENT (A1)                     |   |    PATIENT (B1)                   |  |
        |  |    * tenant_id = UUID_A             |   |    * tenant_id = UUID_B           |  |
        |  |    * mapped to User 1 (SPONSOR)     |   |    * mapped to User 2 (SITE)      |  |
        |  +-------------------------------------+   +-----------------------------------+  |
        +-----------------------------------------------------------------------------------+
```

---

## 3. Database Schema & Migration Strategy

### 3.1 New Entity: `TenantEntity` (`tenants` table)

The `tenants` table stores tenant metadata and includes:
- `default_tenant BOOLEAN NOT NULL DEFAULT FALSE`: Designates the default platform organization.
- `tenant_type VARCHAR(50)`: Indicates whether the tenant is a `SPONSOR` organization, a `SITE` organization, or a generic organizational tenant.
- A PostgreSQL partial unique index ensuring that at most one default tenant exists.

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    tenant_type VARCHAR(50) NOT NULL DEFAULT 'SPONSOR', -- 'SPONSOR', 'SITE', 'GENERAL'
    default_tenant BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    subscription_tier VARCHAR(50) DEFAULT 'STANDARD',
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    settings JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(255) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0
);

-- Ensure only one default tenant exists across the entire platform
CREATE UNIQUE INDEX uq_tenants_default_true ON tenants(default_tenant) WHERE default_tenant = TRUE;
CREATE INDEX idx_tenants_slug ON tenants(slug);
CREATE INDEX idx_tenants_status ON tenants(status);
CREATE INDEX idx_tenants_type ON tenants(tenant_type);
```

### 3.2 Modifying `users` Table with Role-Tenancy Constraint (`V9__create_tenants_and_add_tenant_id_to_users.sql`)

```sql
-- 1. Create tenants table
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    tenant_type VARCHAR(50) NOT NULL DEFAULT 'GENERAL',
    default_tenant BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    subscription_tier VARCHAR(50) DEFAULT 'STANDARD',
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    settings JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(255) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX uq_tenants_default_true ON tenants(default_tenant) WHERE default_tenant = TRUE;
CREATE INDEX idx_tenants_slug ON tenants(slug);
CREATE INDEX idx_tenants_status ON tenants(status);

-- 2. Seed Default Organization (default_tenant = TRUE)
INSERT INTO tenants (id, name, slug, tenant_type, default_tenant, status, contact_email, created_by, updated_by)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Default Organization',
    'default-tenant',
    'GENERAL',
    TRUE,
    'ACTIVE',
    'admin@hekma.com',
    'SYSTEM_MIGRATION',
    'SYSTEM_MIGRATION'
)
ON CONFLICT (id) DO NOTHING;

-- 3. Add tenant_id column to users
ALTER TABLE users ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE RESTRICT;

-- 4. Backfill existing SPONSOR, SITE, and PATIENT users to default-tenant
-- SYSTEM_ADMIN and ADMIN remain NULL (platform-global)
UPDATE users 
SET tenant_id = '00000000-0000-0000-0000-000000000001' 
WHERE tenant_id IS NULL AND role IN ('SPONSOR', 'SITE', 'PATIENT');

-- 5. Enforce Strict Role-Tenancy Invariant at Database Level
-- SPONSOR, SITE, and PATIENT users MUST have a tenant_id.
-- SYSTEM_ADMIN and ADMIN users must NEVER have a tenant_id (platform-global governance).
ALTER TABLE users ADD CONSTRAINT chk_users_tenant_role CHECK (
    (role IN ('SPONSOR', 'SITE', 'PATIENT') AND tenant_id IS NOT NULL) OR
    (role IN ('SYSTEM_ADMIN', 'ADMIN') AND tenant_id IS NULL)
);

-- 6. Indexes for multi-tenant query performance
CREATE INDEX idx_users_tenant_id ON users(tenant_id);
CREATE INDEX idx_users_tenant_role ON users(tenant_id, role);
CREATE INDEX idx_users_tenant_status ON users(tenant_id, status);
CREATE INDEX idx_users_tenant_email ON users(tenant_id, email);

-- 7. Add assigned_user_id column to patient_details to map PATIENT to a SITE or SPONSOR user
ALTER TABLE patient_details ADD COLUMN assigned_user_id UUID REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX idx_patient_details_assigned_user ON patient_details(assigned_user_id);
```

### 3.3 JPA Entity Enhancements (`UserEntity` & `PatientDetailEntity`)

1. **`UserEntity.java`**:
   ```java
   @ManyToOne(fetch = FetchType.LAZY)
   @JoinColumn(name = "tenant_id")
   private TenantEntity tenant;
   ```
   - Invariant: When `role == Role.PATIENT`, `tenant` is non-null (pointing either to the inviting `SITE`/`SPONSOR`'s tenant, or to the `default-tenant`).
   - Invariant: When `role == Role.SYSTEM_ADMIN` or `role == Role.ADMIN`, `tenant` is always `null`.

2. **`PatientDetailEntity.java`**:
   ```java
   @ManyToOne(fetch = FetchType.LAZY)
   @JoinColumn(name = "assigned_user_id")
   private UserEntity assignedUser; // The SITE or SPONSOR user who created the profile/sent the invite
   ```
   - Invariant: If `assignedUser` is present, `assignedUser.getRole()` must be `Role.SITE` or `Role.SPONSOR` (or default tenant coordinator).
   - `assignedUser.getTenant()` must match `user.getTenant()`.


---

## 4. Administrative User Bootstrap & Generation Architecture

### 4.1 How `SYSTEM_ADMIN` is Currently Generated (Verified Ground Truth)

In the existing codebase, the root `SYSTEM_ADMIN` user is generated dynamically upon application startup without storing any plaintext password in Git or configuration files:

1. **Startup Hook (`SystemAdminInitializer.java`)**:
   - Implements Spring Boot `ApplicationRunner` with `@Order(10)`.
   - Reads configuration properties from `app.system-admin` (`SystemAdminProperties.java`):
     - `enabled`: default `true`
     - `email`: default `system.admin@hekma.com`
     - `displayName`: default `"System Administrator"`
2. **Idempotency Check**:
   - `AuthService.initializeSystemAdmin(email, displayName)` queries:
     `userRepository.existsByRole(Role.SYSTEM_ADMIN)` or `userRepository.existsByEmail(normalizedEmail)`.
   - If the system admin already exists in PostgreSQL, initialization is skipped cleanly.
3. **Cryptographically Secure Random Password Generation**:
   - If `SYSTEM_ADMIN` does not exist in Firebase, `AuthService.generateSecureRandomPassword()` generates a **20-character random password** using `java.security.SecureRandom`:
     - Guarantees at least 1 uppercase letter (`A-Z`), 1 lowercase letter (`a-z`), 1 digit (`2-9`), and 1 special symbol (`!@#$%^&*()-_=+`).
     - Randomly fills the remaining 16 characters and shuffles the character array using `Collections.shuffle(chars, SECURE_RANDOM)`.
4. **Firebase Auth Synchronization**:
   - Registers user in Firebase Auth with `normalizedEmail`, `randomPassword`, `displayName`, and role claim `SYSTEM_ADMIN`.
   - Retrieves the immutable `firebaseUid`.
5. **PostgreSQL Persistence**:
   - Inserts `UserEntity` with:
     - `email = "system.admin@hekma.com"`
     - `role = Role.SYSTEM_ADMIN`
     - `tenant_id = NULL` (platform superuser, decoupled from tenants)
     - `status = UserStatus.ACTIVE`
     - `isActive = true`
     - `emailVerified = true`
     - `twoFactorEnabled = false`
     - `verificationMode = VerificationMode.EMAIL`
6. **Password Reset Capability**:
   - The generated password is never stored in plaintext.
   - The `SYSTEM_ADMIN` logs in or uses the standard **Firebase Password Reset Flow** (`POST /api/v1/auth/forgot-password` or Firebase Auth email link) to set their operational password.

### 4.2 Bootstrapping Platform Administrator (`admin@hekma.com`)

Following the exact same secure architectural pattern as `SYSTEM_ADMIN`, a platform operational administrator (`admin@hekma.com`) is bootstrapped at startup:

```
                            +-------------------------------------------+
                            |           Application Startup             |
                            +---------------------+---------------------+
                                                  |
                                                  v
                            +-------------------------------------------+
                            |            AdminInitializer               |
                            |         (Spring ApplicationRunner)        |
                            +---------------------+---------------------+
                                                  |
                         +------------------------+------------------------+
                         |                                                 |
                         v                                                 v
        +---------------------------------+               +---------------------------------+
        |      Check PostgreSQL Exists    |               |        Check Firebase Exists    |
        |   userRepository.existsByEmail  |               |    firebaseService.getUserBy    |
        |        ("admin@hekma.com")      |               |              Email()            |
        +----------------+----------------+               +----------------+----------------+
                         |                                                 |
                         +------------------------+------------------------+
                                                  |
                               (If not present)   v
                            +-------------------------------------------+
                            |      generateSecureRandomPassword()       |
                            |   (20-char cryptographically secure)      |
                            +---------------------+---------------------+
                                                  |
                                                  v
                            +-------------------------------------------+
                            |         Firebase Admin SDK                |
                            | 1. createUser("admin@hekma.com", pass)    |
                            | 2. assignCustomClaims(uid, {              |
                            |      "role": "ADMIN"                      |
                            |    })                                     |
                            +---------------------+---------------------+
                                                  |
                                                  v
                            +-------------------------------------------+
                            |         PostgreSQL Persistence            |
                            | UserEntity:                               |
                            | - email: "admin@hekma.com"                |
                            | - role: Role.ADMIN                        |
                            | - tenant_id: NULL (Platform administrator)|
                            | - status: ACTIVE, isActive: true          |
                            | - emailVerified: true                     |
                            +---------------------+---------------------+
                                                  |
                                                  v
                            +-------------------------------------------+
                            |          Password Reset Flow              |
                            | Admin resets password via standard        |
                            | Firebase email reset or auth link         |
                            +-------------------------------------------+
```

#### Key Details for `admin@hekma.com`:
- **Role**: `Role.ADMIN`.
- **Tenant Scope**: `tenant_id = NULL` (operates platform-wide, coordinating sponsors, sites, and patients across tenants).
- **Password Generation**: Generated dynamically via `generateSecureRandomPassword()` at startup. No plaintext password stored anywhere.
- **Password Reset**: `admin@hekma.com` can reset their password at any time via the standard Firebase password reset flow.

---

## 5. Tenant Context & Hibernate `@TenantId` Integration

### 5.1 Context Scoping Rules

1. **Tenant-Scoped Requests (`SPONSOR`, `SITE`, `PATIENT`)**:
   - `TenantFilter` extracts `tenant_id` from the user's JWT claims (or `X-Tenant-ID` header during specific authorized operations).
   - Validates that the referenced tenant exists and is in `ACTIVE` status.
   - Binds `tenant_id` to `TenantContext`.
   - Hibernate 6 automatically applies `WHERE tenant_id = :tenantId` to all operations on `@TenantId`-annotated entities (`UserEntity`, `PatientDetailEntity`).
   - For `PATIENT`, queries and health record accesses are automatically confined within their associated tenant.

2. **Global Platform Requests (`SYSTEM_ADMIN`, `ADMIN`)**:
   - `TenantContext.setSystemBypass(true)` is activated.
   - For `SYSTEM_ADMIN` and `ADMIN`, queries span across all tenants (or target a specific tenant if `X-Tenant-ID: <UUID>` is explicitly provided in the request).

### 5.2 `TenantFilter` Servlet Execution

```java
public class TenantFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        try {
            Authentication auth = SecurityContextHolder.getContext().getAuthentication();
            String userRole = extractRole(auth);

            if ("SYSTEM_ADMIN".equals(userRole) || "ADMIN".equals(userRole)) {
                // Platform-global administrators bypass tenant isolation
                TenantContext.setSystemBypass(true);
                // Allow optional tenant filtering for administrators via header
                String explicitTenantHeader = request.getHeader("X-Tenant-ID");
                if (explicitTenantHeader != null) {
                    TenantContext.setTenantId(UUID.fromString(explicitTenantHeader));
                }
            } else if ("SPONSOR".equals(userRole) || "SITE".equals(userRole) || "PATIENT".equals(userRole)) {
                // Enforce tenant context for organizational members and associated patients
                UUID tenantId = extractTenantIdFromTokenOrHeader(request, auth);
                validateTenantActive(tenantId);
                TenantContext.setTenantId(tenantId);
            }

            filterChain.doFilter(request, response);
        } finally {
            TenantContext.clear(); // Mandatory cleanup to prevent ThreadLocal contamination
        }
    }
}
```

---

## 6. Authentication, Registration & Patient Invitation Workflows

### 6.1 Patient Profile Creation & Email Invitation (by `SITE` or `SPONSOR` User)

In decentralized clinical trials, patients are recruited and managed by investigator sites or trial sponsors. A `SITE` or `SPONSOR` user initiates the patient onboarding process:

```
+------------------+         +--------------------------+         +-------------------------------+
| SITE/SPONSOR User|         | hekma-identity-service   |         |  hekma-notification-service   |
+--------+---------+         +------------+-------------+         +---------------+---------------+
         |                                |                                       |
         | POST /api/v1/patients/invite   |                                       |
         | (firstName, lastName, email)   |                                       |
         |------------------------------->|                                       |
         |                                | 1. Verify caller has active tenant    |
         |                                | 2. Generate secure invitation token   |
         |                                | 3. Create UserEntity:                 |
         |                                |    - role = PATIENT                   |
         |                                |    - tenant_id = caller.tenantId      |
         |                                |    - status = PENDING_VERIFICATION    |
         |                                | 4. Create PatientDetailEntity:        |
         |                                |    - assigned_user_id = caller.id     |
         |                                |    - invitation_code = token          |
         |                                |                                       |
         |                                | POST /api/v1/notifications/email      |
         |                                | (template: PATIENT_INVITATION)        |
         |                                |-------------------------------------->|
         |                                |                                       |-- Sends email to
         |                                |<--------------------------------------|   patient with invite link
         |<-------------------------------|                                       |
         | 201 Created (Invitation Sent)  |                                       |
         |                                |                                       |
+--------+---------+         +------------+-------------+                         |
| Invited Patient  |         | hekma-identity-service   |                         |
+--------+---------+         +------------+-------------+                         |
         |                                |                                       |
         | Clicks invite link             |                                       |
         | POST /api/v1/patients/accept   |                                       |
         | (token, password, consents)    |                                       |
         |------------------------------->|                                       |
         |                                | 1. Validate invitation token & expiry |
         |                                | 2. Create Firebase user with claims:  |
         |                                |    { role: PATIENT, tenant_id: ... }  |
         |                                | 3. Record regulatory consents         |
         |                                | 4. Update status = ACTIVE             |
         |<-------------------------------|                                       |
         | 200 OK + Auth Tokens           |                                       |
```

1. **Step 1: Invitation Request (`POST /api/v1/patients/invite`)**:
   - Authorized roles: `SPONSOR`, `SITE`.
   - Caller identity provides the organizational context: `caller.getTenantId()`.
   - Payload:
     ```json
     {
       "firstName": "John",
       "lastName": "Doe",
       "email": "john.doe@example.com",
       "phoneNumber": "+1234567890",
       "clinicalStudyId": "STUDY-ONCOLOGY-01"
     }
     ```
2. **Step 2: Staging User and Mapping Record**:
   - System verifies email uniqueness across PostgreSQL and Firebase.
   - Generates a cryptographically secure invitation token/code (`invitation_code`, e.g. `INV-ROCHE-7X9Q2Z` or a 64-character UUID token with 7-day expiration).
   - Creates staged `UserEntity`:
     - `email`: `"john.doe@example.com"`
     - `role`: `Role.PATIENT`
     - `tenant_id`: `caller.getTenantId()` (adopts caller's organization)
     - `status`: `UserStatus.PENDING_VERIFICATION`, `isActive = false`
   - Creates `PatientDetailEntity`:
     - `firstName`: `"John"`, `lastName`: `"Doe"`
     - `phoneNumber`: `"+1234567890"`
     - `invitationCode`: token
     - **`assigned_user_id`**: `caller.getId()` (mapped directly to the inviting `SITE` or `SPONSOR` user!)
3. **Step 3: Email Notification Dispatch**:
   - Calls `hekma-notification-service` with template `PATIENT_INVITATION`.
   - Email includes: Inviting investigator/sponsor name, organization name, invitation link (`https://app.hekma.com/register/patient?token=XYZ&invitationCode=...`), and expiration time.
4. **Step 4: Patient Accepts Invitation (`POST /api/v1/patients/accept-invite`)**:
   - Patient clicks the link and submits:
     ```json
     {
       "invitationToken": "XYZ...",
       "password": "SecurePassword123!",
       "termsAccepted": true,
       "privacyPolicyAccepted": true,
       "healthDataConsentAccepted": true
     }
     ```
   - Validates regulatory consents.
   - Creates user in Firebase Auth with custom claims:
     ```json
     {
       "role": "PATIENT",
       "tenant_id": "<INVITER_TENANT_UUID>"
     }
     ```
   - Updates `UserEntity`: `status = UserStatus.ACTIVE`, `isActive = true`, `emailVerified = true`.
   - Records consent timestamp in `patient_details.consented_at = NOW()`.
   - Returns JWT authentication tokens.

---

### 6.2 Direct Public Patient Registration (Fallback to Default Tenant Hekma)

When a patient discovers Hekma independently and registers directly without an invitation from a `SITE` or `SPONSOR`:

```
+-------------------+         +---------------------------+         +-------------------------------+
| Direct Patient    |         | hekma-identity-service    |         |  Default Tenant (Hekma)       |
+---------+---------+         +-------------+-------------+         +---------------+---------------+
          |                                 |                                       |
          | POST /api/v1/auth/register      |                                       |
          | (role=PATIENT, no invite code)  |                                       |
          |-------------------------------->|                                       |
          |                                 | 1. Detect direct self-registration    |
          |                                 | 2. Fetch Default Tenant:              |
          |                                 |    findByDefaultTenantTrue()          |
          |                                 |    (UUID: ...0001, slug: default-tenant)
          |                                 | 3. Create UserEntity:                 |
          |                                 |    - role = PATIENT                   |
          |                                 |    - tenant_id = Default Tenant UUID  |
          |                                 | 4. Create PatientDetailEntity:        |
          |                                 |    - assigned_user_id = NULL          |
          |                                 |    - regulatory consents = true       |
          |                                 | 5. Register in Firebase with claims:  |
          |                                 |    { role: PATIENT, tenant_id: ... }  |
          |<--------------------------------|                                       |
          | 201 Created + OTP Challenge     |                                       |
```

1. **Endpoint**: `POST /api/v1/auth/register` with `role = Role.PATIENT` and no invitation token.
2. **Default Tenant Resolution**:
   - `AuthService` detects no invitation code was supplied.
   - Queries `tenantRepository.findByDefaultTenantTrue()` to resolve the platform's Default Organization (`00000000-0000-0000-0000-000000000001`, slug: `default-tenant`, Hekma).
3. **Database Persistence**:
   - `UserEntity`:
     - `role = Role.PATIENT`
     - **`tenant_id = defaultTenant.getId()`** (associated with Default Tenant Hekma)
     - `status = UserStatus.PENDING_VERIFICATION`
   - `PatientDetailEntity`:
     - Mandatory regulatory consents validated (`termsAccepted`, `privacyPolicyAccepted`, `healthDataConsentAccepted`).
     - **`assigned_user_id = NULL`** (placed into the unassigned default tenant patient pool; can later be claimed/assigned to a `SITE` or `SPONSOR` user upon clinical trial recruitment).
4. **Firebase Custom Claims**:
   - `{ "role": "PATIENT", "tenant_id": "00000000-0000-0000-0000-000000000001" }`.
5. **OTP Verification**:
   - Standard phone or email OTP verification challenge dispatched to finalize account verification.

---

### 6.3 Self-Registration for `SPONSOR` and `SITE` Users (`/api/v1/auth/register`)

1. **Role Restriction**: Only `SPONSOR` and `SITE` roles can register as organizational members.
2. **Tenant Resolution**:
   - Accepts `tenantId` (UUID) or `tenantSlug` (String) in the request body.
   - If not provided, defaults to `default-tenant` (`default_tenant = TRUE`).
   - Validates that the target tenant exists, is `ACTIVE`, and matches the role (e.g. `SPONSOR` inside a sponsor tenant, `SITE` inside a site tenant).
3. **Persistence & Firebase Claims**:
   - `UserEntity` persisted with `tenant_id = targetTenant.getId()`.
   - Firebase custom claims set: `{ "role": "<SPONSOR|SITE>", "tenant_id": "<UUID>" }`.

---

### 6.4 Administrative Invitation Flow (`/api/v1/system-admin/admins`)

- Root `SYSTEM_ADMIN` invites a platform operational `ADMIN` user.
- The invited `ADMIN` is created with `role = Role.ADMIN` and `tenant_id = NULL` (platform-global coordinator).
- Platform `ADMIN` users can subsequently provision `SPONSOR` or `SITE` users into specific tenants or manage unassigned patients in the Default Tenant.

---

### 6.5 Login & Token Refresh Flow (`/api/v1/auth/login` & `/api/v1/auth/refresh-token`)

- **For `SPONSOR`, `SITE`, and `PATIENT`**:
  - Checks if the user's `TenantEntity` is `ACTIVE`. If `SUSPENDED`, throws `TenantSuspendedException` (HTTP `403 Forbidden`).
  - For `PATIENT`: Evaluates conditional 2FA (`twoFactorEnabled`). If enabled, generates OTP challenge and withholds tokens until verified via `/api/v1/auth/otp/verify`.
  - Returns tenant details (`id`, `name`, `slug`, `defaultTenant`) in `LoginResponse`.
- **For `SYSTEM_ADMIN` and `ADMIN`**:
  - Authenticates without tenant status check (`tenant = null`).
  - Returns tokens immediately.

---

## 7. Tenant & Patient Management REST APIs

### 7.1 Tenant Management Endpoints (`TenantController`)

Base path: `/api/v1/tenants`  
Protected: Accessible only to `SYSTEM_ADMIN` (or read-only for `ADMIN`).

| Method | Endpoint | Authorized Roles | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/tenants` | `SYSTEM_ADMIN` | Create a new tenant (`SPONSOR` or `SITE`). `default_tenant` is always `FALSE`. |
| `GET` | `/api/v1/tenants` | `SYSTEM_ADMIN`, `ADMIN` | List all tenants with pagination, type filtering (`tenantType`), and status. |
| `GET` | `/api/v1/tenants/{tenantId}` | `SYSTEM_ADMIN`, `ADMIN` | Retrieve detailed tenant metadata, contact details, and member count. |
| `PATCH` | `/api/v1/tenants/{tenantId}/status` | `SYSTEM_ADMIN` | Update status (`ACTIVE`, `SUSPENDED`, `INACTIVE`). Default tenant cannot be suspended. |
| `PUT` | `/api/v1/tenants/{tenantId}` | `SYSTEM_ADMIN` | Update tenant profile, branding, and contact settings. |

### 7.2 Patient Invitation & Mapping Endpoints (`PatientController`)

Base path: `/api/v1/patients`

| Method | Endpoint | Authorized Roles | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/patients/invite` | `SPONSOR`, `SITE` | Create patient profile, stage `UserEntity`, map `assigned_user_id` to caller, and dispatch invitation email. |
| `POST` | `/api/v1/patients/accept-invite` | Public (Unauthenticated) | Validate invitation token, set password, record HIPAA/GDPR regulatory consents, activate user, and return JWT tokens. |
| `GET` | `/api/v1/patients` | `SPONSOR`, `SITE`, `ADMIN`, `SYSTEM_ADMIN` | List patients. `SPONSOR`/`SITE` are scoped to their tenant; supports `?assignedToMe=true` filter. `ADMIN` can view default tenant unassigned pool. |
| `GET` | `/api/v1/patients/{patientId}` | `SPONSOR`, `SITE`, `ADMIN`, `SYSTEM_ADMIN` | Retrieve detailed patient profile and consent history (scoped within caller's tenant boundary). |
| `PATCH` | `/api/v1/patients/{patientId}/assign` | `SPONSOR`, `SITE`, `ADMIN` | Reassign a patient to another `SITE`/`SPONSOR` investigator within the tenant, or assign an unassigned default-tenant patient to a site coordinator. |

---

## 8. User Management & Query Scoping

### 8.1 Administrative Hierarchy & Boundaries
- **`SYSTEM_ADMIN`**: Can query and modify all users across all roles (`ADMIN`, `SPONSOR`, `SITE`, `PATIENT`) across all tenants.
- **`ADMIN`**:
  - Can manage active/inactive status and soft deletion for `SPONSOR`, `SITE`, and `PATIENT`.
  - Can manage unassigned patients in the Default Tenant (`default-tenant`).
  - Cannot modify peer `ADMIN` users or `SYSTEM_ADMIN`.
- **`SPONSOR` / `SITE`**:
  - Strictly confined to their own tenant (`tenant_id`).
  - Cannot query or access users outside their assigned `tenant_id`.
  - Can filter patients by `assigned_user_id` to manage their assigned participant cohorts.
- **`PATIENT`**:
  - Accesses only their personal clinical profile (`/api/v1/patients/me`) and consents.

### 8.2 Scoping Invariants Matrix

| Caller Role | Target User Role | Allowed Actions | Tenant Boundary Enforced? |
| :--- | :--- | :--- | :--- |
| `SYSTEM_ADMIN` | Any Role | Full CRUD, Provisioning, Reset | No (Platform Global) |
| `ADMIN` | `SPONSOR`, `SITE`, `PATIENT` | Status update, soft delete, view | No (Platform Global, cross-tenant) |
| `SPONSOR` | `PATIENT` (same tenant) | Create profile, invite, view, update | Yes (`caller.tenantId == patient.tenantId`) |
| `SITE` | `PATIENT` (same tenant) | Create profile, invite, view, update | Yes (`caller.tenantId == patient.tenantId`) |
| `PATIENT` | Self (`PATIENT`) | Read profile, update profile, view consents | Yes (Self only) |

---

## 9. Downstream Microservice Alignment (`hekma-notification-service`)

When `hekma-identity-service` calls `hekma-notification-service`:
- **Patient Invitations**:
  - Dispatches `POST /api/v1/notifications/email` with template `PATIENT_INVITATION`.
  - Payload attributes: `inviterName`, `organizationName`, `invitationLink`, `invitationCode`, `expiresAt`.
  - Email header branding is decorated with the inviter's `tenantId` (e.g., logo, organization signature).
- **Tenant Staff Communications (`SPONSOR` / `SITE`)**:
  - Attaches `tenantId` to notification requests to apply tenant-specific branding and email sender configuration.
- **Platform Communications (`SYSTEM_ADMIN` / `ADMIN` / Default Tenant Patients)**:
  - Dispatches with `tenantId = NULL` or platform default branding (Hekma Platform).

---

## 10. Phased Implementation Roadmap

```
Phase 1: Database Migration & Tenant Entity Foundation
  ├── Flyway V9 Migration:
  │     ├── CREATE TABLE tenants (with default_tenant & partial unique index)
  │     ├── Seed Default Organization (default_tenant = TRUE, slug = default-tenant)
  │     ├── ALTER TABLE users ADD COLUMN tenant_id
  │     ├── Backfill existing SPONSOR, SITE, and PATIENT users to default-tenant
  │     ├── ADD CONSTRAINT chk_users_tenant_role:
  │     │     * SPONSOR, SITE, PATIENT -> tenant_id IS NOT NULL
  │     │     * SYSTEM_ADMIN, ADMIN -> tenant_id IS NULL
  │     └── ALTER TABLE patient_details ADD COLUMN assigned_user_id UUID REFERENCES users(id)
  └── TenantEntity, TenantStatus, TenantRepository (findByDefaultTenantTrue())

Phase 2: Administrative Bootstrap Alignment
  ├── SystemAdminInitializer (@Order 10): system.admin@hekma.com (tenant_id = NULL)
  ├── AdminInitializer (@Order 20): admin@hekma.com (tenant_id = NULL)
  └── Both auto-generate 20-character secure random passwords with Firebase password reset capability

Phase 3: Tenant Context & Request Resolution Pipeline
  ├── TenantContext (ThreadLocal with setSystemBypass)
  ├── TenantFilter: Enforce tenant context for SPONSOR, SITE, PATIENT; bypass for ADMIN & SYSTEM_ADMIN
  └── Hibernate 6 CurrentTenantIdentifierResolver connecting to @TenantId

Phase 4: Registration, Patient Invitation & Default Tenant Fallback
  ├── Patient Invitation Flow:
  │     ├── POST /api/v1/patients/invite (by SPONSOR / SITE user)
  │     ├── Generate secure token & stage UserEntity + PatientDetailEntity (assigned_user_id)
  │     └── Call hekma-notification-service with PATIENT_INVITATION email template
  ├── Patient Acceptance Flow:
  │     └── POST /api/v1/patients/accept-invite (activate user, set Firebase claims)
  ├── Direct Public Patient Registration Fallback:
  │     └── POST /api/v1/auth/register (role = PATIENT, defaults to default-tenant UUID)
  └── Organizational Registration: SPONSOR / SITE require valid tenant_id

Phase 5: Tenant Management REST API (/api/v1/tenants)
  ├── TenantController, TenantService, DTOs
  ├── CRUD endpoints with OpenAPI documentation
  └── Protect default tenant from deactivation or deletion

Phase 6: User Management, Patient Query Scoping & Assignment
  ├── Scoped UserController & UserManagementService (tenant boundary validation)
  ├── PatientController: GET /api/v1/patients (?assignedToMe=true)
  ├── PATCH /api/v1/patients/{patientId}/assign (reassign patient to SITE/SPONSOR)
  └── Unit and integration tests for tenant isolation and patient mapping

Phase 7: Downstream Integration & Regression Verification
  ├── NotificationServiceClient: pass tenantId for SPONSOR/SITE and invitation templates
  └── Full test suite verification (139+ tests passing without regressions)
```

---

## 11. Confirmed Design Choices Summary

- **Roles & Tenancy Boundary**:
  - **Organizational Staff**: Strictly restricted to `SPONSOR` and `SITE`. No tenant can employ staff with role `ADMIN`, `SYSTEM_ADMIN`, or `PATIENT`.
  - **Platform Governance**: `SYSTEM_ADMIN` (`system.admin@hekma.com`) and `ADMIN` (`admin@hekma.com`) are **platform-global roles** (`tenant_id = NULL`).
  - **Clinical Participants (`PATIENT`)**:
    - Always associated with a tenant (`tenant_id IS NOT NULL`).
    - Always mapped to a `SITE` or `SPONSOR` user when created/invited by them (`patient_details.assigned_user_id`).
    - If registered directly (public self-registration without an invite), automatically associated with the **Default Tenant (`default_tenant = TRUE`, Hekma)**.
  - Enforced at both database level (`chk_users_tenant_role`, `patient_details.assigned_user_id`) and application service layer.
- **Default Tenant**:
  - Bootstrapped via Flyway V9 with ID `00000000-0000-0000-0000-000000000001`, slug `default-tenant`, name `"Default Organization"`, and `default_tenant = TRUE`.
  - Protected from suspension or deletion.
- **Default Administrator**:
  - `admin@hekma.com` (Role: `ADMIN`, `tenant_id = NULL`), auto-bootstrapped on startup with a 20-character secure random password, resetting credentials via standard Firebase password reset flow.
- **`default_tenant` Boolean Flag**:
  - Maintained on `tenants` table with PostgreSQL partial unique index `WHERE default_tenant = TRUE`.

