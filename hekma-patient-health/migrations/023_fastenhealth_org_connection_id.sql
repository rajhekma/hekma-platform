-- Option B: scope Fasten resource rows per health-system connection.
-- Re-export replaces rows for (patient_id, org_connection_id) only.

DO $$
DECLARE
    tbl record;
    con record;
    idx_name text;
    uniq_name text;
BEGIN
    FOR tbl IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename LIKE 'fastenhealth\_%' ESCAPE '\'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ADD COLUMN IF NOT EXISTS org_connection_id TEXT',
            tbl.tablename
        );

        idx_name := tbl.tablename || '_patient_conn_idx';
        IF length(idx_name) > 63 THEN
            idx_name := left(idx_name, 63);
        END IF;

        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON %I (patient_id, org_connection_id)',
            idx_name,
            tbl.tablename
        );

        FOR con IN
            SELECT c.conname
            FROM pg_constraint c
            JOIN pg_class rel ON rel.oid = c.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            WHERE nsp.nspname = 'public'
              AND rel.relname = tbl.tablename
              AND c.contype = 'u'
              AND pg_get_constraintdef(c.oid) NOT LIKE '%org_connection_id%'
        LOOP
            EXECUTE format(
                'ALTER TABLE %I DROP CONSTRAINT %I',
                tbl.tablename,
                con.conname
            );
        END LOOP;

        uniq_name := tbl.tablename || '_patient_org_resource_uniq';
        IF length(uniq_name) > 63 THEN
            uniq_name := left(uniq_name, 63);
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class rel ON rel.oid = c.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            WHERE nsp.nspname = 'public'
              AND rel.relname = tbl.tablename
              AND c.conname = uniq_name
        ) THEN
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I UNIQUE (patient_id, org_connection_id, resource_id)',
                tbl.tablename,
                uniq_name
            );
        END IF;
    END LOOP;
END $$;
