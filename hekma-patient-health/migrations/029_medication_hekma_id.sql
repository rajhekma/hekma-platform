ALTER TABLE medications
    ADD COLUMN IF NOT EXISTS hekma_id VARCHAR(36) NULL;

CREATE INDEX IF NOT EXISTS idx_medications_hekma_id ON medications (hekma_id);
