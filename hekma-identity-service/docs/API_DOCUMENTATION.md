# API Documentation: Hekma Identity Service (`hekma-identity-service`)

## 1. API Design Conventions & Protocols

The **Hekma Identity Service** provides dual API interfaces:
1. **REST API (`/api/v1/*`)**: Designed for transactional operations, account registration, credential authentication, OTP generation, and administrative state modifications.
2. **GraphQL API (`/graphql`)**: Designed for administrative user search, multi-attribute filtering, and batch field loading (`patientDetails`).

### 1.1 HTTP Status Codes
- `200 OK`: Request succeeded. Returned on successful login, token refresh, OTP operations, and profile updates.
- `201 Created`: Resource successfully created. Returned on user registration and admin invitation.
- `400 Bad Request`: Input validation failed, malformed JSON, or unauthorized registration role.
- `401 Unauthorized`: Authentication failed, invalid password, invalid/expired OTP, or missing user account.
- `403 Forbidden`: Account is inactive/suspended, or operation violates administrative role hierarchy.
- `404 Not Found`: Target user or resource does not exist (or has been soft-deleted).
- `409 Conflict`: Unique constraint violation (email or phone number already registered).
- `429 Too Many Requests`: Rate limit exceeded (OTP hourly quota reached or lockout active).
- `502 Bad Gateway`: Upstream communication failure with Google Firebase or notification services.

### 1.2 Authentication & Authorization
- Every endpoint requires `Authorization: Bearer <Firebase ID token>` **except** these public operations (all `POST`):
  `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/refresh-token`, `/api/v1/auth/forgot-password`,
  `/api/v1/auth/reset-password`, `/api/v1/auth/register-tenant`, `/api/v1/auth/otp/send`, `/api/v1/auth/otp/verify`, `/api/v1/auth/otp/resend`,
  `/api/v1/patients/accept-invite`, `/api/v1/users/accept-invite`. Swagger/OpenAPI and GraphiQL are public only when enabled by configuration.
- ID tokens are obtained from `login`, `otp/verify` (for registered users) or `refresh-token`. The token is verified with the
  Firebase Admin SDK (signature, expiry, revocation) on every request.
- The caller's identity, role and tenant are loaded from PostgreSQL. Client-supplied identity is ignored: the former
  `X-Operator-Id` header and `operatorId` fields no longer exist, and `X-Tenant-ID` cannot select another tenant for tenant users.
- `401` = missing/invalid/revoked token; `403` = role not permitted or account/tenant inactive; resources outside the
  caller's scope return `404`.

### 1.3 Roles & Authorities (RBAC Phase 3)
Five fixed roles: `SYSTEM_ADMIN` (single root), `ADMIN`, `SPONSOR`, `SITE`, `PATIENT`. SPONSOR/SITE users additionally hold **per-user authorities**, always evaluated within their tenant subtree. Platform administrators hold every authority implicitly; patients hold none and act only on themselves. A tenant's first user (registration owner, sub-tenant owner) receives all twelve; invited users receive `tenant:read`, `patient:read`, `patient:create` by default (capped by the inviter's own). Authorities are read from the database on every request, so a revocation applies immediately.

| Authority | Grants |
| :--- | :--- |
| `tenant:read` | View own tenant and descendant tenants |
| `tenant:update` | Edit profile/settings of own or descendant tenants |
| `subtenant:create` | Create sub-tenants under own or descendant tenants |
| `subtenant:manage` | Suspend/activate descendant tenants (never own) |
| `user:read` | View users in own and descendant tenants |
| `user:invite` | Invite SPONSOR/SITE users into own and descendant tenants |
| `user:manage` | Activate/deactivate/soft-delete users in own and descendant tenants (never self) |
| `authority:assign` | Grant/revoke authorities, never beyond one's own, never to self |
| `patient:create` | Create and invite patient profiles |
| `patient:read` | View patients in own and descendant tenants |
| `patient:update` | Update patient profile data |
| `patient:assign` | Reassign patients within own subtree |
| `role:read` | View custom roles in own or ancestor tenants |
| `role:create` | Create custom roles within own tenant subtree |
| `role:update` | Modify custom role details and authority bundles |
| `role:delete` | Delete custom roles in own tenant (rejected if assigned to active users) |
| `role:assign` | Assign custom roles to users in own or descendant tenants |

Endpoints return `403` when the caller lacks the required authority and `404` when the target is outside the caller's subtree.

### 1.4 Standardized Error Response (`ApiErrorResponse`)
All REST API error responses adhere to the following schema:
```json
{
  "status": 400,
  "error": "Bad Request",
  "message": "Validation failed for input data",
  "details": [
    "email: must be a well-formed email address",
    "password: Password must be at least 8 characters long"
  ],
  "timestamp": "2026-10-01T12:00:00Z",
  "traceId": "c8b4172f-f442-43ce-9a3b-c2e82506e938"
}
```

### 1.5 Distributed Tracing Headers & Body Correlation
Every HTTP request to any Hekma backend service participates in distributed tracing:
- **Incoming**: The service accepts `X-Trace-Id`, `trace-id`, or `X-Request-Id` headers from callers/gateways. If omitted, a fresh UUID is generated.
- **Outgoing Headers**: Every response (successful `2xx`, client error `4xx`, or server failure `5xx`) includes both:
  - `X-Trace-Id: <trace-id>`
  - `trace-id: <trace-id>`
