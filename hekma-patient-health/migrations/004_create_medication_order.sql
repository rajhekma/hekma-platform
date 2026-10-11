CREATE TABLE IF NOT EXISTS medication_order (
  id TEXT PRIMARY KEY,
  patient_id TEXT,
  hekma_mail TEXT,
  source TEXT,
  raw_resource JSONB NOT NULL,
  status TEXT,
  date_written TIMESTAMP,
  date_ended TIMESTAMP,
  sort_date TIMESTAMP NOT NULL,

  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_medication_patient_or_mail
ON medication_order (patient_id, hekma_mail);

CREATE INDEX IF NOT EXISTS idx_medication_sort_date
ON medication_order (sort_date DESC);

CREATE INDEX IF NOT EXISTS idx_medication_patient
ON medication_order (patient_id);

CREATE INDEX IF NOT EXISTS idx_medication_status
ON medication_order (status);

CREATE INDEX IF NOT EXISTS idx_medication_raw_resource
ON medication_order USING GIN (raw_resource);
