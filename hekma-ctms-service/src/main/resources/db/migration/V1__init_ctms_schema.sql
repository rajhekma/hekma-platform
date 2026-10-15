-- ============================================================================
-- V1__init_ctms_schema.sql
-- Hekma Clinical Trial Management System (CTMS) - Initial PostgreSQL Schema
-- ============================================================================

-- 1. Studies
CREATE TABLE ctms_studies (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    study_id VARCHAR(100) NOT NULL UNIQUE,
    study_number VARCHAR(100) NOT NULL UNIQUE,
    protocol_number VARCHAR(100),
    parent_account_id BIGINT,
    study_title TEXT NOT NULL,
    name_of_imp VARCHAR(255),
    dev_phase VARCHAR(100),
    status VARCHAR(50) NOT NULL DEFAULT 'DRAFT',
    primary_end_point TEXT,
    secondary_end_point TEXT,
    exp_end_point TEXT,
    start_date DATE,
    end_date DATE,
    study_duration VARCHAR(100),
    stopping_criteria TEXT,
    number_of_sites_planned VARCHAR(50),
    number_of_sub_planned VARCHAR(50),
    route VARCHAR(100),
    regiman VARCHAR(255),
    dosage VARCHAR(255),
    stat_method VARCHAR(255),
    interim_analysis VARCHAR(255),
    study_flow TEXT,
    study_status VARCHAR(50),
    study_type VARCHAR(100),
    study_phase VARCHAR(100),
    sponsor_type VARCHAR(100),
    indication VARCHAR(255),
    therapeutic_area VARCHAR(255),
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ctms_idx_studies_number ON ctms_studies (study_number);
CREATE INDEX ctms_idx_studies_tenant_path ON ctms_studies (tenant_path);
CREATE INDEX ctms_idx_studies_parent_account ON ctms_studies (parent_account_id);

-- 2. Treatment Plans
CREATE TABLE ctms_treatment_plans (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id VARCHAR(100) NOT NULL UNIQUE,
    site_id VARCHAR(100) NOT NULL,
    plan_name VARCHAR(255) NOT NULL,
    plan_description TEXT,
    classification VARCHAR(100),
    status VARCHAR(50) DEFAULT 'ACTIVE',
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ctms_idx_plans_site_id ON ctms_treatment_plans (site_id);

-- 3. Study Arms & Details
CREATE TABLE ctms_study_arms (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arm_num VARCHAR(100) NOT NULL UNIQUE,
    study_id VARCHAR(100) NOT NULL,
    arm_name VARCHAR(255) NOT NULL,
    arm_type VARCHAR(100),
    description TEXT,
    status VARCHAR(50),
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ctms_idx_arms_study_id ON ctms_study_arms (study_id);

CREATE TABLE ctms_study_arm_details (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arm_num VARCHAR(100) NOT NULL REFERENCES ctms_study_arms (arm_num) ON DELETE CASCADE,
    dosage_name VARCHAR(255),
    dosage VARCHAR(255),
    strength VARCHAR(100),
    unit VARCHAR(50),
    route VARCHAR(100),
    frequency VARCHAR(100),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ctms_idx_arm_details_arm_num ON ctms_study_arm_details (arm_num);

-- 4. Study Events (Inclusion, Exclusion, RBM, Milestones)
CREATE TABLE ctms_study_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id VARCHAR(100) NOT NULL UNIQUE,
    study_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    sub_type VARCHAR(100),
    description TEXT,
    severity VARCHAR(50),
    status VARCHAR(50),
    effective_date VARCHAR(100),
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ctms_idx_events_study_type ON ctms_study_events (study_id, event_type);

-- 5. Study Contacts
CREATE TABLE ctms_study_contacts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    study_id VARCHAR(100) NOT NULL,
    contact_id VARCHAR(100) NOT NULL,
    role VARCHAR(100),
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ctms_idx_contacts_study_id ON ctms_study_contacts (study_id);

-- 6. Study Sites & Site Contacts
CREATE TABLE ctms_study_sites (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    study_id VARCHAR(100) NOT NULL,
    site_id VARCHAR(100) NOT NULL,
    site_name VARCHAR(255),
    site_user_id VARCHAR(100),
    status VARCHAR(50),
    onboard_status VARCHAR(50),
    limitization VARCHAR(100),
    primary_contact VARCHAR(255),
    role VARCHAR(100),
    imp_received VARCHAR(50),
    placeholder VARCHAR(255),
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT ctms_uq_study_site UNIQUE (study_id, site_id)
);

CREATE INDEX ctms_idx_sites_study ON ctms_study_sites (study_id);
CREATE INDEX ctms_idx_sites_site ON ctms_study_sites (site_id);

CREATE TABLE ctms_study_site_contacts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    study_id VARCHAR(100) NOT NULL,
    site_id VARCHAR(100) NOT NULL,
    contact_id VARCHAR(100) NOT NULL,
    role VARCHAR(100),
    primary_contact_ind VARCHAR(10),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ctms_idx_site_contacts ON ctms_study_site_contacts (study_id, site_id);

-- 7. Study PAG (Patient Advocacy Groups)
CREATE TABLE ctms_study_pags (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    study_id VARCHAR(100) NOT NULL,
    pag_id VARCHAR(100) NOT NULL,
    status VARCHAR(50),
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT ctms_uq_study_pag UNIQUE (study_id, pag_id)
);

CREATE TABLE ctms_study_pag_contacts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    study_id VARCHAR(100) NOT NULL,
    pag_id VARCHAR(100) NOT NULL,
    contact_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- 8. Study Site Queries
CREATE TABLE ctms_study_site_queries (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    query_id VARCHAR(100) NOT NULL UNIQUE,
    query_num VARCHAR(100),
    study_id VARCHAR(100) NOT NULL,
    study_name VARCHAR(255),
    site_id VARCHAR(100) NOT NULL,
    query_title VARCHAR(255) NOT NULL,
    query_description TEXT,
    category VARCHAR(100),
    severity VARCHAR(50),
    status VARCHAR(50) NOT NULL DEFAULT 'OPEN',
    assigned_to VARCHAR(100),
    assigned_to_name VARCHAR(255),
    sponsor_reference1 VARCHAR(255),
    sponsor_reference2 VARCHAR(255),
    site_reference1 VARCHAR(255),
    site_reference2 VARCHAR(255),
    created_by_name VARCHAR(255),
    query_response TEXT,
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ctms_idx_queries_study_site ON ctms_study_site_queries (study_id, site_id);
CREATE INDEX ctms_idx_queries_status ON ctms_study_site_queries (status);

-- 9. Study Site Notes
CREATE TABLE ctms_study_site_notes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    note_id VARCHAR(100) NOT NULL UNIQUE,
    study_id VARCHAR(100) NOT NULL,
    site_id VARCHAR(100) NOT NULL,
    title VARCHAR(255),
    notes TEXT,
    note_type VARCHAR(100),
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ctms_idx_notes_study_site ON ctms_study_site_notes (study_id, site_id);

-- 10. Study Site Patients
CREATE TABLE ctms_study_site_patients (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    study_id VARCHAR(100) NOT NULL,
    site_id VARCHAR(100) NOT NULL,
    patient_id VARCHAR(100) NOT NULL,
    subject_id VARCHAR(100),
    alternate_id VARCHAR(100),
    subject_status VARCHAR(50),
    onboard_status VARCHAR(50),
    arm_num INT,
    note TEXT,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    email VARCHAR(255),
    phone VARCHAR(50),
    gender VARCHAR(50),
    dob VARCHAR(50),
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT ctms_uq_study_site_patient UNIQUE (study_id, site_id, patient_id)
);

CREATE INDEX ctms_idx_patients_study_site ON ctms_study_site_patients (study_id, site_id);
CREATE INDEX ctms_idx_patients_patient_id ON ctms_study_site_patients (patient_id);

-- 11. Adverse Events
CREATE TABLE ctms_study_patient_adverse_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    adverse_event_id VARCHAR(100) NOT NULL UNIQUE,
    study_id VARCHAR(100) NOT NULL,
    site_id VARCHAR(100) NOT NULL,
    patient_id VARCHAR(100) NOT NULL,
    ae_term VARCHAR(255) NOT NULL,
    severity VARCHAR(50),
    causality VARCHAR(100),
    outcome VARCHAR(100),
    start_date VARCHAR(100),
    stop_date VARCHAR(100),
    summary TEXT,
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ctms_idx_ae_study_site ON ctms_study_patient_adverse_events (study_id, site_id);
CREATE INDEX ctms_idx_ae_patient_id ON ctms_study_patient_adverse_events (patient_id);

-- 12. Study Schedules, Segments, Events, Patient Progress
CREATE TABLE ctms_study_schedules (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    schedule_id VARCHAR(100) NOT NULL UNIQUE,
    study_id VARCHAR(100) NOT NULL,
    schedule_name VARCHAR(255),
    status VARCHAR(50),
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ctms_idx_schedules_study ON ctms_study_schedules (study_id);

CREATE TABLE ctms_study_schedule_segments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    schedule_id VARCHAR(100) NOT NULL,
    segment_id VARCHAR(100) NOT NULL,
    segment_name VARCHAR(255),
    segment_order INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE ctms_study_schedule_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    schedule_id VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    event_name VARCHAR(255),
    segment_id VARCHAR(100),
    row_num INT,
    col_num INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE ctms_study_schedule_patient_progress (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pat_schedule_pk VARCHAR(100) NOT NULL UNIQUE,
    schedule_id VARCHAR(100) NOT NULL,
    site_id VARCHAR(100) NOT NULL,
    patient_id VARCHAR(100) NOT NULL,
    event_id VARCHAR(100),
    event_name VARCHAR(255),
    start_date VARCHAR(100),
    end_date VARCHAR(100),
    actual_date VARCHAR(100),
    completed_ind VARCHAR(10),
    notes TEXT,
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ctms_idx_progress_patient ON ctms_study_schedule_patient_progress (schedule_id, site_id, patient_id);

-- 13. EDC Webhook Configs
CREATE TABLE ctms_study_site_webhook_configs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    study_id VARCHAR(100) NOT NULL,
    site_id VARCHAR(100) NOT NULL,
    access_key VARCHAR(100) NOT NULL UNIQUE,
    secret_key VARCHAR(255) NOT NULL,
    created_by VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ctms_uq_webhook_study_site UNIQUE (study_id, site_id)
);

CREATE INDEX ctms_idx_webhook_keys ON ctms_study_site_webhook_configs (access_key, secret_key);

-- 14. Course Resources
CREATE TABLE ctms_course_resources (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    resource_id VARCHAR(100) NOT NULL UNIQUE,
    study_id VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    crs_res_ind VARCHAR(50),
    summary TEXT,
    type VARCHAR(100),
    category VARCHAR(100),
    language VARCHAR(50),
    version VARCHAR(50),
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version_num BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- 15. Assessments
CREATE TABLE ctms_assessments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    assessment_name VARCHAR(255) NOT NULL UNIQUE,
    tenant_id UUID,
    tenant_path VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- 16. Support Details
CREATE TABLE ctms_support_details (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    support_id VARCHAR(100),
    bu_area VARCHAR(100),
    bu_id VARCHAR(100),
    type VARCHAR(100),
    status VARCHAR(50),
    detail1 TEXT,
    detail2 TEXT,
    detail3 TEXT,
    detail4 TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
