-- Patient-level LLM usage facts and a versioned price catalog.
-- Cost is frozen at ingest so later list-price changes do not rewrite history.

CREATE TABLE IF NOT EXISTS ai_model_prices (
    id                  BIGSERIAL PRIMARY KEY,
    provider            TEXT NOT NULL,
    model               TEXT NOT NULL,
    input_usd_per_1m    NUMERIC(12, 6) NOT NULL CHECK (input_usd_per_1m >= 0),
    output_usd_per_1m   NUMERIC(12, 6) NOT NULL CHECK (output_usd_per_1m >= 0),
    effective_from      TIMESTAMPTZ NOT NULL DEFAULT TIMESTAMPTZ '1970-01-01 00:00:00+00',
    effective_to        TIMESTAMPTZ,
    UNIQUE (provider, model, effective_from)
);

CREATE INDEX IF NOT EXISTS ai_model_prices_lookup_idx
    ON ai_model_prices (provider, model, effective_from DESC);

CREATE TABLE IF NOT EXISTS ai_usage_events (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          UUID NOT NULL UNIQUE,
    tenant_id           BIGINT NOT NULL DEFAULT 1,
    patient_id          TEXT NOT NULL,
    product             TEXT NOT NULL,
    feature             TEXT NOT NULL DEFAULT '',
    provider            TEXT NOT NULL,
    model               TEXT NOT NULL,
    prompt_tokens       INTEGER NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
    completion_tokens   INTEGER NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
    total_tokens        INTEGER NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    input_cost_usd      NUMERIC(18, 8) NOT NULL DEFAULT 0,
    output_cost_usd     NUMERIC(18, 8) NOT NULL DEFAULT 0,
    cost_usd            NUMERIC(18, 8) NOT NULL DEFAULT 0,
    pricing_status      TEXT NOT NULL DEFAULT 'priced'
                            CHECK (pricing_status IN ('priced', 'unpriced')),
    price_version       TEXT,
    cached              BOOLEAN NOT NULL DEFAULT FALSE,
    job_id              TEXT,
    source_service      TEXT,
    occurred_at         TIMESTAMPTZ NOT NULL,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    schema_version      INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS ai_usage_events_patient_time_idx
    ON ai_usage_events (tenant_id, patient_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS ai_usage_events_patient_product_idx
    ON ai_usage_events (tenant_id, patient_id, product, occurred_at DESC);

CREATE INDEX IF NOT EXISTS ai_usage_events_provider_time_idx
    ON ai_usage_events (tenant_id, provider, occurred_at DESC);

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
