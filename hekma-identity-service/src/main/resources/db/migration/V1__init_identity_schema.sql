-- Flyway Migration V1: Consolidated Identity Service Schema
-- Tables: identity_users, identity_patient_details, identity_otp_requests, identity_otp_lockouts, identity_otp_audit_logs

CREATE TABLE IF NOT EXISTS identity_users (
    id UUID PRIMARY KEY,
    firebase_uid VARCHAR(128) NOT NULL UNIQUE,
    email VARCHAR(255) UNIQUE,
    phone_number VARCHAR(50),
    role VARCHAR(50) NOT NULL,
    display_name VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verification_mode VARCHAR(50),
    two_factor_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS identity_idx_users_email ON identity_users(email);
CREATE INDEX IF NOT EXISTS identity_idx_users_firebase_uid ON identity_users(firebase_uid);
CREATE INDEX IF NOT EXISTS identity_idx_users_role ON identity_users(role);
CREATE INDEX IF NOT EXISTS identity_idx_users_phone_number ON identity_users(phone_number);
CREATE INDEX IF NOT EXISTS identity_idx_users_is_deleted ON identity_users(is_deleted);
CREATE INDEX IF NOT EXISTS identity_idx_users_is_active ON identity_users(is_active);
CREATE INDEX IF NOT EXISTS identity_idx_users_phone_verified ON identity_users(phone_verified);
CREATE INDEX IF NOT EXISTS identity_idx_users_email_verified ON identity_users(email_verified);
CREATE INDEX IF NOT EXISTS identity_idx_users_verification_mode ON identity_users(verification_mode);
CREATE INDEX IF NOT EXISTS identity_idx_users_two_factor_enabled ON identity_users(two_factor_enabled);

CREATE TABLE IF NOT EXISTS identity_patient_details (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE REFERENCES identity_users(id) ON DELETE CASCADE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    phone_number VARCHAR(50),
    invitation_code VARCHAR(100),
    terms_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    privacy_policy_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    health_data_consent_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    consented_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS identity_idx_patient_details_user_id ON identity_patient_details(user_id);
CREATE INDEX IF NOT EXISTS identity_idx_patient_details_invitation_code ON identity_patient_details(invitation_code);
CREATE INDEX IF NOT EXISTS identity_idx_patient_details_phone ON identity_patient_details(phone_number);

CREATE TABLE IF NOT EXISTS identity_otp_requests (
    id UUID PRIMARY KEY,
    phone_number VARCHAR(50),
    email VARCHAR(255),
    hashed_otp VARCHAR(255) NOT NULL,
    purpose VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    verification_mode VARCHAR(50) NOT NULL DEFAULT 'PHONE',
    resend_count INT NOT NULL DEFAULT 0,
    verification_attempts INT NOT NULL DEFAULT 0,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    verified_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS identity_idx_otp_requests_phone ON identity_otp_requests(phone_number);
CREATE INDEX IF NOT EXISTS identity_idx_otp_requests_email ON identity_otp_requests(email);
CREATE INDEX IF NOT EXISTS identity_idx_otp_requests_status ON identity_otp_requests(status);
CREATE INDEX IF NOT EXISTS identity_idx_otp_requests_expires_at ON identity_otp_requests(expires_at);
CREATE INDEX IF NOT EXISTS identity_idx_otp_requests_verification_mode ON identity_otp_requests(verification_mode);

CREATE TABLE IF NOT EXISTS identity_otp_lockouts (
    id UUID PRIMARY KEY,
    phone_number VARCHAR(50) UNIQUE,
    email VARCHAR(255) UNIQUE,
    locked_until TIMESTAMP WITH TIME ZONE NOT NULL,
    lock_reason VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS identity_idx_otp_lockouts_phone ON identity_otp_lockouts(phone_number);
CREATE INDEX IF NOT EXISTS identity_idx_otp_lockouts_email ON identity_otp_lockouts(email);
CREATE INDEX IF NOT EXISTS identity_idx_otp_lockouts_locked_until ON identity_otp_lockouts(locked_until);

CREATE TABLE IF NOT EXISTS identity_otp_audit_logs (
    id UUID PRIMARY KEY,
    phone_number VARCHAR(50),
    email VARCHAR(255),
    attempt_id UUID,
    event_type VARCHAR(50) NOT NULL,
    message VARCHAR(500) NOT NULL,
    ip_address VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS identity_idx_otp_audit_phone ON identity_otp_audit_logs(phone_number);
CREATE INDEX IF NOT EXISTS identity_idx_otp_audit_email ON identity_otp_audit_logs(email);
CREATE INDEX IF NOT EXISTS identity_idx_otp_audit_event_type ON identity_otp_audit_logs(event_type);
CREATE INDEX IF NOT EXISTS identity_idx_otp_audit_created_at ON identity_otp_audit_logs(created_at);
