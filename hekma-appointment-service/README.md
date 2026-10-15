# Hekma Appointment Service (`hekma-appointment-service`)

Standalone Clinical Appointment, Scheduling, and Reminder microservice for the Hekma Platform.

## Application Purpose & Core Features

`hekma-appointment-service` handles clinical visit scheduling, appointment request approvals/rejections, schedule conflict detection, appointment reminders (1-hour, 1-day, 7-day cadences), and notification preference management for investigators, study coordinators, and patients.

### Core Capabilities
- **Appointment Scheduling & Management**: Creation, updating, cancellation, and retrieval of clinical appointments across trial sites and subjects.
- **Conflict Detection Engine**: Overlap verification preventing double-booking of doctors, sites, or patients across overlapping time intervals.
- **Appointment Requests & Change Workflows**: Subject/doctor initiated requests for new appointments, reschedules, or cancellations with audit history.
- **Notification Preferences & Web In-App Alerts**: User-configurable notification channels (email, SMS, web notifications) and in-app alert tracking.
- **Automated Reminder Scheduler**: Multi-tier scheduled task (1 hour, 1 day, 7 days prior) dispatching notifications via `hekma-notification-service`.
- **Dual Interface**: Full REST API (OpenAPI 3.1) and Spring for GraphQL query/mutation engine (`/graphql`).
- **Distributed Security & Multi-Tenancy**: Centralized token introspection against `hekma-identity-service` with tenant boundary isolation.

---

## Tech Stack & Versions

- **Java Runtime**: Java 25 (Compiler release 21)
- **Framework**: Spring Boot `4.1.1` (Spring Framework 7.x, Spring Security `7.1.1`, Spring Data JPA `4.1.1`)
- **Query Engine**: Spring for GraphQL `2.0.5` / GraphQL Java `25.0`
- **Database & Migrations**: PostgreSQL 15+ (shared `hekmaai` database) / Flyway `12.4.0`
  - Schema History Table: `appointment_flyway_schema_history`
  - Table Prefix: `appointment_*`
- **API Documentation**: SpringDoc OpenAPI `3.1.0` (Swagger UI at `/swagger-ui/index.html`)
- **Test Infrastructure**: H2 In-Memory Database (`MODE=PostgreSQL`) & JUnit 5 / Spring Boot Test

---

## Setup & Running

### Prerequisites
- JDK 21 or GraalVM JDK 25 configured in `JAVA_HOME`.
- PostgreSQL database accessible (default: `localhost:5432/hekmaai`).
- Running instance of `hekma-identity-service` (default: `http://localhost:8080`) for token introspection.
- Running instance of `hekma-notification-service` (default: `http://localhost:8081`) for reminder dispatch.

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

- **Swagger UI**: [http://localhost:8083/swagger-ui/index.html](http://localhost:8083/swagger-ui/index.html) (public access)
- **OpenAPI JSON Spec**: [http://localhost:8083/v3/api-docs](http://localhost:8083/v3/api-docs)
- **GraphiQL Explorer (GraphQL IDE)**: [http://localhost:8083/graphiql](http://localhost:8083/graphiql)
- **Direct GraphQL Endpoint**: `POST http://localhost:8083/graphql`
