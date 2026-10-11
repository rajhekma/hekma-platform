CREATE TABLE prescriptions (
    id BIGSERIAL PRIMARY KEY,
    image_path TEXT NOT NULL,
    scanned_at BIGINT NOT NULL, -- epoch millis
    prescription_date DATE NULL,
    prescriber_name TEXT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
