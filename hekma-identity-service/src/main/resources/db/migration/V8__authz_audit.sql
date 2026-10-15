-- Flyway Migration V8: Append-only audit log of privileged actions (RBAC Phase 3).
-- Identifiers only, no PHI. The application never updates or deletes rows.

CREATE TABLE IF NOT EXISTS identity_authz_audit_log (
    id UUID PRIMARY KEY,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor_id UUID,
    action VARCHAR(64) NOT NULL,
    target_type VARCHAR(32) NOT NULL,
    target_id UUID,
    tenant_id UUID,
    before_value VARCHAR(2048),
    after_value VARCHAR(2048),
    reason VARCHAR(512)
);

CREATE INDEX IF NOT EXISTS identity_idx_authz_audit_target ON identity_authz_audit_log(target_type, target_id);
CREATE INDEX IF NOT EXISTS identity_idx_authz_audit_actor ON identity_authz_audit_log(actor_id);
CREATE INDEX IF NOT EXISTS identity_idx_authz_audit_tenant ON identity_authz_audit_log(tenant_id);
CREATE INDEX IF NOT EXISTS identity_idx_authz_audit_time ON identity_authz_audit_log(occurred_at);
