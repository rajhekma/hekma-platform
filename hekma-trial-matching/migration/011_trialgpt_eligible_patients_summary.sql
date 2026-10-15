-- Add TrialGPT summary fields to eligible cohort table
ALTER TABLE trialgpt_eligible_patients
    ADD COLUMN IF NOT EXISTS summary_text TEXT NULL,
    ADD COLUMN IF NOT EXISTS structured_json JSONB NULL,
    ADD COLUMN IF NOT EXISTS disease_list TEXT[] NULL,
    ADD COLUMN IF NOT EXISTS last_data_timestamp TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS last_generated_at TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS summary_status TEXT NULL DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS idx_trialgpt_eligible_patients_summary_status
ON trialgpt_eligible_patients (summary_status);
