CREATE TABLE IF NOT EXISTS matching_jobs (
    job_id UUID PRIMARY KEY,

    flow_type TEXT NOT NULL
        CHECK (flow_type IN ('P2T','T2P')),

    requested_user_id TEXT NOT NULL,
    user_type TEXT NOT NULL,

    query_id TEXT NOT NULL,

    parameters JSONB NOT NULL,

    status TEXT NOT NULL
        CHECK (status IN ('STARTED','RUNNING','COMPLETED','FAILED','CANCELLED')),

    compose_status TEXT,
    retrieve_status TEXT,
    evaluate_status TEXT,
    rank_status TEXT,

    stage_meta JSONB DEFAULT '{}'::jsonb,

    error TEXT,
    error_stage TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_matching_jobs_query
ON matching_jobs (query_id, flow_type);

CREATE INDEX IF NOT EXISTS idx_matching_jobs_user
ON matching_jobs (requested_user_id);

CREATE INDEX IF NOT EXISTS idx_matching_jobs_status
ON matching_jobs (status);

CREATE INDEX IF NOT EXISTS idx_matching_jobs_created_at
ON matching_jobs (created_at DESC);