- **CORS Support**: Both `X-Trace-Id` and `trace-id` are exposed via `Access-Control-Expose-Headers`.
- **Response Bodies**:
  - **Positive Responses (2xx)**: JSON responses automatically include the single `"traceId"` property alongside payload fields.
  - **Error Responses (4xx/5xx)**: All error payloads (`ApiErrorResponse` and security rejections) include the single `"traceId"` property.
- **Logs**: Every server log line includes `[traceId=<trace-id>]` via SLF4J MDC.
- **Inter-Service Calls**: Outbound REST calls to downstream services propagate `X-Trace-Id` and `trace-id`.

---

## 2. REST Endpoints: Authentication (`/api/v1/auth`)

### 2.1 Public Self-Registration
- **Endpoint**: `POST /api/v1/auth/register`
- **Description**: Creates a user account in Firebase Auth, assigns custom claim `role`, persists profile in PostgreSQL with status `PENDING_VERIFICATION`, and initiates OTP dispatch.
- **Allowed Roles**: `PATIENT` only. Every other role returns `400 Bad Request`. SPONSOR/SITE owners register through `POST /api/v1/auth/register-tenant`; further SPONSOR/SITE users are created as sub-tenant owners (section 5) or, in Phase 3, by invitation.
- **Request Body**:
  ```json
  {
    "email": "alice@example.com",
    "phoneNumber": "+1234567890",
    "password": "SecurePassword123!",
    "displayName": "Alice Smith",
    "role": "PATIENT",
    "verificationMode": "PHONE",
    "invitationCode": null
  }
  ```
  *(Note: Patients join the default tenant (`default-tenant`, Hekma), or the inviting tenant when a valid `invitationCode` is supplied. Phone-only registrations receive an internal Firebase login email so that the password can be validated by Firebase.)*
- **Response `201 Created`**:
  ```json
  {
    "id": "7b08d4ee-5a67-4ebc-88eb-568ebbaeecc6",
    "firebaseUid": "fb-uid-987654321",
    "email": "alice@example.com",
    "phoneNumber": "+1234567890",
    "role": "PATIENT",
    "displayName": "Alice Smith",
    "status": "PENDING_VERIFICATION",
    "phoneVerified": false,
    "emailVerified": false,
    "twoFactorEnabled": false,
    "verificationMode": "PHONE",
    "otpAttemptId": "d309c1b4-8de9-44f5-bcaf-f2d1f45b56ac",
    "otpExpiresInSeconds": 300,
    "createdAt": "2026-10-01T12:00:00Z",
    "tenantId": "00000000-0000-0000-0000-000000000001",
    "tenantSlug": "default-tenant",
    "message": "User registered successfully. An OTP has been generated for phone verification."
  }
  ```

### 2.2 User Login & Conditional 2FA
- **Endpoint**: `POST /api/v1/auth/login`
- **Description**: Authenticates email/phone and password against Firebase.
  - If user is `PATIENT` with `twoFactorEnabled = true`: Withholds tokens, generates OTP, returns `twoFactorRequired: true` and `otpAttemptId`.
  - Otherwise: Issues Firebase JWT ID token and refresh token directly.
- **Request Body**:
  ```json
  {
    "email": "dr.watson@hospital.org",
    "password": "SecurePassword123!"
  }
  ```
- **Response `200 OK` (Direct Login)**:
  ```json
  {
    "twoFactorRequired": false,
    "twoFactorEnabled": false,
    "idToken": "eyJhbGciOiJSUzI1NiIs...",
    "refreshToken": "AMf-vBx...",
    "tokenType": "Bearer",
    "expiresIn": 3600,
    "userId": "7b08d4ee-5a67-4ebc-88eb-568ebbaeecc6",
    "firebaseUid": "fb-uid-987654321",
    "email": "dr.watson@hospital.org",
    "displayName": "Dr. Emily Watson",
    "role": "SITE",
    "status": "ACTIVE",
    "phoneVerified": true,
    "emailVerified": true,
    "message": "Login successful."
  }
  ```
- **Response `200 OK` (2FA Challenge - PATIENT with 2FA Enabled)**:
  ```json
  {
    "twoFactorRequired": true,
    "twoFactorEnabled": true,
    "otpAttemptId": "550e8400-e29b-41d4-a716-446655440000",
    "otpExpiresInSeconds": 300,
    "verificationMode": "PHONE",
    "userId": "3c82d4ee-5a67-4ebc-88eb-118ebbaee999",
    "phoneNumber": "+1234567890",
    "role": "PATIENT",
    "displayName": "Alice Smith",
    "status": "ACTIVE",
    "message": "Two-factor authentication required. An OTP has been sent to your registered phone number for verification."
  }
  ```

