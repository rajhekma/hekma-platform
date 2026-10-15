# Appointment Service

**Service:** `hekma-appointment-service` · **Port:** 8082 · **Role:** Clinical Visit Scheduling & Consultation Lifecycle

This is the scheduling and calendar management service for patient visits, investigator meetings, and doctor consultations across clinics and clinical trial sites.

It is **not** Identity (does not authenticate passwords), **not** CTMS (does not design trial protocols), and **not** Notification (does not own raw SMS/Email dispatch pipelines).

---

## What it supports

| Component | What the user sees | Owns |
|-----------|--------------------|------|
| **1 · Clinical Visits & Video Calls** | Booked visits, video call links, clinic dates | Booking lifecycle, consultation modes (In-person, Video, Phone) |
| **2 · Conflict Detection Engine** | "Doctor is busy at this time" | Double-booking prevention for physicians and patients |
| **3 · Appointment Requests & Approvals** | "Request an appointment" | Patient self-booking, coordinator review & approval workflow |
| **4 · Automated Reminders** | SMS/Push reminders 24 hours & 1 hour prior | Background cron schedulers, delivery tracking via Notification Service |
| **5 · Patient Notification Preferences** | "Remind me via SMS / Email" | Per-patient communication preferences |

---

## High-level architecture

```mermaid
flowchart TB
    APP[Patient Mobile / Clinic Web] --> GW[API Gateway :9080]
    GW --> APPT

    subgraph APPT ["hekma-appointment-service :8082"]
        FILTER[Introspection Filter]
        CORE[Appointment Service]
        CONFLICT[Conflict Detection Engine]
        REQ[Appointment Request Service]
        SCHED[Reminder Scheduler Cron]
        PREF[Notification Preferences]
        
        FILTER --> CORE & CONFLICT & REQ & PREF
        CORE --> CONFLICT
        SCHED --> CORE
    end

    ID[hekma-identity-service :8080] -->|Token Introspection| FILTER
    APPT -->|Tables: appointment_*| PG[(PostgreSQL · hekma_platform)]
    APPT -->|Trigger Reminders & Push| NOTIF[hekma-notification-service :8083]
```

**Rule:** An appointment cannot be confirmed if either the doctor or the patient already has an overlapping active appointment.

---

## Request path (every call)

```mermaid
flowchart LR
    R[Request + Bearer Token] --> INTRO{Introspect via Identity}
    INTRO -->|invalid| U[401 Unauthorized]
    INTRO -->|valid| ROLE{Patient or Staff?}
    ROLE -->|Patient| OWN{userId matches<br/>patientId?}
    OWN -->|no| N[404 Not Found]
    OWN -->|yes| C[Execute Operation]
    ROLE -->|Staff| SUB{Matches Staff<br/>tenantPath?}
    SUB -->|no| N
    SUB -->|yes| C
```

Patients are restricted strictly to their own appointments. Staff members (doctors, coordinators) are bounded by their hospital site tenant path.

---

## 1 · Visit Scheduling & Status Lifecycle

Manages consultation bookings, modalities (In-person, Video Call, Phone), and status transitions.

```mermaid
stateDiagram-v2
    [*] --> REQUESTED: Patient requests visit
    REQUESTED --> CONFIRMED: Staff approves & slot locked
    REQUESTED --> CANCELLED: Rejected / Cancelled
    CONFIRMED --> IN_PROGRESS: Visit begins
    IN_PROGRESS --> COMPLETED: Consultation finished
    CONFIRMED --> CANCELLED: Patient or Clinic cancels
    CONFIRMED --> NO_SHOW: Patient did not attend
```

| API | Purpose |
|-----|---------|
| `POST /api/v1/appointments` | Book and confirm an appointment directly |
| `GET /api/v1/appointments/{id}` | Get appointment details and consultation link |
| `PUT /api/v1/appointments/{id}/status` | Transition status (`CONFIRMED`, `CANCELLED`, `COMPLETED`) |
| `GET /api/v1/appointments/doctor/{doctorId}` | Fetch schedule for a specific clinician |
| `GET /api/v1/appointments/patient/{patientId}` | Fetch upcoming and past visits for a patient |

---

## 2 · Conflict Detection Engine

Checks both doctor and patient calendars before confirming any booking to guarantee zero double-bookings.

```mermaid
sequenceDiagram
    participant User
    participant Appt as AppointmentService
    participant Conflict as ConflictDetectionService
    participant DB as PostgreSQL

    User->>Appt: POST /api/v1/appointments (doctorId, patientId, start, end)
    Appt->>Conflict: checkConflict(doctorId, patientId, start, end)
    Conflict->>DB: Query overlapping active appointments
    alt Overlap found
        DB-->>Conflict: Found conflicting appointment
        Conflict-->>Appt: throw ConflictException
        Appt-->>User: 409 Conflict ("Doctor already has an appointment during this window")
    else No overlap
        DB-->>Conflict: Zero conflicts
        Conflict-->>Appt: Conflict-free
        Appt->>DB: Save new appointment
        Appt-->>User: 201 Created
    end
```

| API | Purpose |
|-----|---------|
| `POST /api/v1/appointments/check-conflicts` | Dry-run check for time slot availability |

---

## 3 · Appointment Requests & Approvals

Allows patients to request appointment slots that trial coordinators or clinic receptionists can review and accept.

| API | Purpose |
|-----|---------|
| `POST /api/v1/appointment-requests` | Patient submits a request for a consultation |
| `GET /api/v1/appointment-requests` | Clinic staff review pending requests |
| `POST /api/v1/appointment-requests/{id}/approve` | Approve request $\rightarrow$ auto-generates confirmed appointment |
| `POST /api/v1/appointment-requests/{id}/reject` | Decline request with reason message |

---

## 4 · Automated Background Reminders

Runs periodic cron tasks to identify upcoming appointments and dispatch automated reminders to patients.

```mermaid
flowchart LR
    CRON[Spring Scheduler Cron] --> QUERY[Query appointments starting in 24h & 1h]
    QUERY --> PREF[Check patient notification preferences]
    PREF --> DISPATCH[Call hekma-notification-service]
    DISPATCH --> MARK[Update reminder status in DB]
```

---

## Where it sits on the platform

```mermaid
flowchart LR
    ID[1 Identity :8080] -->|Token Introspection| APPT[Appointment :8082]
    CTMS[2 CTMS :8081] -.->|Trial Site visits| APPT
    APPT -->|Trigger reminder SMS/Push| NOTIF[Notification :8083]
```

| This service does | Another service does |
|-------------------|----------------------|
| Visit bookings, video call links | Identity: Auth, login, user accounts |
| Schedule conflicts & double-booking checks | CTMS: Protocol design, trial sites, criteria |
| Appointment reminders scheduler | Notification: Direct SMS/Email dispatch |

---

## Data stores

| Store | Used for |
|-------|----------|
| PostgreSQL (`hekma_platform`) | `appointment_appointments`, `appointment_requests`, `appointment_reminders`, `appointment_notification_preferences` |

---

## Run & Test

```powershell
cd hekma-appointment-service
$env:JAVA_HOME="C:\Users\Acer_PTS\.jdks\graalvm-jdk-25"; $env:Path="$env:JAVA_HOME\bin;" + $env:Path
.\mvnw.cmd test
.\mvnw.cmd spring-boot:run
```
