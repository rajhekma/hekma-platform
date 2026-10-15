# Database & Migration Documentation (`hekma-appointment-service`)

## 1. Co-Location & Flyway Configuration

- **Database**: PostgreSQL (shared `hekmaai` database).
- **Flyway Schema History Table**: `appointment_flyway_schema_history`.
- **Baseline Version**: `0`.
- **Table Prefix**: `appointment_`.

---

## 2. Relational Schema & Tables

### `appointment_appointments`
Stores scheduled appointments.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY | Unique appointment ID |
| `tenant_id` | UUID | NOT NULL | Associated tenant ID |
| `tenant_path` | VARCHAR(255) | NOT NULL | Materialized path for subtree isolation |
| `from_key` | VARCHAR(100) | NOT NULL | Patient or Requester ID |
| `from_type` | VARCHAR(50) | NOT NULL | Participant type |
| `from_name` | VARCHAR(255) | NULLABLE | Participant name |
| `from_email` | VARCHAR(255) | NULLABLE | Participant email |
| `to_key` | VARCHAR(100) | NOT NULL | Doctor / Site coordinator ID |
| `to_type` | VARCHAR(50) | NOT NULL | Participant type |
| `to_name` | VARCHAR(255) | NULLABLE | Doctor name |
| `to_email` | VARCHAR(255) | NULLABLE | Doctor email |
| `start_date_time` | TIMESTAMPTZ | NOT NULL | Scheduled start timestamp |
| `end_date_time` | TIMESTAMPTZ | NOT NULL | Scheduled end timestamp |
| `status` | VARCHAR(50) | NOT NULL | CREATED, UPDATED, CLOSED, CANCELLED |
| `reminder_7d_sent` | BOOLEAN | DEFAULT FALSE | 7-day reminder sent flag |
| `reminder_1d_sent` | BOOLEAN | DEFAULT FALSE | 1-day reminder sent flag |
| `reminder_1h_sent` | BOOLEAN | DEFAULT FALSE | 1-hour reminder sent flag |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | Audit timestamps |
| `created_by` / `updated_by` | VARCHAR(100) | NULLABLE | Audit user IDs |
| `version` | BIGINT | NOT NULL | Optimistic locking |
| `is_deleted` | BOOLEAN | NOT NULL | Soft delete flag |

### `appointment_requests`
Stores booking, reschedule, and cancellation requests.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY | Unique request ID |
| `tenant_id` | UUID | NOT NULL | Tenant ID |
| `tenant_path` | VARCHAR(255) | NOT NULL | Tenant path |
| `from_key` / `to_key` | VARCHAR(100) | NOT NULL | Requester / recipient |
| `type` | VARCHAR(50) | NOT NULL | REACTIVATION, APPOINTMENT_REQUEST, CONSULTATION |
| `request_status` | VARCHAR(50) | NOT NULL | CREATED, ACCEPTED, REJECTED, CLOSED |
| `request_description` | TEXT | NULLABLE | Requester rationale |
| `request_response` | TEXT | NULLABLE | Reviewer/approver comments |

### `appointment_user_preferences`
User preferences for notification channels.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY | Unique preference ID |
| `user_id` | VARCHAR(100) | NOT NULL | User identifier |
| `user_type` | VARCHAR(50) | NOT NULL | User type |
| `toggle_in_app` | BOOLEAN | DEFAULT TRUE | In-app alerts |
| `toggle_email` | BOOLEAN | DEFAULT TRUE | Email alerts |
| `toggle_message` | BOOLEAN | DEFAULT FALSE | SMS alerts |

### `appointment_web_notifications`
In-app web alerts displayed in UI.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY | Unique notification ID |
| `user_id` | VARCHAR(100) | NOT NULL | Recipient user ID |
| `message` | TEXT | NOT NULL | Notification message body |
| `viewed_status` | VARCHAR(50) | NOT NULL | UNREAD, READ |
