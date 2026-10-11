-- Ledger for account deletion: immediate archive + delayed PHI hard purge (step 6).
CREATE TABLE IF NOT EXISTS account_deletion_archive (
    id BIGSERIAL PRIMARY KEY,
    patient_id TEXT NOT NULL,
    subject_id TEXT,
    original_email_hash TEXT,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'ARCHIVED',
    -- ARCHIVED | PURGED
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    purge_eligible_at TIMESTAMPTZ NOT NULL,
    purged_at TIMESTAMPTZ,
    retention_years INTEGER NOT NULL,
    audit_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_account_deletion_archive_patient
    ON account_deletion_archive (patient_id);

CREATE INDEX IF NOT EXISTS idx_account_deletion_archive_purge_due
    ON account_deletion_archive (purge_eligible_at)
    WHERE status = 'ARCHIVED';
