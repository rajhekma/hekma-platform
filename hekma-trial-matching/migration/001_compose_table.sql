CREATE TABLE IF NOT EXISTS compose (
    patient_id TEXT PRIMARY KEY,
    summary_text TEXT NOT NULL,
    structured_json JSONB NOT NULL,
    last_data_timestamp TIMESTAMP NOT NULL,
    last_generated_at TIMESTAMP DEFAULT now(),
    version INT DEFAULT 1,
    site_id TEXT NULL,
    disease_list TEXT[] NULL
);

ALTER TABLE compose ADD COLUMN IF NOT EXISTS site_id TEXT;
ALTER TABLE compose ADD COLUMN IF NOT EXISTS disease_list TEXT[];

-- Indexes
CREATE INDEX IF NOT EXISTS idx_compose_last_data_ts
ON compose (last_data_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_compose_last_generated_at
ON compose (last_generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_compose_structured_json
ON compose USING GIN (structured_json);