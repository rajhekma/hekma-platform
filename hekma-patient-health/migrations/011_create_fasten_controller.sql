-- Fasten widget / connection tracking (required before 022 TEFCA columns).
CREATE TABLE IF NOT EXISTS fasten_controller (
    id BIGSERIAL PRIMARY KEY,
    patient_id TEXT,
    data_time TIMESTAMP,
    fasten_health_ref JSONB,
    org_connection_id TEXT,
    tefca_directory_id TEXT,
    export_status TEXT,
    failure_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fasten_controller_patient_id
    ON fasten_controller (patient_id);

CREATE INDEX IF NOT EXISTS idx_fasten_controller_org_connection_id
    ON fasten_controller (org_connection_id)
    WHERE org_connection_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_fasten_controller_data_time
    ON fasten_controller (data_time DESC);
