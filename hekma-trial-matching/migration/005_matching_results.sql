CREATE TABLE IF NOT EXISTS matching_results (
    id SERIAL PRIMARY KEY,
    job_id UUID NOT NULL,
    flow_type TEXT NOT NULL,
    query_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    inclusion_results JSONB NOT NULL,
    exclusion_results JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_matching_job
ON matching_results (job_id);

CREATE INDEX IF NOT EXISTS idx_matching_job_candidate
ON matching_results (job_id, candidate_id);

CREATE INDEX IF NOT EXISTS idx_matching_job_query
ON matching_results (job_id, query_id);
