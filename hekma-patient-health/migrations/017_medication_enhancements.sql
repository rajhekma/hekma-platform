-- Add patient linkage and extracted payload to prescriptions
ALTER TABLE prescriptions
    ADD COLUMN IF NOT EXISTS patient_id VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS extracted_data JSONB NULL,
    ADD COLUMN IF NOT EXISTS document_type TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_prescriptions_patient_id
    ON prescriptions(patient_id);

-- Device tokens for push notification delivery
CREATE TABLE IF NOT EXISTS patient_device_tokens (
    id BIGSERIAL PRIMARY KEY,
    patient_id VARCHAR(100) NOT NULL,
    device_token TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'unknown',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (patient_id, device_token)
);

CREATE INDEX IF NOT EXISTS idx_patient_device_tokens_patient_id
    ON patient_device_tokens(patient_id);

-- Log of sent medication reminder notifications
CREATE TABLE IF NOT EXISTS medication_notification_log (
    id BIGSERIAL PRIMARY KEY,
    patient_id VARCHAR(100) NOT NULL,
    medication_id BIGINT NOT NULL,
    reminder_id BIGINT NULL,
    scheduled_time BIGINT NOT NULL,
    sent_at TIMESTAMP DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'sent',
    payload JSONB NULL,
    CONSTRAINT fk_notification_medication
        FOREIGN KEY (medication_id)
        REFERENCES medications(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_medication_notification_log_patient_id
    ON medication_notification_log(patient_id);

CREATE INDEX IF NOT EXISTS idx_medication_notification_log_scheduled_time
    ON medication_notification_log(scheduled_time);
