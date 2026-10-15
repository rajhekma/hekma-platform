CREATE TABLE IF NOT EXISTS patient_annotations (
    patient_id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    comments JSONB DEFAULT '{}'::jsonb,
    has_review_requests BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);