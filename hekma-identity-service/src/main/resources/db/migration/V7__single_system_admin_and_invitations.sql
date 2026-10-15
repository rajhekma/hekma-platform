-- Flyway Migration V7: single SYSTEM_ADMIN, bounded patient invitations, staff invitations (RBAC Phase 3)

-- Exactly one (non-deleted) SYSTEM_ADMIN may exist.
CREATE UNIQUE INDEX IF NOT EXISTS identity_uq_users_single_system_admin
    ON identity_users(role) WHERE role = 'SYSTEM_ADMIN' AND is_deleted = FALSE;

-- Patient invitation codes are single-use and expire (72 hours). Existing rows keep NULL (legacy, no expiry recorded).
ALTER TABLE identity_patient_details ADD COLUMN IF NOT EXISTS invitation_expires_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE identity_patient_details ADD COLUMN IF NOT EXISTS invitation_used_at TIMESTAMP WITH TIME ZONE;

-- Single-use, time-limited invitations of SPONSOR/SITE users into a tenant. Only the token hash is stored.
CREATE TABLE IF NOT EXISTS identity_user_invitations (
    id UUID PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    tenant_id UUID NOT NULL REFERENCES identity_tenants(id),
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    authorities VARCHAR(1024) NOT NULL,
    invited_by UUID NOT NULL REFERENCES identity_users(id),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    accepted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS identity_idx_user_invitations_email ON identity_user_invitations(email);
CREATE INDEX IF NOT EXISTS identity_idx_user_invitations_tenant ON identity_user_invitations(tenant_id);
