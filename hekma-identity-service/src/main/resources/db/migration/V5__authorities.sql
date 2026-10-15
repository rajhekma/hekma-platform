-- Flyway Migration V5: Authority catalogue and per-user authorities (RBAC Phase 3)
-- The catalogue is managed only through migrations (mirrors com.hekma.identity.domain.Authority).

CREATE TABLE IF NOT EXISTS identity_authorities (
    authority_key VARCHAR(64) PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    allowed_roles VARCHAR(100) NOT NULL DEFAULT 'SPONSOR,SITE',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO identity_authorities (authority_key, description) VALUES
    ('tenant:read', 'View own tenant and descendant tenants'),
    ('tenant:update', 'Edit profile and settings of own or descendant tenants'),
    ('subtenant:create', 'Create sub-tenants under own or descendant tenants'),
    ('subtenant:manage', 'Suspend or activate descendant tenants'),
    ('user:read', 'View users in own and descendant tenants'),
    ('user:invite', 'Invite SPONSOR/SITE users into own and descendant tenants'),
    ('user:manage', 'Activate, deactivate or soft-delete users in own and descendant tenants'),
    ('authority:assign', 'Grant or revoke authorities (never beyond one''s own)'),
    ('patient:create', 'Create and invite patient profiles'),
    ('patient:read', 'View patients in own and descendant tenants'),
    ('patient:update', 'Update patient profile data'),
    ('patient:assign', 'Reassign patients within own subtree')
ON CONFLICT (authority_key) DO NOTHING;

CREATE TABLE IF NOT EXISTS identity_user_authorities (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES identity_users(id),
    authority_key VARCHAR(64) NOT NULL REFERENCES identity_authorities(authority_key),
    granted_by UUID REFERENCES identity_users(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT identity_uq_user_authorities UNIQUE (user_id, authority_key)
);

CREATE INDEX IF NOT EXISTS identity_idx_user_authorities_user ON identity_user_authorities(user_id);
