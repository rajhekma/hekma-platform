# Project Context: Hekma Identity Service (`hekma-identity-service`)

## 1. Project Overview & Business Purpose

The **Hekma Identity Service** is the core identity, authentication, user authorization, and regulatory consent microservice for the **Hekma Platform** — a specialized decentralized clinical trial and digital health ecosystem.

In clinical trial environments, user identities span diverse participant profiles ranging from platform administrators and clinical trial sponsors to healthcare site investigators and clinical trial participants (patients). Each profile carries strict regulatory, privacy, and auditing mandates:
- **HIPAA & GDPR / Health Data Protection**: Clinical trials demand verifiable consent records, explicit tracking of terms and conditions, privacy policy consents, and health data usage authorization with immutable timestamps.
- **Identity Provider (IdP) Decoupling**: Centralized credential management and token issuance are handled via **Google Firebase Authentication**, while rich domain metadata, administrative hierarchies, clinical relationships, and verification histories reside in **PostgreSQL**.
- **Auditability**: Every entity modification maintains full audit records (`createdAt`, `updatedAt`, `createdBy`, `updatedBy`, `version`), and security-critical events (OTP generation, failure, lockout) are logged in dedicated audit tables.

---

## 2. Core Business Requirements & Capabilities

### 2.1 Role-Based Access Control (RBAC) Hierarchy

