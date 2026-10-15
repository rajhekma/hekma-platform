CREATE TABLE IF NOT EXISTS patient_summary_validations (
    patient_id TEXT PRIMARY KEY,
    validation_result JSONB NOT NULL,
    overall_status TEXT NOT NULL,
    reliability_score INTEGER NOT NULL,
    validated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_patient_summary_validations_status
    ON patient_summary_validations (overall_status);
