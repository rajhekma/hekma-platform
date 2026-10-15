-- Registry of MySQL patients that have usable Postgres FHIR clinical data
-- (~30k cohort). For other pipelines; TrialGPT matching still uses compose_summary_block.

CREATE TABLE IF NOT EXISTS trialgpt_eligible_patients (
    subject_id TEXT PRIMARY KEY,
    mysql_patient_id BIGINT NULL,
    has_pg_patient BOOLEAN NOT NULL DEFAULT FALSE,
    clinical_latest_ts TIMESTAMP NULL,
    in_compose_summary_block BOOLEAN NOT NULL DEFAULT FALSE,
    identified_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trialgpt_eligible_patients_mysql_patient_id
ON trialgpt_eligible_patients (mysql_patient_id);

CREATE INDEX IF NOT EXISTS idx_trialgpt_eligible_patients_clinical_ts
ON trialgpt_eligible_patients (clinical_latest_ts DESC);

CREATE INDEX IF NOT EXISTS idx_trialgpt_eligible_patients_in_compose
ON trialgpt_eligible_patients (in_compose_summary_block);
