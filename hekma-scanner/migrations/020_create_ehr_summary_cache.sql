-- EHR Summary Cache
-- Stores AI-generated clinical summaries per patient to avoid redundant
-- LLM calls on every request.  Rows are upserted (one row per patient_id)
-- and expire after EHR_SUMMARY_CACHE_TTL_HOURS (default 24 h).
-- Cache is also invalidated automatically when new EHR data is ingested.

CREATE TABLE IF NOT EXISTS ehr_summary_cache (
    id              BIGSERIAL   PRIMARY KEY,
    patient_id      TEXT        NOT NULL UNIQUE,
    summary_json    JSONB       NOT NULL,
    record_count    INT         NOT NULL DEFAULT 0,
    generated_at    TIMESTAMP   NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMP   NOT NULL,
    source_version  TEXT        NOT NULL DEFAULT '',  -- reserved for future hash-based invalidation
    created_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ehr_summary_cache_patient
    ON ehr_summary_cache (patient_id);

CREATE INDEX IF NOT EXISTS idx_ehr_summary_cache_expires
    ON ehr_summary_cache (expires_at);

COMMENT ON TABLE ehr_summary_cache IS
    'PostgreSQL-backed cache for AI EHR clinical summaries. '
    'One row per patient_id. Expires after configurable TTL. '
    'Invalidated automatically on new Fasten EHR imports.';
