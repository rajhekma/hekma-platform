# Project Context - CTMS Service (`hekma-ctms-service`)

## 1. Domain Overview & Purpose
`hekma-ctms-service` is the standalone Clinical Trial Management System microservice extracted from the legacy monolithic `hekma_api`. It coordinates clinical trials across Sponsors, Contract Research Organizations (CROs), and Investigator Sites.

### Key Business Domains
1. **Clinical Studies (`ctms_studies`)**:
   - Represents the core clinical study protocol.
   - Holds study number, titles, phase (Phase I through Phase IV), IMP (Investigational Medicinal Product), endpoints, status (ACTIVE, INACTIVE, COMPLETED), and tenant ownership (`tenant_path`).
2. **Study Sites (`ctms_study_sites`)**:
   - Manages institutional investigator sites allocated to a study.
   - Encompasses site contacts, investigators, onboarding status, and protocol limitizations.
3. **Study Arms & Events (`ctms_study_arms`, `ctms_study_events`)**:
   - Treatment arms (e.g., Active Treatment vs. Placebo control) and study events/milestones.
4. **Site Queries & Monitoring Notes (`ctms_study_site_queries`, `ctms_study_site_notes`)**:
   - Query resolution system between sponsor monitors (CRAs) and site coordinators.
5. **Adverse Events (`ctms_study_patient_adverse_events`)**:
   - Regulatory tracking of patient adverse events, detailing severity, causality assessment, outcome, and timelines.
6. **Study Schedules & Patient Progress (`ctms_study_schedules`, `ctms_study_schedule_patient_progress`)**:
   - Longitudinal visit schedules, segment flows, and patient visit tracking.
7. **EDC Webhook Engine (`ctms_study_site_webhook_configs`)**:
   - Ingestion gateway for external Electronic Data Capture (EDC) systems.
   - Decrypts inbound AES-128/256-CBC encrypted payloads using site-specific shared keys and IVs.

---

## 2. Multi-Tenancy & Authorization Rules

- **Identity Provider**: All authentication and authorization credentials are provided by `hekma-identity-service`.
- **Introspection Protocol**: `hekma-ctms-service` intercepts `Authorization: Bearer <token>` and validates it via HTTP POST against `http://localhost:8080/api/v1/auth/introspect`.
- **Introspection Cache**: Uses SHA-256 token hashing with 60-second in-memory caching to eliminate redundant round-trips.
- **Tenant Path Isolation**:
  - Each study has an owning tenant path (e.g., `/sponsor-a/`).
  - Users have an assigned tenant path in their principal.
  - Subtree hierarchy check: A user in `/sponsor-a/` can access `/sponsor-a/` and all descendant sites (`/sponsor-a/site-1/`), but cannot access `/sponsor-b/`.
  - `SYSTEM_ADMIN` and `ADMIN` have global access across all tenant subtrees.

---

## 3. Interfaces & Ports

- **Port**: `8082` (configured in `application.yml`).
- **REST Endpoints**: `/api/v1/studies/**`.
- **GraphQL Endpoint**: `/graphql`.
- **EDC Webhooks**: `/webhook/cmts/**` and `/api/v1/webhook/cmts/**`.
- **Swagger UI**: `/swagger-ui/index.html` (Publicly accessible).
