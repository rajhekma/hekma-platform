# API Documentation (`hekma-ctms-service`)

## 1. Authentication & Headers

All non-public endpoints require standard Bearer token authorization:
```http
Authorization: Bearer <identity_service_or_firebase_token>
```
The token is introspected against `hekma-identity-service`. The calling principal's authorities determine endpoint access.

### Public Endpoints (Permitted without Authentication)
- `GET /swagger-ui/**`, `GET /swagger-ui.html`
- `GET /v3/api-docs/**`
- `GET /api/v1/webhook/cmts/generate-keys`
- `POST /webhook/cmts`
- `POST /api/v1/webhook/cmts/load_data`

---

## 2. REST Endpoints

### Clinical Studies (`/api/v1/studies`)
| Method | Path | Required Authority | Description |
|---|---|---|---|
| `POST` | `/api/v1/studies` | `study:create` | Create a clinical study |
| `GET` | `/api/v1/studies` | `study:read` | List clinical studies in caller's subtree |
| `GET` | `/api/v1/studies/{studyId}` | `study:read` | Get clinical study details |
| `PUT` | `/api/v1/studies/{studyId}` | `study:update` | Update clinical study |
| `GET` | `/api/v1/studies/search?q={query}` | `study:read` | Search studies by number, title, or phase |

### Study Sites (`/api/v1/studies/{studyId}/sites`)
| Method | Path | Required Authority | Description |
|---|---|---|---|
| `POST` | `/api/v1/studies/{studyId}/sites` | `site:manage` | Allocate a site to a study |
| `PUT` | `/api/v1/studies/{studyId}/sites/{siteId}` | `site:manage` | Update study site status or configuration |
| `GET` | `/api/v1/studies/{studyId}/sites` | `study:read` | List all sites in a study |
| `GET` | `/api/v1/studies/{studyId}/sites/{siteId}` | `study:read` | Get specific study site details |
| `GET` | `/api/v1/studies/{studyId}/sites/{siteId}/contacts` | `study:read` | Get site contacts and personnel |
| `GET` | `/api/v1/studies/{studyId}/sites/{siteId}/notes` | `study:read` | Get site monitoring notes |

### Study Queries (`/api/v1/studies/{studyId}/sites/{siteId}/queries`)
| Method | Path | Required Authority | Description |
|---|---|---|---|
| `POST` | `/api/v1/studies/{studyId}/sites/{siteId}/queries` | `query:create` | Raise a new query |
| `GET` | `/api/v1/studies/{studyId}/sites/{siteId}/queries` | `query:read` | List queries for site |
| `PUT` | `/api/v1/studies/queries/{queryId}/resolve` | `query:update` | Mark query as resolved |

### Adverse Events (`/api/v1/studies/.../adverse-events`)
| Method | Path | Required Authority | Description |
|---|---|---|---|
| `POST` | `/api/v1/studies/{studyId}/sites/{siteId}/adverse-events` | `adverse_event:create` | Log a patient adverse event |
| `PUT` | `/api/v1/studies/adverse-events/{aeId}` | `adverse_event:update` | Update adverse event details |
| `GET` | `/api/v1/studies/adverse-events/{aeId}` | `adverse_event:read` | Get adverse event by ID |
| `GET` | `/api/v1/studies/{studyId}/adverse-events` | `adverse_event:read` | List adverse events for study |
| `GET` | `/api/v1/studies/{studyId}/sites/{siteId}/adverse-events` | `adverse_event:read` | List adverse events for site |
| `DELETE` | `/api/v1/studies/adverse-events/{aeId}` | `adverse_event:delete` | Soft-delete adverse event |

---

## 3. EDC Webhook Endpoints

### 1. Key Generation
- **Endpoint**: `GET /api/v1/webhook/cmts/generate-keys?studyId={s}&siteId={s}`
- **Response**: Generates and stores 32-char hex API Key, AES-128 key, and 16-char IV for the site.

### 2. Encrypted Payload Ingestion
- **Endpoint**: `POST /webhook/cmts` or `POST /api/v1/webhook/cmts/load_data`
- **Request Headers**:
  - `X-API-KEY`: Site API key
  - `X-Study-Id`: Study ID
  - `X-Site-Id`: Site ID
- **Request Body**:
  ```json
  {
    "resourceType": "ADVERSE_EVENTS",
    "encryptedPayload": "<Base64 encoded AES-CBC ciphertext>"
  }
  ```
- **Processing**: Verifies API key, decrypts ciphertext via AES/CBC/PKCS5Padding, parses JSON records, and synchronizes into PostgreSQL.

---

## 4. GraphQL Operations & GraphiQL IDE (`/graphql`, `/graphiql`)

The Hekma CTMS Service provides a comprehensive GraphQL API powered by **Spring for GraphQL** (port `8082`) for clinical study protocols, investigator site monitoring, patient safety events, and visit schedules.

