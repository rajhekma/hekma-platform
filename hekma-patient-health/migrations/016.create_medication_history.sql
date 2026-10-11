CREATE TABLE medication_history (
    id BIGSERIAL PRIMARY KEY,

    medication_id BIGINT NOT NULL,
    reminder_id BIGINT NULL,

    scheduled_time BIGINT NOT NULL, -- epoch millis
    taken_time BIGINT NULL,

    status TEXT NOT NULL,

    delay_minutes INTEGER NOT NULL DEFAULT 0,

    synced BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT fk_history_medication
        FOREIGN KEY (medication_id)
        REFERENCES medications(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_medication_history_medication_id
ON medication_history(medication_id);

CREATE INDEX idx_medication_history_scheduled_time
ON medication_history(scheduled_time);

CREATE INDEX idx_medication_history_status
ON medication_history(status);
