CREATE TABLE IF NOT EXISTS healthkit (
    doc_id TEXT PRIMARY KEY,
    id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_healthkit_id_timestamp
ON healthkit (id, timestamp);
