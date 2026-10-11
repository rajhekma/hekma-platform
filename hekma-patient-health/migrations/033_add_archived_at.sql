-- Soft-delete flag for account deletion. Safe to re-run.
-- Covers known PHI tables plus every fastenhealth_* table that exists.

DO $$
DECLARE
    tbl TEXT;
    known TEXT[] := ARRAY[
        'patient',
        'healthkit',
        'condition',
        'allergy',
        'immunization',
        'observation',
        'procedure',
        'medication_order',
        'medications',
        'prescriptions',
        'hekma_fhir_link',
        'medication_reminders',
        'medication_history',
        'medication_daily_counts'
    ];
BEGIN
    FOREACH tbl IN ARRAY known
    LOOP
        IF EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = tbl
        ) THEN
            EXECUTE format(
                'ALTER TABLE %I ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL',
                tbl
            );
        END IF;
    END LOOP;

    FOR tbl IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename LIKE 'fastenhealth\_%' ESCAPE '\'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL',
            tbl
        );
    END LOOP;
END $$;
