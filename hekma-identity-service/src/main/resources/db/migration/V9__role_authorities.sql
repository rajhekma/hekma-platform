-- Flyway Migration V9: Configurable Role Default Authorities (RBAC Phase 4 Enhancement)

CREATE TABLE IF NOT EXISTS identity_role_authorities (
    id UUID PRIMARY KEY,
    role VARCHAR(50) NOT NULL,
    authority_key VARCHAR(64) NOT NULL REFERENCES identity_authorities(authority_key) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT identity_uq_role_authorities UNIQUE (role, authority_key)
);

CREATE INDEX IF NOT EXISTS identity_idx_role_authorities_role ON identity_role_authorities(role);

-- Update allowed_roles on catalogue to include ADMIN
UPDATE identity_authorities SET allowed_roles = 'ADMIN,SPONSOR,SITE';

-- Seed baseline default authorities for ADMIN (all 12)
INSERT INTO identity_role_authorities (id, role, authority_key)
SELECT gen_random_uuid(), 'ADMIN', authority_key FROM identity_authorities
ON CONFLICT DO NOTHING;

-- Seed baseline default authorities for SPONSOR (all 12)
INSERT INTO identity_role_authorities (id, role, authority_key)
SELECT gen_random_uuid(), 'SPONSOR', authority_key FROM identity_authorities
ON CONFLICT DO NOTHING;

-- Seed baseline default authorities for SITE (all 12)
INSERT INTO identity_role_authorities (id, role, authority_key)
SELECT gen_random_uuid(), 'SITE', authority_key FROM identity_authorities
ON CONFLICT DO NOTHING;

-- Backfill existing active ADMIN users into identity_user_authorities
INSERT INTO identity_user_authorities (id, user_id, authority_key, granted_by, created_by, updated_by)
SELECT gen_random_uuid(), u.id, a.authority_key, NULL, 'V9_MIGRATION', 'V9_MIGRATION'
FROM identity_users u
CROSS JOIN identity_authorities a
WHERE u.role = 'ADMIN' AND u.is_deleted = FALSE
ON CONFLICT DO NOTHING;
