-- ==============================================================================
-- V1: Initial Appointment Service Schema
-- Tables:
--   1. appointment_appointments
--   2. appointment_requests
--   3. appointment_user_preferences
--   4. appointment_web_notifications
-- ==============================================================================

-- 1. Appointments Table
CREATE TABLE appointment_appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    tenant_path VARCHAR(255) NOT NULL,
    from_key VARCHAR(100) NOT NULL,
    from_type VARCHAR(50) NOT NULL,
    from_name VARCHAR(255),
    from_email VARCHAR(255),
    to_key VARCHAR(100) NOT NULL,
    to_type VARCHAR(50) NOT NULL,
    to_name VARCHAR(255),
    to_email VARCHAR(255),
    start_date_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_date_time TIMESTAMP WITH TIME ZONE NOT NULL,
    note TEXT,
    mail_subject VARCHAR(255),
    mail_text TEXT,
    doc_mail_text TEXT,
    nav_link TEXT,
    doc_nav_link TEXT,
    reference VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'CREATED',
    notification_status VARCHAR(50),
    reminder_7d_sent BOOLEAN NOT NULL DEFAULT FALSE,
    reminder_1d_sent BOOLEAN NOT NULL DEFAULT FALSE,
    reminder_1h_sent BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX appointment_idx_from_to ON appointment_appointments(from_key, to_key);
CREATE INDEX appointment_idx_tenant_path ON appointment_appointments(tenant_path);
CREATE INDEX appointment_idx_start_end_time ON appointment_appointments(start_date_time, end_date_time);
CREATE INDEX appointment_idx_status_reminders ON appointment_appointments(status, reminder_1h_sent, reminder_1d_sent, reminder_7d_sent);

-- 2. Appointment Requests Table
CREATE TABLE appointment_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    tenant_path VARCHAR(255) NOT NULL,
    from_key VARCHAR(100) NOT NULL,
    from_type VARCHAR(50) NOT NULL,
    to_key VARCHAR(100) NOT NULL,
    to_type VARCHAR(50) NOT NULL,
    ref_key1 VARCHAR(100),
    ref_type1 VARCHAR(50),
    ref_key2 VARCHAR(100),
    ref_type2 VARCHAR(50),
    ref_key3 VARCHAR(100),
    ref_type3 VARCHAR(50),
    type VARCHAR(50) NOT NULL,
    request_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    request_description TEXT,
    request_status VARCHAR(50) NOT NULL DEFAULT 'CREATED',
    request_response TEXT,
    request_update_timestamp TIMESTAMP WITH TIME ZONE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX appointment_idx_req_from_to ON appointment_requests(from_key, to_key);
CREATE INDEX appointment_idx_req_status ON appointment_requests(request_status);

-- 3. User Notification Preferences Table
CREATE TABLE appointment_user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL,
    user_type VARCHAR(50) NOT NULL,
    toggle_in_app BOOLEAN NOT NULL DEFAULT TRUE,
    toggle_email BOOLEAN NOT NULL DEFAULT TRUE,
    toggle_message BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT appointment_uq_user_pref UNIQUE (user_id, user_type)
);

-- 4. In-App Web Notifications Table (Reminders)
CREATE TABLE appointment_web_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL,
    user_type VARCHAR(50) NOT NULL,
    reference_id VARCHAR(100) NOT NULL,
    reference_type VARCHAR(50) NOT NULL,
    reference_timestamp TIMESTAMP WITH TIME ZONE,
    notification_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    viewed_status VARCHAR(50) NOT NULL DEFAULT 'UNREAD',
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    updated_by VARCHAR(128) NOT NULL DEFAULT 'SYSTEM',
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX appointment_idx_web_notif_user ON appointment_web_notifications(user_id, user_type, viewed_status);