### 2.3 Token Refresh
- **Endpoint**: `POST /api/v1/auth/refresh-token`
- **Description**: Exchanges an OAuth2 refresh token for a new Firebase ID token via Google STS. Confirms user exists and is `ACTIVE` in PostgreSQL.
- **Request Body**:
  ```json
  {
    "refreshToken": "AMf-vBx..."
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "idToken": "eyJhbGciOiJSUzI1NiIs...",
    "refreshToken": "AMf-vBx...",
    "tokenType": "Bearer",
    "expiresIn": 3600,
    "firebaseUid": "fb-uid-987654321",
    "email": "dr.watson@hospital.org",
    "role": "SITE",
    "displayName": "Dr. Emily Watson",
    "status": "ACTIVE"
  }
  ```

### 2.4 Initiate Password Reset
- **Endpoint**: `POST /api/v1/auth/forgot-password`
- **Description**: Generates and dispatches a 6-digit `PASSWORD_RESET` OTP to the registered email or phone number. The response is identical whether or not the account exists.
- **Request Body**:
  ```json
  {
    "identifier": "admin@hekma.ai"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "message": "If an account matches this identifier, a password reset code has been dispatched.",
    "status": "DISPATCHED"
  }
  ```

### 2.5 Confirm Password Reset
- **Endpoint**: `POST /api/v1/auth/reset-password`
- **Description**: Verifies `otpCode` against the latest pending `PASSWORD_RESET` OTP (5-minute expiry, max 5 attempts), updates the password in Firebase Auth and revokes all existing sessions. An invalid code or unknown identifier returns `400` without changing the password.
- **Request Body**:
  ```json
  {
    "identifier": "admin@hekma.ai",
    "otpCode": "123456",
    "newPassword": "NewSecurePassword123!"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "message": "Password successfully updated.",
    "status": "SUCCESS"
  }
  ```

### 2.6 Change Password (authenticated)
- **Endpoint**: `POST /api/v1/auth/change-password` — requires `Authorization: Bearer <idToken>`.
- **Description**: Validates `currentPassword` through Firebase (via this API), stores `newPassword` in Firebase with the Admin SDK, revokes all existing sessions and returns a fresh session.
- **Request Body**:
  ```json
  {
    "currentPassword": "OldSecurePassword123!",
    "newPassword": "NewSecurePassword123!"
  }
  ```
- **Response `200 OK`**: `{ "idToken": "...", "refreshToken": "...", "tokenType": "Bearer", "expiresIn": 3600, "message": "Password changed successfully. Other sessions have been signed out." }`
- **Errors**: `400` policy violation or new password equal to current; `401` not authenticated or wrong current password.

### 2.7 Register Organization (Tenant Self-Registration, public)
- **Endpoint**: `POST /api/v1/auth/register-tenant`
- **Description**: Creates a new **top-level** `SPONSOR` or `SITE` tenant together with its owner user (role = tenant type) and sends a verification OTP. Tenant and owner are `PENDING_VERIFICATION` until `POST /api/v1/auth/otp/verify` succeeds, which activates both and returns tokens. Firebase is rolled back if any step fails. Joining an existing tenant is not possible through registration.
- **Request Body**:
  ```json
  {
    "tenantName": "Mayo Clinic Research",
    "tenantSlug": "mayo-clinic",
    "tenantType": "SITE",
    "email": "owner@mayo.edu",
    "phoneNumber": "+15551234567",
    "password": "SecurePassword123!",
    "displayName": "Dr. Emily Watson",
    "verificationMode": "EMAIL"
  }
  ```
- **Response `201 Created`**: `tenantId`, `tenantSlug`, `tenantType`, `tenantStatus: PENDING_VERIFICATION`, `userId`, `role`, `status: PENDING_VERIFICATION`, `otpAttemptId`, `otpExpiresInSeconds`.
- **Errors**: `400` invalid type (`GENERAL`), taken slug, password policy; `409` email/phone already registered.

### 2.8 Password Policy
All endpoints that set a password (`register`, `system-admin/admins`, `patients/accept-invite`, `reset-password`, `change-password`) enforce `@StrongPassword`: 8–128 characters, at least one uppercase, lowercase, digit and special character, no leading/trailing spaces. Passwords are stored only in Firebase; every password check goes through this API.

---

## 3. REST Endpoints: OTP Engine (`/api/v1/auth/otp`)

### 3.1 Send OTP
- **Endpoint**: `POST /api/v1/auth/otp/send`
- **Description**: Generates 6-digit numeric OTP valid for 5 minutes. Enforces max 5 OTPs/hour rate limit and 30-min lockout.
- **Request Body**:
  ```json
  {
    "phoneNumber": "+1234567890",
    "email": "patient@example.com",
    "verificationMode": "PHONE",
    "purpose": "LOGIN"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "attemptId": "297cc5f6-8726-4771-942f-4e3efa93685c",
    "phoneNumber": "+1234567890",
    "email": "patient@example.com",
    "verificationMode": "PHONE",
    "expiresInSeconds": 300,
    "message": "OTP generated (printed to console for dev testing)."
  }
  ```

### 3.2 Resend OTP
- **Endpoint**: `POST /api/v1/auth/otp/resend`
- **Description**: Resends OTP for active attempt or initiates a fresh OTP if requested via email/phone/userId. Maximum 3 resends allowed per attempt.
- **Request Body**:
  ```json
  {
    "attemptId": "297cc5f6-8726-4771-942f-4e3efa93685c",
    "userId": "7b08d4ee-5a67-4ebc-88eb-568ebbaeecc6",
    "phoneNumber": "+1234567890",
    "email": "user@example.com"
  }
  ```
  *(Note: `attemptId` is optional if `userId`, `phoneNumber`, or `email` is provided for lookup).*
