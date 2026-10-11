-- Latest BMI per patient, derived from body height / body weight observations
-- (LOINC codes from standard_lab_catalog: body_height, body_weight, bmi).
-- Written by hekma_api whenever a height/weight vital changes.
--
-- Uses the standard fastenhealth_* column set because 023/032 and the EHR
-- ingest sweep every fastenhealth_% table. Rows carry
-- org_connection_id = 'hekma:computed' so EHR re-ingest deletes never match,
-- and resource_id = 'bmi-' || patient_id so there is one row per patient.
-- Only constraints containing org_connection_id survive 023, so upserts must
-- target (patient_id, org_connection_id, resource_id).
--
-- Keep in sync with BmiPersist.CREATE_TABLE_SQL in hekma_api, which also
-- creates this table (IF NOT EXISTS) on startup.

CREATE TABLE IF NOT EXISTS fastenhealth_bmi_data (
    id BIGSERIAL PRIMARY KEY,
    patient_id TEXT NOT NULL,
    hekma_mail_id TEXT,
    org_connection_id TEXT NOT NULL DEFAULT 'hekma:computed',
    resource_id TEXT NOT NULL,
    hekma_id UUID,
    source TEXT NOT NULL DEFAULT 'computed',
    raw_resource JSONB NOT NULL,
    loinc_code VARCHAR(30) NOT NULL,
    bmi NUMERIC(5,2) NOT NULL,
    bmi_category TEXT,
    height_observation_id BIGINT,
    height_value NUMERIC(10,2),
    height_unit TEXT,
    height_cm NUMERIC(6,2),
    height_observed_at TEXT,
    weight_observation_id BIGINT,
    weight_value NUMERIC(10,2),
    weight_unit TEXT,
    weight_kg NUMERIC(6,2),
    weight_observed_at TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fastenhealth_bmi_data_patient_org_resource_uniq
        UNIQUE (patient_id, org_connection_id, resource_id)
);

CREATE INDEX IF NOT EXISTS fastenhealth_bmi_data_patient_conn_idx
    ON fastenhealth_bmi_data (patient_id, org_connection_id);
