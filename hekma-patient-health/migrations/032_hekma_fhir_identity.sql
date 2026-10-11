-- Dual-write support: Hekma id + source on Fasten FHIR tables, plus MySQL↔FHIR link.

CREATE TABLE IF NOT EXISTS hekma_fhir_link (
    hekma_id UUID PRIMARY KEY,
    patient_id TEXT NOT NULL,
    module TEXT NOT NULL,
    mysql_record_id BIGINT,
    fhir_resource_type TEXT NOT NULL,
    fhir_id TEXT NOT NULL,
    source TEXT NOT NULL,
    document_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS hekma_fhir_link_mysql_uniq
    ON hekma_fhir_link (patient_id, module, mysql_record_id)
    WHERE mysql_record_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS hekma_fhir_link_patient_idx
    ON hekma_fhir_link (patient_id, module);

DO $$
DECLARE
    tbl record;
    hekma_uniq text;
BEGIN
    FOR tbl IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename LIKE 'fastenhealth\_%' ESCAPE '\'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ADD COLUMN IF NOT EXISTS hekma_id UUID',
            tbl.tablename
        );
        EXECUTE format(
            'ALTER TABLE %I ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT %L',
            tbl.tablename,
            'ehr'
        );
        EXECUTE format(
            'UPDATE %I SET hekma_id = gen_random_uuid() WHERE hekma_id IS NULL',
            tbl.tablename
        );

        hekma_uniq := tbl.tablename || '_hekma_id_uniq';
        IF length(hekma_uniq) > 63 THEN
            hekma_uniq := left(hekma_uniq, 63);
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class rel ON rel.oid = c.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            WHERE nsp.nspname = 'public'
              AND rel.relname = tbl.tablename
              AND c.conname = hekma_uniq
        ) THEN
            BEGIN
                EXECUTE format(
                    'ALTER TABLE %I ADD CONSTRAINT %I UNIQUE (hekma_id)',
                    tbl.tablename,
                    hekma_uniq
                );
            EXCEPTION WHEN unique_violation THEN
                NULL;
            END;
        END IF;
    END LOOP;
END $$;
