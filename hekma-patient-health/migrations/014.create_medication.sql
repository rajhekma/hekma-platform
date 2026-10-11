CREATE TABLE medications (
    id BIGSERIAL PRIMARY KEY,
    patient_id VARCHAR(100) NOT NULL,

    name TEXT NOT NULL,
    dosage TEXT NOT NULL,
    frequency TEXT NOT NULL,

    start_date DATE NULL,
    end_date DATE NULL,

    instructions TEXT NOT NULL,
    is_reminder_enabled BOOLEAN NOT NULL,

    status TEXT NOT NULL, -- Active | Stopped

    notes TEXT NOT NULL,

    prescription_id BIGINT NULL,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT fk_prescription
        FOREIGN KEY (prescription_id)
        REFERENCES prescriptions(id)
        ON DELETE SET NULL
);
