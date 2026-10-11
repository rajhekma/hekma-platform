-- Daily quantity tracking for drops, sprays, inhalers, and other count-based medication.
ALTER TABLE medications
ADD COLUMN IF NOT EXISTS daily_target_count INTEGER NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_medications_daily_target_count'
    ) THEN
        ALTER TABLE medications
        ADD CONSTRAINT chk_medications_daily_target_count
        CHECK (daily_target_count IS NULL OR daily_target_count > 0);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS medication_daily_counts (
    id BIGSERIAL PRIMARY KEY,
    medication_id BIGINT NOT NULL,
    tracking_date DATE NOT NULL,
    timezone VARCHAR(100) NOT NULL,
    target_count INTEGER NOT NULL CHECK (target_count > 0),
    taken_count INTEGER NOT NULL DEFAULT 0 CHECK (taken_count >= 0),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_daily_count_medication
        FOREIGN KEY (medication_id)
        REFERENCES medications(id)
        ON DELETE CASCADE,
    CONSTRAINT uq_medication_daily_count
        UNIQUE (medication_id, tracking_date)
);

CREATE INDEX IF NOT EXISTS idx_medication_daily_counts_date
ON medication_daily_counts(tracking_date);