- **Response `200 OK`**:
  ```json
  {
    "attemptId": "297cc5f6-8726-4771-942f-4e3efa93685c",
    "phoneNumber": "+1234567890",
    "resendCount": 1,
    "resendsRemaining": 2,
    "expiresInSeconds": 300,
    "message": "OTP has been resent (printed to console for dev testing)."
  }
  ```

### 3.3 Verify OTP
- **Endpoint**: `POST /api/v1/auth/otp/verify`
- **Description**: Validates OTP code (max 5 attempts). Activates `PENDING_VERIFICATION` accounts to `ACTIVE`, sets verification flags, and for registered users returns a Firebase ID token + refresh token (plus the legacy `firebaseCustomToken`). Supports fallback lookup by `userId`, `email`, or `phoneNumber` if `attemptId` is missing or refers to a user identifier.
- **Request Body**:
  ```json
  {
    "attemptId": "297cc5f6-8726-4771-942f-4e3efa93685c",
    "userId": "7b08d4ee-5a67-4ebc-88eb-568ebbaeecc6",
    "phoneNumber": "+1234567890",
    "email": "patient@example.com",
    "otpCode": "386027",
    "purpose": "REGISTRATION"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "verified": true,
    "attemptId": "297cc5f6-8726-4771-942f-4e3efa93685c",
    "phoneNumber": "+1234567890",
    "email": "patient@example.com",
    "phoneVerified": true,
    "emailVerified": false,
    "twoFactorEnabled": false,
    "verificationMode": "PHONE",
    "firebaseCustomToken": "mock-custom-token-fb-uid-12345",
    "idToken": "eyJhbGciOiJSUzI1NiIs...",
    "refreshToken": "AMf-vBx...",
    "tokenType": "Bearer",
    "expiresIn": 3600,
    "userId": "3c82d4ee-5a67-4ebc-88eb-118ebbaee999",
    "firebaseUid": "fb-uid-12345",
    "role": "PATIENT",
    "displayName": "Alice Smith",
    "message": "OTP verified successfully. Account activated."
  }
  ```

---

## 4. REST Endpoints: System Administration & User Management

### 4.1 Invite Admin (`SYSTEM_ADMIN` only)
- **Endpoint**: `POST /api/v1/system-admin/admins` (legacy alias: `POST /api/v1/system-admin/invite-admin`)
- **Authorized Role**: `SYSTEM_ADMIN` (any other caller receives `403`).
- **Description**: Creates an `ADMIN` user with custom claim `role: ADMIN` in Firebase and persists in PostgreSQL.
- **Request Body**:
  ```json
  {
    "email": "operations.admin@hekma.com",
    "temporaryPassword": "TempPassword123!",
    "displayName": "Operations Coordinator"
  }
  ```
- **Response `201 Created`**:
  ```json
  {
    "id": "b9281a02-5e4c-47bc-9177-3e4e94119d50",
    "firebaseUid": "fb-admin-998877",
    "email": "operations.admin@hekma.com",
    "role": "ADMIN",
    "displayName": "Operations Coordinator",
    "status": "ACTIVE",
    "createdAt": "2026-10-01T12:00:00Z",
    "message": "Admin user invited successfully."
  }
  ```

### 4.2 Update User Active Status
- **Endpoint**: `PATCH /api/v1/users/{userId}/status`
- **Authorized**: callers holding `user:manage` — `SYSTEM_ADMIN` (manages `ADMIN`, `SPONSOR`, `SITE`, `PATIENT`), `ADMIN` (manages `SPONSOR`, `SITE`, `PATIENT`), SPONSOR/SITE users (manage `SPONSOR`, `SITE`, `PATIENT` users of their subtree; others `404`). The operator is the authenticated caller; nobody can change their own status and `SYSTEM_ADMIN` cannot be modified. Deactivation revokes the target's sessions.
- **Request Body**:
  ```json
  {
    "isActive": false,
    "reason": "Administrative compliance review"
  }
  ```

### 4.3 Update Two-Factor Authentication (2FA)
- **Endpoint**: `PATCH /api/v1/users/{userId}/2fa`
- **Authorized**: the user itself, `SYSTEM_ADMIN`, `ADMIN` (others receive `404`).
- **Request Body**:
  ```json
  {
    "twoFactorEnabled": true
  }
  ```

### 4.4 Soft-Delete User
- **Endpoint**: `DELETE /api/v1/users/{userId}`
- **Authorized Roles**: same hierarchy as 4.2. Soft deletion revokes the target's sessions.

### 4.5 Get User Profile by ID
- **Endpoint**: `GET /api/v1/users/{userId}`
- **Scoping**: the user itself; `SYSTEM_ADMIN`/`ADMIN`; `SPONSOR`/`SITE` holding `user:read` for users of their subtree. Others receive `404`.

