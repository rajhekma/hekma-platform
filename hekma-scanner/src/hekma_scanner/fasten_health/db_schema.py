def _hekma_uniq_name(table: str) -> str:
    name = f"{table}_hekma_id_uniq"
    return name[:63]


def ensure_hekma_identity_columns(cur, table: str) -> None:
    """Add hekma_id/source on an existing fastenhealth_* table if missing."""
    cur.execute(
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS hekma_id UUID"
    )
    cur.execute(
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'ehr'"
    )
    uniq = _hekma_uniq_name(table)
    cur.execute(
        """
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class rel ON rel.oid = c.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE nsp.nspname = 'public'
          AND rel.relname = %s
          AND c.conname = %s
        """,
        (table, uniq),
    )
    if cur.fetchone():
        return
    try:
        cur.execute(f"ALTER TABLE {table} ADD CONSTRAINT {uniq} UNIQUE (hekma_id)")
    except Exception:
        pass


def create_fasten_table(cur, resource_type: str):
    table = f"fastenhealth_{resource_type.lower()}"
    idx_name = f"{table}_patient_conn_idx"
    if len(idx_name) > 63:
        idx_name = idx_name[:63]
    uniq_name = f"{table}_patient_org_resource_uniq"
    if len(uniq_name) > 63:
        uniq_name = uniq_name[:63]

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id BIGSERIAL PRIMARY KEY,
            patient_id TEXT,
            hekma_mail_id TEXT,
            org_connection_id TEXT,
            resource_id TEXT,
            hekma_id UUID,
            source TEXT NOT NULL DEFAULT 'ehr',
            raw_resource JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            archived_at TIMESTAMPTZ NULL,
            CONSTRAINT {uniq_name} UNIQUE (patient_id, org_connection_id, resource_id)
        );
    """)
    cur.execute(f"""
        CREATE INDEX IF NOT EXISTS {idx_name}
        ON {table} (patient_id, org_connection_id)
    """)
    cur.execute(
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL"
    )
    ensure_hekma_identity_columns(cur, table)
