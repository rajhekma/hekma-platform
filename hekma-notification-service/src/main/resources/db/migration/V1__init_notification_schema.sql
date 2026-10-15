-- Flyway Migration V1: Consolidated Notification Service Schema
-- Tables: notification_logs, notification_in_app_notifications, notification_support_*

CREATE TABLE IF NOT EXISTS notification_logs (
    id UUID PRIMARY KEY,
    channel VARCHAR(20) NOT NULL,
    recipient VARCHAR(255) NOT NULL,
    title VARCHAR(255),
    content TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    priority VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
    error_message TEXT,
    source_service VARCHAR(100),
    idempotency_key VARCHAR(120),
    metadata_json TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS notification_idx_logs_recipient ON notification_logs(recipient);
CREATE INDEX IF NOT EXISTS notification_idx_logs_channel ON notification_logs(channel);
CREATE INDEX IF NOT EXISTS notification_idx_logs_status ON notification_logs(status);
CREATE INDEX IF NOT EXISTS notification_idx_logs_idempotency ON notification_logs(idempotency_key);
CREATE INDEX IF NOT EXISTS notification_idx_logs_created_at ON notification_logs(created_at);

CREATE TABLE IF NOT EXISTS notification_in_app_notifications (
    id UUID PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(50) DEFAULT 'GENERAL',
    action_url VARCHAR(500),
    data_json TEXT,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS notification_idx_in_app_user_id ON notification_in_app_notifications(user_id);
CREATE INDEX IF NOT EXISTS notification_idx_in_app_is_read ON notification_in_app_notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS notification_idx_in_app_created_at ON notification_in_app_notifications(created_at);

CREATE TABLE IF NOT EXISTS notification_support_ticket (
    id BIGSERIAL PRIMARY KEY,
    uuid VARCHAR(36) UNIQUE NOT NULL,
    ticket_number VARCHAR(30) UNIQUE NOT NULL,
    subject VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(50) NOT NULL DEFAULT 'GENERAL',
    status VARCHAR(50) NOT NULL DEFAULT 'RECEIVED',
    priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
    participant_email VARCHAR(255) NOT NULL,
    participant_user_id VARCHAR(100),
    participant_user_type VARCHAR(50),
    assigned_agent_id VARCHAR(100),
    assigned_agent_name VARCHAR(255),
    assigned_team VARCHAR(100),
    study_id VARCHAR(100),
    resolution TEXT,
    tags VARCHAR(500),
    is_escalated BOOLEAN NOT NULL DEFAULT FALSE,
    escalated_at TIMESTAMP WITH TIME ZONE,
    escalated_by VARCHAR(100),
    sla_due_at TIMESTAMP WITH TIME ZONE,
    sla_breached BOOLEAN NOT NULL DEFAULT FALSE,
    diagnostics_json TEXT,
    privacy_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_by VARCHAR(100),
    created_ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_by VARCHAR(100),
    modified_ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS notification_idx_support_ticket_email ON notification_support_ticket(participant_email);
CREATE INDEX IF NOT EXISTS notification_idx_support_ticket_status ON notification_support_ticket(status);
CREATE INDEX IF NOT EXISTS notification_idx_support_ticket_assigned ON notification_support_ticket(assigned_agent_id);
CREATE INDEX IF NOT EXISTS notification_idx_support_ticket_created ON notification_support_ticket(created_ts);

CREATE TABLE IF NOT EXISTS notification_support_ticket_comment (
    id BIGSERIAL PRIMARY KEY,
    uuid VARCHAR(36) UNIQUE NOT NULL,
    ticket_id BIGINT NOT NULL REFERENCES notification_support_ticket(id) ON DELETE CASCADE,
    author_id VARCHAR(100),
    author_name VARCHAR(255),
    author_type VARCHAR(50) NOT NULL,
    comment_text TEXT NOT NULL,
    is_internal BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS notification_idx_support_comment_ticket ON notification_support_ticket_comment(ticket_id);

CREATE TABLE IF NOT EXISTS notification_support_ticket_attachment (
    id BIGSERIAL PRIMARY KEY,
    uuid VARCHAR(36) UNIQUE NOT NULL,
    ticket_id BIGINT NOT NULL REFERENCES notification_support_ticket(id) ON DELETE CASCADE,
    comment_id BIGINT,
    file_name VARCHAR(500) NOT NULL,
    file_url VARCHAR(1000) NOT NULL,
    file_size BIGINT,
    mime_type VARCHAR(100),
    scan_status VARCHAR(30) NOT NULL DEFAULT 'CLEAN',
    uploaded_by VARCHAR(100),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS notification_idx_support_attachment_ticket ON notification_support_ticket_attachment(ticket_id);

CREATE TABLE IF NOT EXISTS notification_support_ticket_assignment_history (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES notification_support_ticket(id) ON DELETE CASCADE,
    assigned_to_id VARCHAR(100),
    assigned_to_name VARCHAR(255),
    assigned_team VARCHAR(100),
    assigned_by_id VARCHAR(100),
    assigned_by_name VARCHAR(255),
    notes VARCHAR(500),
    created_ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS notification_idx_support_assignment_ticket ON notification_support_ticket_assignment_history(ticket_id);

CREATE TABLE IF NOT EXISTS notification_support_ticket_status_history (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES notification_support_ticket(id) ON DELETE CASCADE,
    from_status VARCHAR(50),
    to_status VARCHAR(50) NOT NULL,
    changed_by_id VARCHAR(100),
    changed_by_name VARCHAR(255),
    notes VARCHAR(500),
    created_ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS notification_idx_support_status_ticket ON notification_support_ticket_status_history(ticket_id);

CREATE TABLE IF NOT EXISTS notification_support_ticket_notification_history (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES notification_support_ticket(id) ON DELETE CASCADE,
    notification_type VARCHAR(50) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    recipient_email VARCHAR(255),
    recipient_user_id VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'SENT',
    error_message VARCHAR(500),
    created_ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS notification_idx_support_notification_ticket ON notification_support_ticket_notification_history(ticket_id);

CREATE TABLE IF NOT EXISTS notification_support_ticket_audit_log (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES notification_support_ticket(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    actor_id VARCHAR(100),
    actor_name VARCHAR(255),
    details TEXT,
    ip_address VARCHAR(50),
    created_ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS notification_idx_support_audit_ticket ON notification_support_ticket_audit_log(ticket_id);

CREATE TABLE IF NOT EXISTS notification_support_sla_tracking (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL UNIQUE REFERENCES notification_support_ticket(id) ON DELETE CASCADE,
    sla_hours INT NOT NULL DEFAULT 48,
    first_response_at TIMESTAMP WITH TIME ZONE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    due_at TIMESTAMP WITH TIME ZONE NOT NULL,
    breached BOOLEAN NOT NULL DEFAULT FALSE,
    created_ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notification_support_otp_verification (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    otp_hash VARCHAR(128) NOT NULL,
    challenge_id VARCHAR(36) UNIQUE NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    session_token VARCHAR(64),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS notification_idx_support_otp_email ON notification_support_otp_verification(email);
CREATE INDEX IF NOT EXISTS notification_idx_support_otp_challenge ON notification_support_otp_verification(challenge_id);
CREATE INDEX IF NOT EXISTS notification_idx_support_otp_session ON notification_support_otp_verification(session_token);