### 4.1 Accessing the GraphiQL IDE
- **Interactive UI URL**: [http://localhost:8082/graphiql](http://localhost:8082/graphiql)
- **Direct GraphQL Endpoint**: `POST http://localhost:8082/graphql`
- **Activation Configuration**: GraphiQL is enabled by default in local environments:
  ```yaml
  spring:
    graphql:
      graphiql:
        enabled: ${GRAPHIQL_ENABLED:true}
        path: /graphiql
      schema:
        introspection:
          enabled: ${GRAPHQL_INTROSPECTION_ENABLED:true}
  ```

### 4.2 GraphiQL Header Configuration
GraphQL operations are validated by `IntrospectionAuthenticationFilter` via `hekma-identity-service`.

In the GraphiQL web interface, open the **Request Headers** panel at the bottom left and enter:
```json
{
  "Authorization": "Bearer <TOKEN>"
}
```

### 4.3 Available Root Queries

#### 1. Retrieve Clinical Study Protocol
```graphql
query GetStudyDetails($studyId: String!) {
  getStudy(studyId: $studyId) {
    id
    studyId
    studyNumber
    protocolNumber
    studyTitle
    nameOfIMP
    devPhase
    status
    primaryEndPoint
    secondaryEndPoint
    startDt
    endDt
    numberOfSitesPlanned
    numberOfSubPlanned
  }
}
```
*Variables:*
```json
{
  "studyId": "STD-2026-001"
}
```

#### 2. Search Studies
```graphql
query SearchStudies($searchStr: String!) {
  getStudySearch(searchStr: $searchStr) {
    studyId
    studyNumber
    studyTitle
    studyPhase
    status
  }
}
```

#### 3. Retrieve Sites for a Study
```graphql
query GetSitesForStudy($studyId: String!) {
  getStudySite(studyId: $studyId) {
    siteId
    siteName
    status
    onboardStatus
    primaryContact
    role
  }
}
```

#### 4. Retrieve Adverse Events for Study or Site
```graphql
query GetAdverseEvents($studyId: String, $siteId: String) {
  getStudySiteAdverseEvents(studyId: $studyId, siteId: $siteId) {
    adverseEventId
    patientId
    aeTerm
    severity
    causality
    outcome
    startDate
    summary
  }
}
```

#### 5. Search Study Site Discrepancy Queries
```graphql
query SearchQueries($studyId: String, $siteId: String, $statuses: String) {
  searchStudySiteQuery(studyId: $studyId, siteId: $siteId, statuses: $statuses) {
    queryId
    queryNum
    queryTitle
    queryDescription
    category
    severity
    assignedTo
    status
  }
}
```

#### 6. Retrieve Visit Schedule & Cohort Timeline
```graphql
query GetSchedule($studyId: String, $scheduleId: String) {
  getScheduleDetails(studyId: $studyId, scheduleId: $scheduleId) {
    scheduleId
    scheduleName
    segments {
      segmentId
      segmentName
      visits {
        visitId
        visitName
        visitWindowDays
      }
    }
  }
}
```

### 4.4 Available Root Mutations

#### 1. Create Clinical Study
```graphql
mutation CreateNewStudy {
  createStudy(
    studyNumber: "STD-2026-002"
    studyTitle: "Phase II Clinical Trial of Compound X"
    nameofIMP: "Compound-X"
    devPhase: "Phase II"
    protocolNumber: "PRT-CX-002"
    status: "ACTIVE"
    therapeuticArea: "Oncology"
  ) {
    code
    type
    message
    data
  }
}
```

#### 2. Allocate Site to Study
```graphql
mutation AllocateSite {
  addStudySite(
    studyId: "STD-2026-002"
    siteId: "SITE-MAYO-01"
    siteName: "Mayo Clinic Trial Site"
    status: "ACTIVE"
    onboardStatus: "COMPLETED"
  ) {
    code
    message
  }
}
```

#### 3. Log Patient Adverse Event
```graphql
mutation LogAdverseEvent {
  createStudySitePatientAdverseEvents(
    studyId: "STD-2026-002"
    siteId: "SITE-MAYO-01"
    patientId: "PAT-0091"
    aeTerm: "Mild Headache"
    severity: "GRADE_1"
    causality: "POSSIBLE"
    outcome: "RESOLVED"
    startDate: "2026-10-10"
    summary: "Participant experienced transient headache following visit 2."
  ) {
    code
    message
  }
}
```

#### 4. Resolve Discrepancy Query
```graphql
mutation ResolveQuery($queryId: String!) {
  resolveStudySiteQuery(queryId: $queryId) {
    code
    message
  }
}
```

---

## 5. Interactive Documentation & Testing Tools

When running locally (`http://localhost:8082`):
- **GraphiQL Explorer (GraphQL IDE)**: [http://localhost:8082/graphiql](http://localhost:8082/graphiql)
- **Direct GraphQL Endpoint**: `POST http://localhost:8082/graphql`
- **Swagger UI (REST OpenAPI 3)**: [http://localhost:8082/swagger-ui.html](http://localhost:8082/swagger-ui.html)
- **OpenAPI 3 JSON Specification**: [http://localhost:8082/v3/api-docs](http://localhost:8082/v3/api-docs)