The platform defines five discrete roles within [Role.java](file:///D:/coding/hekma/hekma-identity-service/src/main/java/com/hekma/identity/domain/Role.java):

```
       +-----------------------+
       |     SYSTEM_ADMIN      |  (Root superuser, auto-bootstrapped, immutable)
       +-----------+-----------+
                   |
                   v
       +-----------------------+
       |         ADMIN         |  (Invited by SYSTEM_ADMIN, platform coordinator)
       +-----------+-----------+
                   |
       +-----------+-----------+
       |           |           |
       v           v           v
  +---------+  +--------+  +---------+
  | SPONSOR |  |  SITE  |  | PATIENT |  (Publicly registerable)
  +---------+  +--------+  +---------+
```

1. **`SYSTEM_ADMIN`**:
   - The root governance role.
   - Automatically bootstrapped on application startup via [SystemAdminInitializer.java](file:///D:/coding/hekma/hekma-identity-service/src/main/java/com/hekma/identity/config/SystemAdminInitializer.java).
   - Generates a cryptographically strong 20-character random password; never stored in plaintext configuration.
   - Only role authorized to invite or create `ADMIN` users.
   - Protected: Cannot be modified, deactivated, or deleted by any API operator.
2. **`ADMIN`**:
   - Platform operational administrators (e.g., clinical trial operations coordinators).
   - Can manage and modify active status / soft-deletion for operational roles below them (`SPONSOR`, `SITE`, `PATIENT`).
   - Strictly forbidden from modifying or deactivating other `ADMIN` users or `SYSTEM_ADMIN`.
3. **`SPONSOR`**:
   - Pharmaceutical companies or trial sponsor organizations. Tenant role: an organization registers itself (`POST /api/v1/auth/register-tenant`) or is created as a sub-tenant; users see their tenant and its sub-tenants.
4. **`SITE`**:
   - Clinical sites, trial hospitals, principal investigators, and site study coordinators. Tenant role: an organization registers itself or is created as a sub-tenant (e.g. a site under a sponsor); users see their tenant and its sub-tenants.
5. **`PATIENT`**:
   - Clinical trial participants. The only role allowed for public self-registration (phone or email verification); joins the default tenant Hekma unless registering with an invitation code.
   - Associated with [PatientDetailEntity.java](file:///D:/coding/hekma/hekma-identity-service/src/main/java/com/hekma/identity/domain/PatientDetailEntity.java) for regulatory consent tracking.
   - Supports conditional Two-Factor Authentication (2FA) via OTP.

### 2.2 Patient Onboarding & Regulatory Consent Tracking

For clinical research compliance, patient registration requires explicit regulatory consents stored in `patient_details`:
- `termsAccepted` (`BOOLEAN`): Acceptance of platform terms of service.
- `privacyPolicyAccepted` (`BOOLEAN`): Acceptance of privacy policy.
- `healthDataConsentAccepted` (`BOOLEAN`): Regulatory consent to process and share protected health information for trial purposes.
- `consentedAt` (`TIMESTAMP WITH TIME ZONE`): Precise UTC timestamp of consent execution.
- Optional linkage: `invitationCode` for site/trial study recruitment attribution.

### 2.3 Multi-Mode OTP Engine & Rate-Limiting Protection

The OTP authentication subsystem ([OtpService.java](file:///D:/coding/hekma/hekma-identity-service/src/main/java/com/hekma/identity/service/OtpService.java)) provides secure verification:
- **Modes**: Supported over `PHONE` (SMS) and `EMAIL`.
- **OTP Properties**: 6-digit numeric code (`000000` - `999999`), BCrypt-hashed in database, plain text never stored.
- **Validity Window**: 5 minutes per OTP code.
- **Verification Attempts**: Maximum 5 attempts per attempt ID. Exceeding 5 attempts sets status to `INVALIDATED`.
- **Resend Policy**: Maximum 3 resends per attempt ID. Each resend regenerates a code, resets attempts, and extends validity by 5 minutes.
- **Rate Limiting**: Maximum 5 OTP requests per hour per phone number or email address.
- **Lockout Policy**: If the hourly threshold is reached, an automatic 30-minute lockout is triggered in `otp_lockouts`, rejecting requests with HTTP `429 Too Many Requests`.
- **Auditing**: Every lifecycle event (`GENERATION`, `RESEND`, `VERIFICATION_SUCCESS`, `VERIFICATION_FAILURE`, `EXPIRATION`, `LOCKOUT`) is logged in `otp_audit_logs`.

### 2.4 User Lifecycle & Soft Deletion

User records transition across specific statuses ([UserStatus.java](file:///D:/coding/hekma/hekma-identity-service/src/main/java/com/hekma/identity/domain/UserStatus.java)):
- `PENDING_VERIFICATION`: Initial state upon public self-registration awaiting OTP verification. `isActive = false`.
- `ACTIVE`: Fully verified and active account. Permitted to authenticate and refresh tokens.
- `INACTIVE`: Administratively deactivated account. Login and token refresh blocked (`403 Forbidden`).
- `SUSPENDED`: Administratively suspended account.
- **Soft Deletion**: When soft-deleted via `DELETE /api/v1/users/{userId}`, `isDeleted` is set to `true`, `isActive` to `false`, and `status` to `INACTIVE`. Hibernate `@SQLRestriction("is_deleted = false")` on [UserEntity.java](file:///D:/coding/hekma/hekma-identity-service/src/main/java/com/hekma/identity/domain/UserEntity.java) ensures soft-deleted users are automatically excluded from all standard JPA queries and foreign key lookups.

---

## 3. Services, Modules & Boundaries

| Module / Component | Package | Primary Responsibility |
| :--- | :--- | :--- |
| **Authentication Service** | `com.hekma.identity.service.AuthService` | Public registration, login credential validation, Firebase dual-write, compensating rollbacks, token refresh, system admin bootstrap |
| **OTP Service** | `com.hekma.identity.service.OtpService` | OTP generation, BCrypt hashing, SMS/Email dispatch coordination, rate limiting, lockout enforcement, attempt tracking, audit logging |
| **User Management Service** | `com.hekma.identity.service.UserManagementService` | Administrative status modifications (`isActive`), role hierarchy checks, soft-deletion, 2FA settings management |
| **User Query Service** | `com.hekma.identity.service.UserQueryService` | Read-only administrative querying, role filtering, pagination/ordering, GraphQL batch resolution for patient details |
| **Firebase Integration** | `com.hekma.identity.firebase.*` | Firebase Admin SDK integration, custom claims assignment (`role`), custom token issuance, Google STS token refresh, mock fallback |
| **Notification Integration** | `com.hekma.identity.notification.NotificationServiceClient` | Outbound HTTP REST client dispatching SMS OTP, Email OTP, and Welcome notifications to `hekma-notification-service` |
| **REST Controllers** | `com.hekma.identity.controller.*` | `AuthController`, `SystemAdminController`, `UserController`, `OtpController` exposing OpenAPI-documented REST APIs |
| **GraphQL Controller** | `com.hekma.identity.controller.UserGraphQlController` | Exposing queries and mutations for administrative user exploration |

---

## 4. Key Business Rules & Invariants

1. **Self-Registration Restrictions**:
   - Allowed: `SPONSOR`, `SITE`, `PATIENT`.
   - Forbidden: `SYSTEM_ADMIN` and `ADMIN`. Any attempt returns `400 Bad Request`.
2. **Dual-Write Consistency (Compensating Transactions)**:
   - When a user is registered, Firebase Auth is written first.
   - If PostgreSQL persistence fails, the Firebase user is immediately deleted.
   - If initial registration OTP dispatch fails, both PostgreSQL user and Firebase user are rolled back.
3. **Login & Conditional 2FA Invariant**:
   - `PATIENT` with `twoFactorEnabled == true`: Direct login is withheld; OTP is dispatched; returns `twoFactorRequired = true` and `otpAttemptId`. Authentication tokens (`idToken`, `refreshToken`) are only issued after successful OTP verification via `/api/v1/auth/otp/verify`.
   - `PATIENT` with `twoFactorEnabled == false`: Direct login granted (`twoFactorRequired = false`), returns tokens immediately.
   - Operational/Admin roles (`SYSTEM_ADMIN`, `ADMIN`, `SPONSOR`, `SITE`): Direct login granted immediately (`twoFactorRequired = false`).
4. **Administrative Hierarchy Invariant**:
   - `SYSTEM_ADMIN` is immutable and cannot be deactivated or deleted.
   - `ADMIN` cannot modify, deactivate, or delete another `ADMIN` or `SYSTEM_ADMIN`.
   - Non-admin roles cannot perform any user management operations.

---

## 5. Current Development Status & Known Limitations

- **Current Status**: All core authentication, OTP verification, admin delegation, status management, GraphQL queries, and OpenAPI documentation are fully implemented with **139 passing unit and integration tests**.
- **Known Limitations / Future Work**:
  - **Stateless JWT Security Filter**: `SecurityConfig` currently permits all `/api/v1/**` and `/graphql` paths in local/dev profiles. Token validation logic is centralized in services (e.g., verifying user status on refresh/login), but global Bearer JWT token interception via Spring Security filter remains to be finalized for API gateway or microservice isolation.
  - **Phone OTP in Dev Mode**: For development convenience, phone OTPs are printed to standard output (`System.out.println` and SLF4J logs) instead of invoking SMS gateways directly. Email OTPs and welcome events are dispatched to `hekma-notification-service`.
