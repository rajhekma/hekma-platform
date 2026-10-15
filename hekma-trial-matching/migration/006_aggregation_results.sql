CREATE TABLE IF NOT EXISTS aggregation_results (
    id SERIAL PRIMARY KEY,
    job_id UUID NOT NULL,
    flow_type TEXT NOT NULL,
    query_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    relevance_score_R FLOAT NOT NULL,
    eligibility_score_E FLOAT NOT NULL,
    relevance_explanation TEXT,
    eligibility_explanation TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agg_job
ON aggregation_results (job_id);

CREATE INDEX IF NOT EXISTS idx_agg_job_candidate
ON aggregation_results (job_id, candidate_id);

CREATE INDEX IF NOT EXISTS idx_agg_job_query
ON aggregation_results (job_id, query_id);