### 4.6 List Users in Scope
- **Endpoint**: `GET /api/v1/users?role=&page=&size=` — requires `user:read`. Platform admins see every user; SPONSOR/SITE users see users of their tenant subtree.

### 4.7 Invite a SPONSOR/SITE User
- **Endpoint**: `POST /api/v1/users/invite` — requires `user:invite`.
- **Request Body**: `{ "email": "coordinator@mayo.edu", "tenantId": "<own tenant or sub-tenant>", "authorities": ["tenant:read", "patient:read"] }` (`authorities` optional).
- **Behaviour**: The invitee's role equals the tenant's type. Requested authorities must all be held by the inviter (`403` otherwise); without a list the default bundle capped by the inviter's authorities is used. A random single-use token (72 hours, stored only as a SHA-256 hash) is emailed as `https://app.hekma.com/invitations/accept?token=…`. Tenants outside the inviter's subtree return `404`; existing emails `409`.
- **Response `201`**: `invitationId`, `email`, `role`, `tenantId`, `tenantSlug`, `authorities`, `expiresAt`.

### 4.8 Accept a Staff Invitation (public)
- **Endpoint**: `POST /api/v1/users/accept-invite`
- **Request Body**: `{ "token": "…", "password": "SecurePassword123!", "displayName": "Dr. Emily Watson", "phoneNumber": "+15551234567" }`
- **Behaviour**: Creates the Firebase account and an `ACTIVE` user in the invitation's tenant, grants the invitation's authorities and marks the token used. Used, expired or unknown tokens return `400`. Response `201` with the `UserResponse`.

### 4.9 View / Replace a User's Authorities
- **Endpoints**: `GET /api/v1/users/{userId}/authorities` (self, platform admins, or `user:read` within subtree) and `PUT /api/v1/users/{userId}/authorities` (requires `authority:assign`).
- **PUT Body**: `{ "authorities": ["tenant:read", "patient:read"], "reason": "Promoted to coordinator" }` — the complete new set.
- **Rules**: target must be a SPONSOR/SITE user in the caller's subtree (`404` otherwise); no self-change (`403`); every added or removed authority must be held by the caller (`403`); unknown keys `400`. Changes are written to the audit log with before/after values.

### 4.10 Current User (`/api/v1/me`)
- `GET /api/v1/me` — profile, role, tenant (`tenantId`, `tenantName`, `tenantSlug`, `tenantType`, `tenantPath`) and effective `authorities`.
- `GET /api/v1/me/authorities` — `{ "userId": "…", "authorities": ["patient:read", …] }`. Clients should render menus from this list; the server still enforces every rule.

### 4.11 Authorities Catalogue (`GET /api/v1/authorities`)
- **Endpoint**: `GET /api/v1/authorities`
- **Authorized**: Any authenticated user.
- **Description**: Returns all 12 platform authorities with display name, functional category (*Tenant Governance*, *User Management*, *Clinical & Patients*), description, and allowed roles.
- **Response `200 OK`**:
  ```json
  [
    {
      "key": "tenant:read",
      "name": "View Tenant Hierarchy",
      "category": "Tenant Governance",
      "description": "View own tenant and descendant tenants",
      "allowedRoles": ["ADMIN", "SPONSOR", "SITE"]
    }
  ]
  ```

### 4.12 Role Authorities Management (`SYSTEM_ADMIN` only)
- **Authority Catalogue**: `GET /api/v1/system-admin/authorities`
  - Returns complete catalogue of authorities with metadata and functional categories.
- **All Role Authority Mappings**: `GET /api/v1/system-admin/roles/authorities`
  - Returns default authorities configured for each manageable role (`ADMIN`, `SPONSOR`, `SITE`).
  - Response `200 OK`:
    ```json
    [
      { "role": "ADMIN", "authorities": ["tenant:read", "..."], "totalAuthorities": 12 },
      { "role": "SPONSOR", "authorities": ["tenant:read", "..."], "totalAuthorities": 12 },
      { "role": "SITE", "authorities": ["tenant:read", "..."], "totalAuthorities": 12 }
    ]
    ```
- **Single Role Authorities**: `GET /api/v1/system-admin/roles/{role}/authorities`
  - Returns default authorities for target role.
- **Update Role Authorities**: `PUT /api/v1/system-admin/roles/{role}/authorities`
  - Target role must be `ADMIN`, `SPONSOR`, or `SITE` (`SYSTEM_ADMIN` is immutable root, `PATIENT` is restricted to patient self-service; both return `400`).
  - **Request Body**:
    ```json
    {
      "authorities": ["tenant:read", "user:read", "patient:read"],
      "applyToExistingUsers": true,
      "reason": "Updated SITE baseline permissions per compliance review"
    }
    ```
  - **Cascade Behavior**:
    - `applyToExistingUsers = false`: Updates the role's default template in `identity_role_authorities` for newly registered/invited users only. Existing users retain their individual authority grants.
    - `applyToExistingUsers = true`: Updates `identity_role_authorities` AND immediately overwrites `identity_user_authorities` for all active, non-deleted users with that role in PostgreSQL.
  - Privileged changes are logged to `identity_authz_audit_log` with action `ROLE_AUTHORITIES_CHANGED`.
  - Response `200 OK`: `RoleAuthoritiesResponse`.

