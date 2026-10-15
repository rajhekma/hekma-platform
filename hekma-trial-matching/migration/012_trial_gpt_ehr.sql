-- EHR-backed TrialGPT patient summaries from Fasten Health exports.
-- Mirrors trialgpt_eligible_patients summary columns + llm flag for A/B modes.

CREATE TABLE IF NOT EXISTS trial_gpt_ehr (
    subject_id TEXT NOT NULL,
    mysql_patient_id BIGINT NOT NULL,
    has_pg_patient BOOLEAN NOT NULL DEFAULT FALSE,
    clinical_latest_ts TIMESTAMP NULL,
    identified_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    summary_text TEXT NULL,
    structured_json JSONB NULL,
    disease_list TEXT[] NULL,
    last_data_timestamp TIMESTAMP NULL,
    last_generated_at TIMESTAMP NULL,
    summary_status TEXT NULL DEFAULT 'pending',
    llm BOOLEAN NOT NULL,
    PRIMARY KEY (mysql_patient_id, llm)
);

CREATE INDEX IF NOT EXISTS idx_trial_gpt_ehr_subject_id
ON trial_gpt_ehr (subject_id);

CREATE INDEX IF NOT EXISTS idx_trial_gpt_ehr_summary_status
ON trial_gpt_ehr (summary_status);

CREATE INDEX IF NOT EXISTS idx_trial_gpt_ehr_llm
ON trial_gpt_ehr (llm);

CREATE INDEX IF NOT EXISTS idx_trial_gpt_ehr_subject_llm
ON trial_gpt_ehr (subject_id, llm);
