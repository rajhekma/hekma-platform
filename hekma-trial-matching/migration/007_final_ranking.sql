CREATE TABLE IF NOT EXISTS final_ranking (
    id SERIAL PRIMARY KEY,
    job_id UUID NOT NULL,
    flow_type TEXT NOT NULL,
    query_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    final_score FLOAT NOT NULL,
    rank_position INT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_final_job
ON final_ranking (job_id);

CREATE INDEX IF NOT EXISTS idx_final_job_rank
ON final_ranking (job_id, rank_position);

CREATE INDEX IF NOT EXISTS idx_final_job_candidate
ON final_ranking (job_id, candidate_id);
