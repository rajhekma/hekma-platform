CREATE TABLE IF NOT EXISTS retrieval_results (
    id SERIAL PRIMARY KEY,
    job_id UUID NOT NULL,
    flow_type TEXT NOT NULL,
    query_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    rank_position INT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_retrieval_job
ON retrieval_results (job_id);

CREATE INDEX IF NOT EXISTS idx_retrieval_job_query
ON retrieval_results (job_id, query_id);

CREATE INDEX IF NOT EXISTS idx_retrieval_job_query_rank
ON retrieval_results (job_id, query_id, rank_position);
