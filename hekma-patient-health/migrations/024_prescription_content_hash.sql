-- Add content_hash column for duplicate prescription detection
ALTER TABLE prescriptions ADD COLUMN IF NOT EXISTS content_hash TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_prescriptions_patient_content_hash
    ON prescriptions (patient_id, content_hash)
    WHERE content_hash IS NOT NULL;
