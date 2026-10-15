# Security Hardening Plan — `hekma-notification-service`

> **Status:** Proposed (2026-10-07) — planning document only; no application code has been changed.
> **Context:** `hekma-identity-service` now authenticates every request with Firebase ID tokens and keeps role, tenant and
> authorities in PostgreSQL (its RBAC Phases 1–3, see `hekma-identity-service/docs/RBAC_PLAN.md`). This plan brings the
> notification service to the same standard.

---

## 1. Findings (verified against code, 2026-10-07)

| # | Finding | Location | Severity |
|---|---|---|---|
| N-01 | A live-format **SendGrid API key** is the in-code default of `SENDGRID_API_KEY`; added in commit `4351b09` and **pushed to `origin/dev`**. Anyone with repo access can send email as `support@hekma.ai`. The commit message says it was copied from `hekma_api`. | `src/main/resources/application.yml` | **Critical** |
| N-02 | In-app inbox endpoints are public and take the user from `?userId=`; `markAsRead` and `delete` take only a notification ID. Anyone can read, mark or delete any user's notifications. | `SecurityConfig` (`/api/v1/in-app-notifications/**` permitAll), `InAppNotificationController` | **Critical** |
| N-03 | `/api/v1/support/**` is whitelisted entirely. Authenticated support endpoints (`/summary`, `/tickets/{id}/attachments`) resolve the user from the client header `X-User-Id` / `X-User-Email` first — any caller can act as any user. | `SecurityConfig`, `SupportController.resolveUser` | **Critical** |
| N-04 | The JWT fallback in `resolveUser` signs with `JWT_SECRET` default `Graphql` (7 bytes). `Keys.hmacShaKeyFor` rejects keys under 32 bytes, so this path always fails — only the spoofable header path works. | `SupportController.parseJwtToken`, `application.yml` | High |
| N-05 | Other secrets with in-code defaults: datasource password (`Pa55word`), service key (`hekma-internal-secret-key-2026`, also hardcoded in `SecurityConfig`), `SUPPORT_OTP_PEPPER`, a personal Gmail username. | `application.yml`, `SecurityConfig` | High |
| N-06 | Service-key check uses `String.equals` (not constant-time). | `ApiKeyAuthFilter` | Low |
| N-07 | `/actuator/**` is whitelisted although Actuator is not a dependency (latent: becomes public the moment it is added). Swagger is always public. | `SecurityConfig` | Low |
| N-08 | Docs describe SMTP as the default email provider and FCM via Firebase credentials; code defaults to SendGrid, and no Firebase SDK is on the classpath. | `docs/ai/*`, `README.md` | Docs |

**Not a finding:** the anonymous support flow under `/api/v1/support/public/**` is protected by an email OTP session token (`X-Support-Otp-Token`) bound to the verified email. It stays public by design.

---

## 2. Target Model

