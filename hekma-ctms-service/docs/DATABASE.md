# Database Schema & Migrations (`hekma-ctms-service`)

## 1. Database Architecture & Conventions

- **Database Server**: PostgreSQL 15+ (Shared cluster `hekmaai`).
- **Flyway History Table**: `ctms_flyway_schema_history` (isolated from other services).
- **Table Naming**: Microservice prefix `ctms_<table_name>`.
- **Index Naming**: `ctms_idx_<table_name>_<columns>`.
- **Audit Fields**: Every table includes:
  - `created_at TIMESTAMP WITH TIME ZONE NOT NULL`
  - `updated_at TIMESTAMP WITH TIME ZONE`
  - `created_by VARCHAR(100)`
  - `updated_by VARCHAR(100)`
  - `version BIGINT NOT NULL DEFAULT 0`
  - `is_deleted BOOLEAN NOT NULL DEFAULT FALSE`

---

## 2. Table Specifications

### Core Studies & Sites
| Table | Description | Key Columns |
|---|---|---|
| `ctms_studies` | Master study protocol | `study_id` (PK, UUID), `study_number`, `study_title`, `dev_phase`, `status`, `tenant_path` |
| `ctms_study_sites` | Sites allocated to study | `id` (PK), `study_id` (FK), `site_id`, `site_name`, `status`, `onboard_status` |
| `ctms_study_site_contacts` | Site investigators & personnel | `id` (PK), `study_id` (FK), `site_id`, `contact_id`, `role`, `primary_contact_ind` |
| `ctms_study_site_notes` | Site monitoring notes | `id` (PK), `study_id` (FK), `site_id`, `note_title`, `note_description` |
| `ctms_study_site_queries` | Discrepancy & site queries | `query_id` (PK, UUID), `study_id` (FK), `site_id`, `query_title`, `status`, `severity` |

### Protocol Details & Schedules
| Table | Description | Key Columns |
|---|---|---|
| `ctms_study_arms` | Treatment arms | `id` (PK), `study_id` (FK), `arm_num`, `arm_name`, `type`, `status` |
| `ctms_study_arm_details` | Arm dosage & regime steps | `id` (PK), `arm_num` (FK), `regimen`, `dosage`, `route` |
| `ctms_study_events` | Study milestones/events | `event_id` (PK, UUID), `study_id` (FK), `event_type`, `effective_date` |
| `ctms_study_contacts` | Sponsor contacts | `id` (PK), `study_id` (FK), `contact_id`, `role` |
| `ctms_study_schedules` | Visit schedules | `schedule_id` (PK, UUID), `study_id` (FK), `schedule_name`, `status` |
| `ctms_study_schedule_segments` | Schedule segments | `segment_id` (PK, UUID), `schedule_id` (FK), `segment_name`, `segment_order` |
| `ctms_study_schedule_events` | Schedule events / visits | `event_id` (PK, UUID), `segment_id` (FK), `event_name`, `timepoint_day` |

### Patients & Adverse Events
| Table | Description | Key Columns |
|---|---|---|
| `ctms_study_site_patients` | Enrolled patients at site | `id` (PK), `study_id` (FK), `site_id`, `patient_id`, `status` |
| `ctms_study_patient_adverse_events` | Adverse events log | `adverse_event_id` (PK, UUID), `study_id` (FK), `site_id`, `patient_id`, `ae_term`, `severity`, `causality`, `outcome` |
| `ctms_study_schedule_patient_progress` | Patient visit tracking | `progress_id` (PK, UUID), `study_id`, `site_id`, `patient_id`, `event_id`, `status` |

### EDC Webhook Ingestion
| Table | Description | Key Columns |
|---|---|---|
| `ctms_study_site_webhook_configs` | EDC API keys and AES secrets | `config_id` (PK, UUID), `study_id`, `site_id`, `api_key`, `aes_key`, `aes_iv`, `active` |

---

## 3. Flyway Migrations History
- **`V1__init_ctms_schema.sql`**: Full baseline DDL defining 22 CTMS tables, foreign key constraints, indexes, and soft-delete conventions.
