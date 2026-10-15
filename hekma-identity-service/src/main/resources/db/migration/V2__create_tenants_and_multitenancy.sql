CREATE TABLE IF NOT EXISTS identity_tenants (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    tenant_type VARCHAR(50) NOT NULL DEFAULT 'GENERAL',
    default_tenant BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    subscription_tier VARCHAR(50) DEFAULT 'STANDARD',
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    settings TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS identity_uq_tenants_default_true ON identity_tenants(default_tenant) WHERE default_tenant = TRUE;
CREATE INDEX IF NOT EXISTS identity_idx_tenants_slug ON identity_tenants(slug);
CREATE INDEX IF NOT EXISTS identity_idx_tenants_status ON identity_tenants(status);
CREATE INDEX IF NOT EXISTS identity_idx_tenants_type ON identity_tenants(tenant_type);

-- Seed Default Platform Organization (Hekma)
INSERT INTO identity_tenants (id, name, slug, tenant_type, default_tenant, status, subscription_tier, contact_email)
VALUES ('00000000-0000-0000-0000-000000000001', 'Default Organization', 'default-tenant', 'GENERAL', TRUE, 'ACTIVE', 'ENTERPRISE', 'admin@hekma.com')
ON CONFLICT (id) DO NOTHING;

-- Add tenant_id to identity_users
ALTER TABLE identity_users ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES identity_tenants(id) ON DELETE SET NULL;

-- Backfill any existing tenant users to default tenant
UPDATE identity_users SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE role IN ('SPONSOR', 'SITE', 'PATIENT') AND tenant_id IS NULL;
UPDATE identity_users SET tenant_id = NULL WHERE role IN ('SYSTEM_ADMIN', 'ADMIN');

-- Enforce Role-to-Tenancy Constraint:
-- SYSTEM_ADMIN and ADMIN are platform-global (tenant_id IS NULL)
-- SPONSOR, SITE, and PATIENT must belong to a tenant (tenant_id IS NOT NULL)
ALTER TABLE identity_users ADD CONSTRAINT identity_chk_users_tenant_role
CHECK (
    (role IN ('SYSTEM_ADMIN', 'ADMIN') AND tenant_id IS NULL)
    OR
    (role IN ('SPONSOR', 'SITE', 'PATIENT') AND tenant_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS identity_idx_users_tenant_id ON identity_users(tenant_id);

-- Add assigned_user_id to identity_patient_details for patient-to-site/sponsor user mapping
ALTER TABLE identity_patient_details ADD COLUMN IF NOT EXISTS assigned_user_id UUID REFERENCES identity_users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS identity_idx_patient_details_assigned_user_id ON identity_patient_details(assigned_user_id);