---

## 5. REST Endpoints: Tenant Hierarchy (`/api/v1/tenants`)

Tenants form a tree: any SPONSOR or SITE tenant can have sub-tenants of any type at any depth. `SYSTEM_ADMIN`/`ADMIN` see and manage every tenant; `SPONSOR`/`SITE` users see and manage their own tenant and all of its descendants (other tenants return `404`). Top-level tenants are created only by self-registration (`POST /api/v1/auth/register-tenant`, section 2.7). Suspending or deactivating a tenant blocks every user in its subtree. The default tenant (Hekma) cannot be suspended and cannot have sub-tenants.

| Method & URL | Allowed | Behaviour |
| :--- | :--- | :--- |
| `POST /api/v1/tenants/{tenantId}/sub-tenants` | `subtenant:create`, within subtree | Creates a `SPONSOR`/`SITE` sub-tenant (status `ACTIVE`) with an optional owner whose role equals the sub-tenant type. `201` |
| `GET /api/v1/tenants` | `tenant:read` (admins: all; staff: own subtree) | Paged list; `?type=`, `?status=`, `?page=`, `?size=` |
| `GET /api/v1/tenants/{tenantId}` | Any authenticated user: own tenant always; other tenants of the subtree need `tenant:read` | Tenant details incl. `parentTenantId`, `path`, `depth`, `memberCount` |
| `GET /api/v1/tenants/{tenantId}/children` | `tenant:read`, within subtree | Direct sub-tenants |
| `GET /api/v1/tenants/slug/{slug}` | Platform admins | Tenant by slug |
| `PUT /api/v1/tenants/{tenantId}` | `tenant:update`, within subtree | Update name, tier, contacts, settings |
| `PATCH /api/v1/tenants/{tenantId}/status` | `subtenant:manage`; staff only for strict descendants | `ACTIVE`, `SUSPENDED`, `INACTIVE` (`PENDING_VERIFICATION` is set only by registration) |

### 5.1 Create Sub-Tenant — request
```json
{
  "name": "Mayo Clinic Rochester Site",
  "slug": "mayo-rochester",
  "tenantType": "SITE",
  "contactEmail": "admin@mayo.edu",
  "owner": {
    "email": "coordinator@mayo.edu",
    "displayName": "Dr. Emily Watson",
    "phoneNumber": "+15551234567",
    "temporaryPassword": "TempPassword123!"
  }
}
```
Response `201`: `TenantResponse` with `parentTenantId`, `path` (`/<root-id>/<child-id>/`), `depth`, `status: ACTIVE`, `memberCount`. The owner receives all twelve authorities, signs in with the temporary password and should call `POST /api/v1/auth/change-password`.

> Access is governed by authorities (section 1.3). Platform administrators hold all of them.

---

## 6. REST Endpoints: Patient Recruitment & Clinical Assignment (`/api/v1/patients`)

Clinical workflow endpoints for inviting trial participants, accepting invitations, and investigator assignment.

