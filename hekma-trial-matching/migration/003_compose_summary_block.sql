CREATE TABLE IF NOT EXISTS compose_summary_block (
    patient_id TEXT PRIMARY KEY,
    summary_text TEXT NOT NULL,
    structured_json JSONB NOT NULL,
    last_data_timestamp TIMESTAMP NOT NULL,
    last_generated_at TIMESTAMP DEFAULT NOW(),
    version INT DEFAULT 1,
    site_id TEXT NULL,
    disease_list TEXT[] NULL
);

-- Indexes aligned with compose table usage patterns
CREATE INDEX IF NOT EXISTS idx_compose_summary_block_last_data_ts
ON compose_summary_block (last_data_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_compose_summary_block_last_generated_at
ON compose_summary_block (last_generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_compose_summary_block_structured_json
ON compose_summary_block USING GIN (structured_json);
