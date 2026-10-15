-- Clinical trial corpus used by TrialGPT location + matching APIs.
-- Matches the current Dev trialgpt_corpus shape (locations/diseases jsonb, etc.).
-- Idempotent: safe on startup when the table already exists.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS trialgpt_corpus (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nct_id TEXT,
    title TEXT,
    text TEXT,
    inclusion_criteria JSONB,
    exclusion_criteria JSONB,
    source_type TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    min_age INTEGER,
    max_age INTEGER,
    sex VARCHAR(20),
    locations JSONB,
    countries JSONB,
    diseases JSONB,
    drugs JSONB,
    phase TEXT,
    enrollment JSONB,
    locations_detailed JSONB,
    overall_status TEXT,
    raw_json JSONB,
    start_date TEXT,
    completion_date TEXT
);

ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS min_age INTEGER;
ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS max_age INTEGER;
ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS sex VARCHAR(20);
ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS locations JSONB;
ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS countries JSONB;
ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS diseases JSONB;
ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS drugs JSONB;
ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS phase TEXT;
ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS enrollment JSONB;
ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS locations_detailed JSONB;
ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS overall_status TEXT;
ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS raw_json JSONB;
ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS start_date TEXT;
ALTER TABLE trialgpt_corpus ADD COLUMN IF NOT EXISTS completion_date TEXT;

CREATE INDEX IF NOT EXISTS idx_trialgpt_corpus_source_type
ON trialgpt_corpus (source_type);

CREATE INDEX IF NOT EXISTS idx_trialgpt_corpus_status
ON trialgpt_corpus (overall_status);

CREATE INDEX IF NOT EXISTS idx_trialgpt_corpus_text_fts
ON trialgpt_corpus
USING gin (to_tsvector('english', "text"));

CREATE UNIQUE INDEX IF NOT EXISTS uq_trialgpt_corpus_nctid
ON trialgpt_corpus (nct_id)
WHERE nct_id IS NOT NULL;
