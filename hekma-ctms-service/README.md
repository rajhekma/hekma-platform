# Hekma CTMS Service (`hekma-ctms-service`)

Standalone Clinical Trial Management System (CTMS) microservice for the Hekma Platform.

## Application Purpose & Core Features

`hekma-ctms-service` manages clinical trial operations, protocols, investigator sites, clinical adverse events, visit schedules, and Electronic Data Capture (EDC) system integration.

### Core Capabilities
- **Clinical Study Lifecycle**: Protocol definition, study phases (Phase Iâ€“IV), arms, milestones, endpoints, and status tracking.
- **Site Management & Governance**: Allocation of investigator sites to studies, personnel assignments, queries, and site monitoring notes.
- **Patient Progress & Adverse Events**: Logging and tracking of patient adverse events (AEs) with severity, causality, and outcome metrics.
- **Trial Schedules & Visits**: Visit segments, timepoint events, and patient visit compliance schedules.
- **EDC Webhook Engine**: Secure ingestion of electronic trial data with AES-128/256-CBC decryption, replay protection, and automated entity ingestion.
- **Dual Interface**: Full REST API (OpenAPI 3.1) and GraphQL query/mutation engine (`/graphql`).
- **Distributed Security & Multi-Tenancy**: Centralized token introspection against `hekma-identity-service` with tenant subtree boundary isolation.

---

## Tech Stack & Versions

- **Java Runtime**: Java 25 (Compiler release 21)
- **Framework**: Spring Boot `4.1.1` (Spring Framework 7.x, Spring Security `7.1.1`, Spring Data JPA `4.1.1`)
- **Query Engine**: Spring for GraphQL `2.0.5` / GraphQL Java `25.0`
- **Database & Migrations**: PostgreSQL 15+ (shared `hekmaai` database) / Flyway `12.4.0`
- **API Documentation**: SpringDoc OpenAPI `3.1.0` (Swagger UI at `/swagger-ui/index.html`)
- **Test Infrastructure**: H2 In-Memory Database (`MODE=PostgreSQL`) & JUnit 5 / Spring Boot Test

---

## Setup & Running

### Prerequisites
- JDK 21 or GraalVM JDK 25 configured in `JAVA_HOME`.
- PostgreSQL database accessible (default: `localhost:5432/hekmaai`).
- Running instance of `hekma-identity-service` (default: `http://localhost:8080`) or mock introspection for development.

### Running with Maven Wrapper
```powershell
$env:JAVA_HOME="C:\Users\Acer_PTS\.jdks\graalvm-jdk-25"; $env:Path="$env:JAVA_HOME\bin;" + $env:Path
.\mvnw.cmd spring-boot:run
```

### Running Tests
```powershell
$env:JAVA_HOME="C:\Users\Acer_PTS\.jdks\graalvm-jdk-25"; $env:Path="$env:JAVA_HOME\bin;" + $env:Path
.\mvnw.cmd test
```

---

## API Documentation & Exploration

- **Swagger UI**: [http://localhost:8082/swagger-ui/index.html](http://localhost:8082/swagger-ui/index.html) (public access)
- **OpenAPI JSON Spec**: [http://localhost:8082/v3/api-docs](http://localhost:8082/v3/api-docs)
- **GraphiQL Explorer (GraphQL IDE)**: [http://localhost:8082/graphiql](http://localhost:8082/graphiql)
- **Direct GraphQL Endpoint**: `POST http://localhost:8082/graphql`
