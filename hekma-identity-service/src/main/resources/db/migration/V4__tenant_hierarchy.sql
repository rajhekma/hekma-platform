-- Flyway Migration V4: Hierarchical tenants (RBAC Phase 2)
-- A tenant may have a parent tenant (any type, any depth). The materialized path lists tenant IDs from the root
-- to the tenant (e.g. '/<root-id>/<child-id>/'); a tenant's subtree = every tenant whose path starts with its path.
-- Paths are immutable: tenants are never re-parented.

ALTER TABLE identity_tenants ADD COLUMN IF NOT EXISTS parent_tenant_id UUID REFERENCES identity_tenants(id);
ALTER TABLE identity_tenants ADD COLUMN IF NOT EXISTS path VARCHAR(2048);
ALTER TABLE identity_tenants ADD COLUMN IF NOT EXISTS depth INT NOT NULL DEFAULT 0;

-- Every existing tenant becomes a top-level tenant.
UPDATE identity_tenants SET path = '/' || CAST(id AS VARCHAR(36)) || '/', depth = 0 WHERE path IS NULL;

ALTER TABLE identity_tenants ALTER COLUMN path SET NOT NULL;

CREATE INDEX IF NOT EXISTS identity_idx_tenants_parent ON identity_tenants(parent_tenant_id);
-- varchar_pattern_ops lets PostgreSQL use the index for prefix LIKE 'path%' lookups in any collation.
CREATE INDEX IF NOT EXISTS identity_idx_tenants_path ON identity_tenants(path varchar_pattern_ops);
