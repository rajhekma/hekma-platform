-- Flyway Migration V10: Custom Roles & Role Governance Authorities (RBAC Phase 8)

-- 0. Clean up legacy unversioned prototype tables if present from pre-Flyway setups
DROP TABLE IF EXISTS identity_custom_role_groups CASCADE;
DROP TABLE IF EXISTS identity_permission_group_authorities CASCADE;
DROP TABLE IF EXISTS identity_permission_groups CASCADE;
DROP TABLE IF EXISTS identity_user_custom_roles CASCADE;
DROP TABLE IF EXISTS identity_custom_role_authorities CASCADE;
DROP TABLE IF EXISTS identity_custom_roles CASCADE;

-- 1. Insert new Role Governance authorities into the platform catalogue
INSERT INTO identity_authorities (authority_key, description, allowed_roles) VALUES
    ('role:read', 'View custom roles within own tenant subtree and platform templates', 'ADMIN,SPONSOR,SITE'),
    ('role:create', 'Create custom roles within own tenant subtree', 'ADMIN,SPONSOR,SITE'),
    ('role:update', 'Modify custom role definitions and bundled authorities', 'ADMIN,SPONSOR,SITE'),
    ('role:delete', 'Delete custom roles within own tenant subtree', 'ADMIN,SPONSOR,SITE'),
    ('role:assign', 'Assign or revoke custom roles for users in own subtree', 'ADMIN,SPONSOR,SITE')
ON CONFLICT (authority_key) DO NOTHING;

-- 2. Custom Roles Table
CREATE TABLE identity_custom_roles (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES identity_tenants(id) ON DELETE CASCADE,
    tenant_path VARCHAR(255),
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) NOT NULL,
    description VARCHAR(255),
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0
);

-- Unique index: code unique per tenant (or global when tenant_id IS NULL)
CREATE UNIQUE INDEX identity_uq_custom_roles_tenant_code 
    ON identity_custom_roles(COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::UUID), code)
    WHERE is_deleted = FALSE;

CREATE INDEX identity_idx_custom_roles_tenant_path ON identity_custom_roles(tenant_path);
CREATE INDEX identity_idx_custom_roles_active ON identity_custom_roles(is_active, is_deleted);

-- 3. Custom Role Authorities Mapping Table
CREATE TABLE identity_custom_role_authorities (
    id UUID PRIMARY KEY,
    custom_role_id UUID NOT NULL REFERENCES identity_custom_roles(id) ON DELETE CASCADE,
    authority_key VARCHAR(64) NOT NULL REFERENCES identity_authorities(authority_key) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT identity_uq_custom_role_authorities UNIQUE (custom_role_id, authority_key)
);

CREATE INDEX identity_idx_custom_role_authorities_role ON identity_custom_role_authorities(custom_role_id);

-- 4. User Custom Roles Assignment Table
CREATE TABLE identity_user_custom_roles (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES identity_users(id) ON DELETE CASCADE,
    custom_role_id UUID NOT NULL REFERENCES identity_custom_roles(id) ON DELETE CASCADE,
    assigned_by UUID REFERENCES identity_users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT identity_uq_user_custom_roles UNIQUE (user_id, custom_role_id)
);

CREATE INDEX identity_idx_user_custom_roles_user ON identity_user_custom_roles(user_id);
CREATE INDEX identity_idx_user_custom_roles_role ON identity_user_custom_roles(custom_role_id);

-- 5. Seed default global system role templates
INSERT INTO identity_custom_roles (id, tenant_id, tenant_path, name, code, description, is_system, is_active, is_deleted, created_by, updated_by)
VALUES
    ('c0000000-0000-0000-0000-000000000001', NULL, NULL, 'Sponsor Admin', 'SPONSOR_ADMIN', 'Overall administrator for the sponsor organization', TRUE, TRUE, FALSE, 'SYSTEM', 'SYSTEM'),
    ('c0000000-0000-0000-0000-000000000002', NULL, NULL, 'Study Manager', 'STUDY_MANAGER', 'Operational study manager over trials and sites', TRUE, TRUE, FALSE, 'SYSTEM', 'SYSTEM'),
    ('c0000000-0000-0000-0000-000000000003', NULL, NULL, 'Sponsor Viewer', 'SPONSOR_VIEWER', 'Read-only observer for sponsor trials', TRUE, TRUE, FALSE, 'SYSTEM', 'SYSTEM'),
    ('c0000000-0000-0000-0000-000000000004', NULL, NULL, 'Site Admin', 'SITE_ADMIN', 'Administrator for the clinical research site', TRUE, TRUE, FALSE, 'SYSTEM', 'SYSTEM'),
    ('c0000000-0000-0000-0000-000000000005', NULL, NULL, 'Principal Investigator', 'PRINCIPAL_INVESTIGATOR', 'Lead investigator responsible for clinical study oversight', TRUE, TRUE, FALSE, 'SYSTEM', 'SYSTEM'),
    ('c0000000-0000-0000-0000-000000000006', NULL, NULL, 'Study Coordinator', 'STUDY_COORDINATOR', 'Day-to-day trial coordinator and patient recruiter', TRUE, TRUE, FALSE, 'SYSTEM', 'SYSTEM'),
    ('c0000000-0000-0000-0000-000000000007', NULL, NULL, 'Site Viewer', 'SITE_VIEWER', 'Read-only observer for clinical site activities', TRUE, TRUE, FALSE, 'SYSTEM', 'SYSTEM')
