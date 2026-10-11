CREATE TABLE medication_reminders (
    id BIGSERIAL PRIMARY KEY,

    medication_id BIGINT NOT NULL,

    hour INTEGER NOT NULL CHECK (hour >= 0 AND hour <= 23),
    minute INTEGER NOT NULL CHECK (minute >= 0 AND minute <= 59),

    label TEXT NULL,

    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT fk_medication
        FOREIGN KEY (medication_id)
        REFERENCES medications(id)
        ON DELETE CASCADE
);  


CREATE INDEX idx_medication_reminders_medication_id
ON medication_reminders(medication_id);
