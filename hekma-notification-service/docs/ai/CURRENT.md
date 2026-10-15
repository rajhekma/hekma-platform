# Current Project State

## Current Focus
Establishing a token-efficient shared AI context system across Claude Code, Cursor, and Antigravity, while preparing the notification dispatcher and support module for **Multi-Tenancy** propagation (`tenant_id` tagging).

## Recently Completed
- **Support Center & Helpdesk Subsystem**: Integrated full support desk migrated from `hekma_api` (`V2__create_support_center_tables.sql`, `SupportTicketService`, `SupportOtpService`, AWS S3 presigned attachment storage SPI).
- **Send Notification Flow Documentation**: Authored [docs/NOTIFICATION_FLOW.md](file:///D:/coding/hekma/hekma-notification-service/docs/NOTIFICATION_FLOW.md) detailing end-to-end delivery mechanics across `EMAIL`, `SMS`, `PUSH`, and `IN_APP`.
- **Fresh Database Consolidation, Table & Index Prefixing**: Consolidated all migrations (V1–V2) into a single baseline migration `V1__init_notification_schema.sql`, prefixed all tables with `notification_` (`notification_logs`, `notification_in_app_notifications`, `notification_support_ticket`, `notification_support_ticket_comment`, etc.), and standardized all database indexes to the microservice-first prefix pattern (`notification_idx_<table/concept>_<column>`, e.g., `notification_idx_logs_recipient`, `notification_idx_in_app_user_id`).
- **Live SMTP Provider**: Configured `SmtpEmailProvider` utilizing Spring Boot Mail (`JavaMailSender`) for live HTML and plain text email delivery.
- **Shared Database Migration Isolation**: Configured custom Flyway schema history table (`spring.flyway.table = notification_flyway_schema_history`) enabling `hekma-notification-service` and `hekma-identity-service` to safely co-locate on the shared `hekmaai` PostgreSQL database without schema migration version collision.
- **Postman Collection & Environment**: Published standalone Postman collection `Hekma_Notification_Service.postman_collection.json` with local environment.
- **Cross-Service Key Alignment**: Aligned `HEKMA_SERVICE_API_KEY` default (`13f8fc11-b3b5-4a9e-ab49-06e96a57f42b`) with `hekma-identity-service` and `hekma-test-app` for seamless internal dispatch.
- **Agent Governance & Planning Boundary**: Formalized strict plan-only boundary and Git commit/push restrictions in [AGENTS.md](file:///D:/coding/hekma/hekma-notification-service/AGENTS.md).
- **JVM UTC TimeZone Enforcement & Flyway Baseline Version 0**: Configured JVM `TimeZone.setDefault(TimeZone.getTimeZone("UTC"))` in `HekmaNotificationServiceApplication` (both `main` and `@PostConstruct`) to eliminate PostgreSQL driver startup parameter errors with deprecated `Asia/Calcutta`, and configured `spring.flyway.baseline-version: 0` in `application.yml` ensuring baseline migration `V1` runs reliably on shared pre-existing databases.
- **Automated Verification**: Test suite verified at **34 passing automated tests** (0 failures, 0 errors) under GraalVM JDK 25 and H2 in-memory DB.

## In Progress
- Parallel AI context synchronization with `hekma-identity-service`, `hekma-ctms-service`, and `hekma-test-app`.
- Security hardening (proposed, 2026-10-07): [docs/SECURITY_PLAN.md](../SECURITY_PLAN.md) — rotate the committed SendGrid key, remove in-code secret defaults, authenticate in-app/support users via identity-service token introspection (no more `?userId=` / `X-User-Id`). Awaiting approval; no code changed.
- Setting up the cross-agent AI context system (`docs/ai/`, `CLAUDE.md`, `.cursor/rules/project.mdc`).

## Pending
- **Multi-Tenancy Alignment**:
  - Add `tenant_id` column to `notification_logs` and `in_app_notifications`.
  - Accept `X-Tenant-ID` header and `tenantId` in `NotificationSendRequest` to enable tenant-specific branding and quota tracking.
- **Production Provider Credentials**:
  - Configure production Twilio Account SID and Firebase Cloud Messaging credentials via environment variables for live delivery verification.

## Known Issues
- **Security (2026-10-07, see [docs/SECURITY_PLAN.md](../SECURITY_PLAN.md))**:
  - A live SendGrid API key is the in-code default in `application.yml` (commit `4351b09`, pushed to `origin/dev`) — must be rotated.
  - `/api/v1/in-app-notifications/**` is public and trusts `?userId=`; `/api/v1/support/**` trusts the client header `X-User-Id`; the legacy JWT fallback (`JWT_SECRET` default `Graphql`) never validates (key under 32 bytes).
  - Other in-code secret defaults: datasource password, `HEKMA_SERVICE_API_KEY`, `SUPPORT_OTP_PEPPER`, mail username.
- Email provider default is **SendGrid** (`EMAIL_PROVIDER:sendgrid`), not SMTP; no Firebase SDK is on the classpath (push is mock-only).
- The shared PostgreSQL server is version 15.19.
- `hekma-identity-service` must set `NOTIFICATION_SERVICE_KEY` equal to this service's `HEKMA_SERVICE_API_KEY`.
- No active compile or test errors.
- Mock providers (`mock`) are required for local test suites when live SMTP/Twilio credentials are not supplied.

## Important Blockers
- None currently blocking notification service development.

## Related Jira Issues
- `HK-6060`: Multi-channel notification engine, SPI strategy pattern, and in-app feed implementation.
