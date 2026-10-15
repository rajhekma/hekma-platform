-- =============================================================================
-- Raw PostgreSQL DDL for PII/PHI Token Vault (phi_vault)
-- Multi-Environment Setup: dev, staging, demo, production
-- Safe & Idempotent (Uses IF NOT EXISTS)
-- =============================================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Organizations Table (Tenant Isolation)
CREATE TABLE IF NOT EXISTS organizations (
    org_id VARCHAR(128) PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    api_key_hash VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Policies Table (Tenant Anonymization Rules)
CREATE TABLE IF NOT EXISTS policies (
    org_id VARCHAR(128) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    policy_type VARCHAR(32) NOT NULL,
    anonymize_strategy VARCHAR(32),
    custom_replacement VARCHAR(256),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_org_entity_policy PRIMARY KEY (org_id, entity_type)
);

-- 3. Token Mappings Table (Core Reversible Surrogate Vault)
CREATE TABLE IF NOT EXISTS token_mappings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id VARCHAR(128) NOT NULL,
    original_value TEXT NOT NULL, -- AES-256 / AWS KMS Encrypted Ciphertext
    original_hash VARCHAR(64) NOT NULL, -- HMAC-SHA256 Hash for O(1) Index Deduplication
    tokenized_value VARCHAR(256) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    policy_applied VARCHAR(64) NOT NULL,
    context_hash VARCHAR(64),
    confidence FLOAT NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ,
    restored_at TIMESTAMPTZ,
    restored_by VARCHAR(128)
);

-- Indexes for token_mappings
CREATE INDEX IF NOT EXISTS ix_token_mappings_org_id ON token_mappings (org_id);
CREATE INDEX IF NOT EXISTS ix_token_mappings_tokenized_value ON token_mappings (tokenized_value);
CREATE INDEX IF NOT EXISTS ix_token_mappings_entity_type ON token_mappings (entity_type);
CREATE INDEX IF NOT EXISTS ix_token_mappings_original_hash ON token_mappings (original_hash);
CREATE INDEX IF NOT EXISTS ix_token_mappings_created_at ON token_mappings (created_at);
CREATE INDEX IF NOT EXISTS ix_token_mappings_expires_at ON token_mappings (expires_at);
CREATE INDEX IF NOT EXISTS ix_org_token ON token_mappings (org_id, tokenized_value);
CREATE INDEX IF NOT EXISTS ix_org_original_hash ON token_mappings (org_id, original_hash);

-- 4. Audit Logs Table (Immutable HIPAA Access Trail)
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id VARCHAR(128) NOT NULL,
    mapping_id UUID,
    tokenized_value VARCHAR(256),
    entity_type VARCHAR(64),
    action VARCHAR(32) NOT NULL,
    requester_id VARCHAR(128) NOT NULL,
    ip_address VARCHAR(64) NOT NULL,
    purpose VARCHAR(64) NOT NULL,
    reason VARCHAR(256),
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for audit_logs
CREATE INDEX IF NOT EXISTS ix_audit_logs_org_id ON audit_logs (org_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_mapping_id ON audit_logs (mapping_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_requester_id ON audit_logs (requester_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at);
