# System Architecture (`hekma-ctms-service`)

## 1. High-Level Component Topology

```mermaid
flowchart TD
    Client[Web/Mobile Client] -->|REST / OpenAPI 3.1| RestControllers[REST Controllers :8082]
    Client -->|GraphQL Queries / Mutations| GqlController[GraphQL Controller :8082]
    EDC[External EDC Systems] -->|AES-encrypted Webhook| WebhookController[EDC Webhook Controller]

    subgraph Security Layer
        IntrospectionFilter[IntrospectionAuthenticationFilter]
        IdentityClient[IdentityServiceClient]
        IntrospectionCache[(In-Memory SHA-256 Token Cache)]
    end

    RestControllers & GqlController --> IntrospectionFilter
    IntrospectionFilter --> IdentityClient
    IdentityClient -->|Cache Miss: HTTP POST /api/v1/auth/introspect| IdentityService[hekma-identity-service :8080]
    IdentityClient <--> IntrospectionCache

    subgraph Business Service Layer
        StudyService[StudyService]
        StudySiteService[StudySiteService]
        AdverseEventService[AdverseEventService]
        StudyScheduleService[StudyScheduleService]
        CmtsWebhookService[CmtsWebhookService]
    end

    RestControllers --> StudyService & StudySiteService & AdverseEventService
    GqlController --> StudyService & StudySiteService & AdverseEventService & StudyScheduleService
    WebhookController --> CmtsWebhookService
    CmtsWebhookService --> AdverseEventService

    subgraph Persistence Layer
        JPARepositories[Spring Data JPA Repositories]
        Postgres[(PostgreSQL 15+ hekmaai)]
    end

    StudyService & StudySiteService & AdverseEventService & StudyScheduleService & CmtsWebhookService --> JPARepositories
    JPARepositories --> Postgres
```

---

## 2. External Integration Contracts

### `hekma-identity-service` Token Introspection
- **Request**:
  `POST http://localhost:8080/api/v1/auth/introspect`
  ```json
  { "token": "<bearer_token>" }
  ```
- **Response**:
  ```json
  {
    "active": true,
    "userId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "email": "sponsor.admin@domain.com",
    "role": "SPONSOR",
    "tenantId": "1fa85f64-5717-4562-b3fc-2c963f66afa6",
    "tenantPath": "/sponsor-alpha/",
    "authorities": ["study:create", "study:read", "site:manage"],
    "roles": ["Sponsor Admin"]
  }
  ```
- **Security Context**: Transformed into `CtmsPrincipal` and set into Spring Security `SecurityContextHolder`.