- **Service-to-service** (`/api/v1/notifications/**`): unchanged — `X-Hekma-Service-Key`, compared in constant time, no default value.
- **End users** (in-app inbox, authenticated support): `Authorization: Bearer <Firebase ID token>` issued by `hekma-identity-service`. The notification service **never** trusts user IDs from headers, query parameters or bodies.
- **Token resolution — recommended: introspection by the identity service.** The notification service sends the bearer token to a new internal endpoint of the identity service and caches the answer briefly:

  ```
  POST /internal/v1/auth/introspect          (hekma-identity-service; X-Hekma-Service-Key required)
  { "token": "<Firebase ID token>" }
  → 200 { "active": true, "userId": "…", "role": "PATIENT", "tenantId": "…", "tenantPath": "/…/",
          "email": "…", "authorities": ["patient:read", …] }
  → 200 { "active": false }   (invalid, expired, revoked, deactivated user, inactive tenant)
  ```

  Why introspection rather than verifying the JWT locally:
  1. Identity keys in-app notifications by its own **user UUID** (`sendWelcomeInApp(user.getId(), …)`); a Firebase token only carries the Firebase UID. Introspection returns the UUID; local verification would need a new `userId` custom claim plus a backfill.
  2. It reflects deactivation, tenant suspension and authority changes immediately (identity reads them from its database on every call).
  3. No Firebase SDK, credentials or Web API key are needed in this service, and it works with the identity service's mock tokens in local development.

  Cost: one internal HTTP call per new token; mitigated by an in-memory cache keyed by SHA-256(token) for 60 s (never longer than the token's remaining life). If identity is unreachable → **fail closed** (401/503), never anonymous.

- Alternative (not recommended now): local verification with Google's public keys + a `userId` custom claim set by identity. Revisit only if introspection latency becomes a problem.

---

## 3. Phases

### Phase S0 — Containment (immediate, mostly operational)
1. **Rotate the SendGrid key** in the SendGrid console (revoke `SG.UOh7…`, issue a new one, store it only in the environment / secrets manager). Check `hekma_api` for the same key. Removing it from the file does **not** remove it from git history; rotation is what neutralizes it. (Optional: rewrite history with `git filter-repo` / BFG — coordinate with everyone who has clones.)
2. Remove in-code defaults for `SENDGRID_API_KEY`, `SPRING_DATASOURCE_PASSWORD`/`USERNAME`/`URL`, `HEKMA_SERVICE_API_KEY` (also the `@Value` default in `SecurityConfig`), `SUPPORT_OTP_PEPPER`, `JWT_SECRET`, `SPRING_MAIL_USERNAME`. Fail startup with a clear message when a required value is missing for the selected provider; keep `mock` providers working without secrets for local dev and tests (test `application.yml` supplies dummy values).
3. Constant-time service-key comparison (`MessageDigest.isEqual`).
4. Remove `/actuator/**` from the whitelist; make Swagger exposure configurable (`APP_EXPOSE_API_DOCS`, default false), mirroring identity.

### Phase S1 — Identity introspection endpoint (in `hekma-identity-service`)
1. `POST /internal/v1/auth/introspect`, protected by `X-Hekma-Service-Key` (a separate filter chain for `/internal/**`; not reachable with end-user tokens).
2. Reuses the existing verification path (`FirebaseService.verifyIdToken(token)` with revocation check → user + tenant chain active → authorities).
3. Returns `{active:false}` instead of 401 for bad tokens (the caller decides the HTTP status).
4. Tests: active user, revoked token, deactivated user, suspended ancestor tenant, wrong service key.
5. Also usable later by `hekma-study-service` and Python services (the option discussed earlier).

### Phase S2 — Caller authentication in the notification service
1. `IdentityClient` (RestClient) calling introspection with the service key; timeouts (connect 1 s, read 2 s); `Caffeine`/`ConcurrentHashMap` cache keyed by SHA-256(token), TTL 60 s.
2. `BearerAuthFilter`: for requests with `Authorization: Bearer …`, introspect and set a `CallerPrincipal{userId, role, tenantId, tenantPath, email, authorities}` in the security context; inactive → 401; identity unavailable → 503.
3. `SecurityConfig` deny-by-default:
   - service-key: `/api/v1/notifications/**`
   - bearer: `/api/v1/in-app-notifications/**`, `/api/v1/support/**` (except below)
   - public (exact list): `/api/v1/support/public/**` (OTP-session protected), `GET /api/v1/support/categories`, Swagger when enabled.

### Phase S3 — In-app inbox ownership
1. Remove `userId` request parameters; the inbox is always `caller.userId`.
2. `PATCH /{id}/read` and `DELETE /{id}`: load the notification and require `notification.userId == caller.userId`, else **404**.
3. Tests: own inbox, other user's notification (404), unauthenticated (401), spoofed `?userId=` ignored.

### Phase S4 — Authenticated support endpoints
1. Replace `resolveUser` (header + legacy HS256 JWT) with the verified `CallerPrincipal`; delete the `X-User-Id` / `X-User-Email` path and the legacy JWT parsing.
2. Ticket ownership checks use `caller.userId` / verified email; staff views (if any) use identity roles/authorities.
3. Keep the anonymous OTP flow unchanged.

### Phase S5 — Tests & docs
- Integration tests with a stubbed `IdentityClient` (or WireMock) for every protected route: no token, invalid token, other user, own data, identity down (fail closed).
- Update `docs/ai/*`, `README.md`, `API_DOCUMENTATION.md` (provider defaults, auth model), ADR for introspection-based authentication.

---

## 4. Breaking Changes & Coordination

| Consumer | Change |
|---|---|
| Web/mobile clients of the in-app inbox | Must send `Authorization: Bearer <idToken>`; drop `?userId=` |
| Clients of authenticated support endpoints | Must send the bearer token; `X-User-Id` / legacy `hekma_api` JWTs stop working |
| `hekma-identity-service` | Adds `/internal/v1/auth/introspect`; both services share `HEKMA_SERVICE_API_KEY` = identity `NOTIFICATION_SERVICE_KEY` |
| Deployments | All secrets via environment; startup fails if missing (outside mock providers) |

---

## 5. Open Questions

| ID | Question | Proposed default |
|---|---|---|
| NQ-1 | Support tickets migrated from `hekma_api` store `participant_user_id` / `recipient_user_id` — are these legacy `hekma_api` IDs or identity UUIDs? | Unknown — check data before S4; if legacy, add a mapping or match by verified email |
| NQ-2 | Must legacy `hekma_api` clients keep using support endpoints during transition? | No; switch to identity tokens (the legacy JWT path is already non-functional, N-04) |
| NQ-3 | Rewrite git history to purge the SendGrid key? | Rotate first (mandatory); history rewrite optional |
| NQ-4 | Should in-app notifications be tenant-scoped for staff dashboards? | Out of scope here; covered by the pending multi-tenancy alignment |

---

## 6. Estimated Effort

| Phase | Effort |
|---|---|
| S0 | 0.5 day (+ key rotation by an account owner) |
| S1 (identity) | 0.5–1 day |
| S2 | 1 day |
| S3 | 0.5 day |
| S4 | 1 day (+ NQ-1 data check) |
| S5 | 0.5–1 day |