### 6.1 Invite Patient to Study
- **Endpoint**: `POST /api/v1/patients/invite`
- **Authorized**: `SPONSOR`/`SITE` holding `patient:create` (the inviter is the authenticated caller). Invitation codes are single-use and expire after 72 hours.
- **Optional fields**: `tenantId` (the inviter's tenant or any sub-tenant; other tenants return `404`) and `assignedUserId` (a SPONSOR/SITE user in the inviter's subtree whose tenant is the patient's tenant or one of its ancestors; otherwise `400`). Defaults: inviter's tenant, assigned to the inviter.
- **Behavior**:
  - Inherits inviter's `tenant_id`.
  - Maps `patient_details.assigned_user_id` to inviter.
  - Stages user with status `PENDING_VERIFICATION`.
  - Dispatches invitation email with code via `hekma-notification-service`.
- **Request Body**:
  ```json
  {
    "firstName": "Jane",
    "lastName": "Doe",
    "email": "jane.doe@example.com",
    "phoneNumber": "+15551234567",
    "clinicalStudyId": "STUDY-ONCOLOGY-01"
  }
  ```
- **Response `201 Created`**:
  ```json
  {
    "patientId": "e3a89042-45e8-4682-959c-6b3a24119da1",
    "email": "jane.doe@example.com",
    "invitationCode": "INV-7X9Q2Z4B1C",
    "tenantId": "c1f8e21a-3a21-4b45-9876-000000000002",
    "tenantSlug": "mayo-clinic",
    "assignedUserId": "7b08d4ee-5a67-4ebc-88eb-568ebbaeecc6",
    "message": "Patient invited successfully. Invitation email dispatched."
  }
  ```

### 6.2 Accept Patient Invitation (Public Self-Activation)
- **Endpoint**: `POST /api/v1/patients/accept-invite`
- **Authentication**: Unauthenticated / Public.
- **Behavior**:
  - Validates `invitationToken` and regulatory consent flags.
  - Provisions account in Firebase Auth with custom claims `{ role: "PATIENT", tenant_id: "..." }`.
  - Sets user status `ACTIVE`, `isActive = true`, `emailVerified = true`.
  - Records consent timestamp in `patient_details.consented_at = NOW()`.
- **Request Body**:
  ```json
  {
    "invitationToken": "INV-7X9Q2Z4B1C",
    "password": "SecurePassword123!",
    "termsAccepted": true,
    "privacyPolicyAccepted": true,
    "healthDataConsentAccepted": true
  }
  ```
- **Response `200 OK`**: Returns activated `PatientResponse`.

### 6.3 List Patients with Tenant Scoping
- **Endpoint**: `GET /api/v1/patients`
- **Authorized**: patients (self only) and callers holding `patient:read`.
- **Scoping Invariants**:
  - `SPONSOR` and `SITE` callers see patients of their tenant and all of its sub-tenants.
  - `assignedToMe=true`: Filters patients directly mapped to the caller (`assigned_user_id == caller.id`).
  - `ADMIN` and `SYSTEM_ADMIN`: Can query all patients, or filter by `?tenantId=<UUID>` (e.g. default tenant unassigned cohort).
  - `PATIENT`: only its own profile.
- **Response `200 OK` (`PagedResponse<PatientResponse>`)**

### 6.4 Get Patient Profile by ID
- **Endpoint**: `GET /api/v1/patients/{patientId}`
- **Scoping**: `PATIENT` callers can read only themselves; `SPONSOR`/`SITE` only patients of their tenant's subtree; `ADMIN`/`SYSTEM_ADMIN` any patient. Out-of-scope patients return `404 Not Found`.

### 6.5 Reassign Patient to Investigator
- **Endpoint**: `PATCH /api/v1/patients/{patientId}/assign`
- **Authorized**: callers holding `patient:assign` (the operator is the authenticated caller).
- **Request Body**:
  ```json
  {
    "assignedUserId": "8b9281a0-25e4-47bc-9177-3e4e94119d50"
  }
  ```
- **Behavior**:
  - For `SPONSOR`/`SITE`: patient and new investigator must be in the caller's subtree (else `404`), and the investigator's tenant must be the patient's tenant or one of its ancestors (else `400`).
  - For `ADMIN`: Can assign an unassigned patient from default tenant to a site investigator, automatically migrating the patient's tenant.

---

### 6.6 Update Patient Profile
- **Endpoint**: `PATCH /api/v1/patients/{patientId}` — the patient itself, or callers holding `patient:update` whose subtree contains the patient (others `404`).
- **Request Body**: `{ "firstName": "Jane", "lastName": "Doe", "phoneNumber": "+15551234567" }` (all optional).

---

## 7. REST Endpoints: Custom Roles & Functional Permissions (`/api/v1/custom-roles`, `/api/v1/users/{userId}/custom-roles`)

Custom functional role governance (RBAC Phase 8). Allows tenant organizations to define and assign custom roles bundling granular authorities within their tenant subtree.

### 7.1 Create Custom Role
- **Endpoint**: `POST /api/v1/custom-roles`
- **Authorized**: `role:create`
- **Invariants**:
  - **Grant $\le$ Own**: Caller can only bundle authorities they personally hold.
  - **Subtree Isolation**: Platform administrators can create global roles (`tenantId = null`) or tenant roles; tenant staff can only create roles within their own tenant subtree.
  - **Code Uniqueness**: Role codes must be unique per tenant (and globally for global templates).
- **Request Body (`CreateCustomRoleRequest`)**:
  ```json
  {
    "name": "Clinical Research Associate",
    "code": "CRA",
    "description": "Monitors trial sites and participant adherence",
    "tenantId": "c1f8e21a-3a21-4b45-9876-000000000002",
    "authorities": ["patient:read", "patient:update"]
  }
  ```
- **Response `201 Created`**: Returns `CustomRoleResponse`.

### 7.2 List Visible Custom Roles
- **Endpoint**: `GET /api/v1/custom-roles` (optional query param: `?tenantId=<UUID>`)
- **Authorized**: `role:read`
- **Scoping**: Returns global platform template roles + roles defined within the caller's tenant subtree or ancestor tenants.

### 7.3 Get Custom Role Details
- **Endpoint**: `GET /api/v1/custom-roles/{roleId}`
- **Authorized**: `role:read` (must be visible within caller's scope)
- **Response `200 OK`**: Returns `CustomRoleResponse` including bundled authorities list and active assigned user count.

### 7.4 Update Custom Role
- **Endpoint**: `PUT /api/v1/custom-roles/{roleId}`
- **Authorized**: `role:update`
- **Invariants**: Immutable system roles cannot be modified. Updating authority bundle enforces **Grant $\le$ Own**.

### 7.5 Delete Custom Role
- **Endpoint**: `DELETE /api/v1/custom-roles/{roleId}`
- **Authorized**: `role:delete`
- **Invariants**: System roles cannot be deleted. Soft-deletes the role (`is_deleted = true`). Rejects deletion with `400 Bad Request` if any active users are currently assigned this role.

### 7.6 Assign Custom Roles to Staff User
- **Endpoint**: `PUT /api/v1/users/{userId}/custom-roles`
- **Authorized**: `role:assign`
- **Invariants**:
  - **No Self-Elevation**: Users cannot assign or modify custom roles for themselves.
  - **Target User Scope**: Staff only (`ADMIN`, `SPONSOR`, `SITE`) within caller's tenant subtree.
  - **Grant $\le$ Own**: Caller must hold every authority bundled across all roles being assigned.
- **Request Body (`AssignCustomRolesRequest`)**:
  ```json
  {
    "roleIds": ["c71a3d92-23c8-4796-9321-7299a919e912"],
    "reason": "Promoted to lead CRA monitor"
  }
  ```
- **Response `200 OK`**: Returns `UserCustomRolesResponse` with assigned roles and union of inherited authorities.

### 7.7 Get User Assigned Custom Roles
- **Endpoint**: `GET /api/v1/users/{userId}/custom-roles`
- **Authorized**: `role:read` (target user must be within caller's subtree or self)
- **Response `200 OK`**: Returns `UserCustomRolesResponse`.

---

## 8. GraphQL Operations & GraphiQL IDE (`/graphql`, `/graphiql`)

The Hekma Identity Service provides an administrative GraphQL API powered by **Spring for GraphQL** (GraphQL Java) for rich multi-attribute querying, pagination, and batch subfield resolution.

### 8.1 Accessing the GraphiQL IDE
- **Interactive UI URL**: [http://localhost:8080/graphiql](http://localhost:8080/graphiql)
- **Direct GraphQL Endpoint**: `POST http://localhost:8080/graphql`
- **Activation Configuration**: GraphiQL and schema introspection are disabled by default for security hardening. Enable them via environment variables:
  ```env
  GRAPHIQL_ENABLED=true
  GRAPHQL_INTROSPECTION_ENABLED=true
  ```
  *(Or in `application.yml` under `spring.graphql.graphiql.enabled` and `spring.graphql.schema.introspection.enabled`)*.

### 8.2 GraphiQL Header Configuration
All GraphQL queries and mutations require a valid Bearer token and are restricted to platform administrators (`SYSTEM_ADMIN` and `ADMIN`). Callers with other roles receive an error with classification `FORBIDDEN`.

In the GraphiQL web interface, open the **Request Headers** panel at the bottom left and enter:
```json
{
  "Authorization": "Bearer <FIREBASE_ID_TOKEN>"
}
```

### 8.3 Available Queries

#### 1. Retrieve Users with Subfield Batch Loading
Efficiently queries users with optional role filtering (`SYSTEM_ADMIN`, `ADMIN`, `SPONSOR`, `SITE`, `PATIENT`). Subfield `patientDetails` uses `@BatchMapping` to resolve participant data in a single batch query, avoiding N+1 performance bottlenecks:
```graphql
query GetAllUsersWithPatientDetails($role: Role) {
  users(role: $role) {
    id
    email
    displayName
    phoneNumber
    role
    status
    isActive
    isDeleted
    twoFactorEnabled
    createdAt
    patientDetails {
      id
      firstName
      lastName
      termsAccepted
      privacyPolicyAccepted
      healthDataConsentAccepted
      consentedAt
    }
  }
}
```
*Variables:*
```json
{
  "role": "PATIENT"
}
```

#### 2. Query User By ID or Email
```graphql
query GetUserById($id: ID!) {
  userById(id: $id) {
    id
    email
    displayName
    role
    status
    isActive
    patientDetails {
      firstName
      lastName
    }
  }
}

query GetUserByEmail($email: String!) {
  userByEmail(email: $email) {
    id
    email
    role
    status
    isActive
  }
}
```

#### 3. Count Users by Role
```graphql
query GetUserCounts {
  allUsers: userCount
  patients: userCount(role: PATIENT)
  sponsors: userCount(role: SPONSOR)
  sites: userCount(role: SITE)
  admins: userCount(role: ADMIN)
}
```

### 8.4 Available Mutations

#### 1. Update User Activation Status
```graphql
mutation ToggleUserStatus($userId: ID!, $isActive: Boolean!) {
  updateUserActiveStatus(userId: $userId, isActive: $isActive) {
    id
    email
    status
    isActive
    updatedAt
  }
}
```

#### 2. Soft-Delete User
```graphql
mutation SoftDeleteUser($userId: ID!) {
  softDeleteUser(userId: $userId)
}
```

#### 3. Update Patient Two-Factor Authentication (2FA)
```graphql
mutation Update2FA($userId: ID!, $twoFactorEnabled: Boolean!) {
  updateUserTwoFactor(userId: $userId, twoFactorEnabled: $twoFactorEnabled) {
    id
    email
    twoFactorEnabled
  }
}
```

---

## 9. Interactive Documentation & Testing Tools

When running locally (`http://localhost:8080`) with `APP_EXPOSE_API_DOCS=true` (Swagger/OpenAPI) and `GRAPHIQL_ENABLED=true` (GraphiQL):
- **GraphiQL Explorer (GraphQL IDE)**: [http://localhost:8080/graphiql](http://localhost:8080/graphiql)
- **Direct GraphQL Endpoint**: `POST http://localhost:8080/graphql`
- **Swagger UI (REST OpenAPI 3)**: [http://localhost:8080/swagger-ui.html](http://localhost:8080/swagger-ui.html)
- **OpenAPI 3 JSON Specification**: [http://localhost:8080/v3/api-docs](http://localhost:8080/v3/api-docs)