ON CONFLICT (id) DO NOTHING;

-- Seed authorities into global templates
INSERT INTO identity_custom_role_authorities (id, custom_role_id, authority_key)
SELECT gen_random_uuid(), 'c0000000-0000-0000-0000-000000000001', a.authority_key
FROM identity_authorities a
WHERE a.authority_key IN ('tenant:read', 'tenant:update', 'subtenant:create', 'subtenant:manage', 'user:read', 'user:invite', 'user:manage', 'authority:assign', 'role:read', 'role:create', 'role:update', 'role:delete', 'role:assign', 'patient:create', 'patient:read', 'patient:update', 'patient:assign')
ON CONFLICT DO NOTHING;

INSERT INTO identity_custom_role_authorities (id, custom_role_id, authority_key)
SELECT gen_random_uuid(), 'c0000000-0000-0000-0000-000000000002', a.authority_key
FROM identity_authorities a
WHERE a.authority_key IN ('tenant:read', 'tenant:update', 'subtenant:create', 'subtenant:manage', 'patient:create', 'patient:read', 'patient:update', 'patient:assign', 'role:read')
ON CONFLICT DO NOTHING;

INSERT INTO identity_custom_role_authorities (id, custom_role_id, authority_key)
SELECT gen_random_uuid(), 'c0000000-0000-0000-0000-000000000003', a.authority_key
FROM identity_authorities a
WHERE a.authority_key IN ('tenant:read', 'user:read', 'patient:read', 'role:read')
ON CONFLICT DO NOTHING;

INSERT INTO identity_custom_role_authorities (id, custom_role_id, authority_key)
SELECT gen_random_uuid(), 'c0000000-0000-0000-0000-000000000004', a.authority_key
FROM identity_authorities a
WHERE a.authority_key IN ('tenant:read', 'tenant:update', 'subtenant:create', 'subtenant:manage', 'user:read', 'user:invite', 'user:manage', 'authority:assign', 'role:read', 'role:create', 'role:update', 'role:delete', 'role:assign', 'patient:create', 'patient:read', 'patient:update', 'patient:assign')
ON CONFLICT DO NOTHING;

INSERT INTO identity_custom_role_authorities (id, custom_role_id, authority_key)
SELECT gen_random_uuid(), 'c0000000-0000-0000-0000-000000000005', a.authority_key
FROM identity_authorities a
WHERE a.authority_key IN ('patient:create', 'patient:read', 'patient:update', 'patient:assign', 'role:read')
ON CONFLICT DO NOTHING;

INSERT INTO identity_custom_role_authorities (id, custom_role_id, authority_key)
SELECT gen_random_uuid(), 'c0000000-0000-0000-0000-000000000006', a.authority_key
FROM identity_authorities a
WHERE a.authority_key IN ('patient:create', 'patient:read', 'patient:update', 'patient:assign', 'role:read')
ON CONFLICT DO NOTHING;

INSERT INTO identity_custom_role_authorities (id, custom_role_id, authority_key)
SELECT gen_random_uuid(), 'c0000000-0000-0000-0000-000000000007', a.authority_key
FROM identity_authorities a
WHERE a.authority_key IN ('tenant:read', 'user:read', 'patient:read', 'role:read')
ON CONFLICT DO NOTHING;

-- 6. Seed default authorities into configurable role templates
INSERT INTO identity_role_authorities (id, role, authority_key)
SELECT gen_random_uuid(), 'ADMIN', a.authority_key 
FROM identity_authorities a WHERE a.authority_key LIKE 'role:%'
ON CONFLICT DO NOTHING;

INSERT INTO identity_role_authorities (id, role, authority_key)
SELECT gen_random_uuid(), 'SPONSOR', a.authority_key 
FROM identity_authorities a WHERE a.authority_key LIKE 'role:%'
ON CONFLICT DO NOTHING;

INSERT INTO identity_role_authorities (id, role, authority_key)
SELECT gen_random_uuid(), 'SITE', a.authority_key 
FROM identity_authorities a WHERE a.authority_key LIKE 'role:%'
ON CONFLICT DO NOTHING;

-- 7. Backfill existing active tenant staff with the new role authorities
INSERT INTO identity_user_authorities (id, user_id, authority_key, granted_by, created_by, updated_by)
SELECT gen_random_uuid(), u.id, a.authority_key, NULL, 'V10_MIGRATION', 'V10_MIGRATION'
FROM identity_users u
CROSS JOIN (SELECT authority_key FROM identity_authorities WHERE authority_key LIKE 'role:%') a
WHERE u.role IN ('ADMIN', 'SPONSOR', 'SITE') AND u.is_deleted = FALSE
ON CONFLICT DO NOTHING;
