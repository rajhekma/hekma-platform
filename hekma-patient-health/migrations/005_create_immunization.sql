CREATE TABLE IF NOT EXISTS immunization (
  id TEXT PRIMARY KEY,
  patient_id TEXT,
  hekma_mail TEXT,
  source TEXT,
  raw_resource JSONB NOT NULL,
  immunization_date TIMESTAMP,
  sort_date TIMESTAMP NOT NULL,
  status TEXT,

  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_immunization_patient_or_mail
ON immunization (patient_id, hekma_mail);

CREATE INDEX IF NOT EXISTS idx_immunization_sort_date
ON immunization (sort_date DESC);

CREATE INDEX IF NOT EXISTS idx_immunization_patient
ON immunization (patient_id);

CREATE INDEX IF NOT EXISTS idx_immunization_mail
ON immunization (hekma_mail);

CREATE INDEX IF NOT EXISTS idx_immunization_patient_source
ON immunization (patient_id, source);

CREATE INDEX IF NOT EXISTS idx_immunization_raw_resource
ON immunization USING GIN (raw_resource);
