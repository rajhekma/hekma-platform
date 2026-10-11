CREATE TABLE IF NOT EXISTS condition (
  id TEXT PRIMARY KEY,
  patient_id TEXT,
  hekma_mail TEXT,
  source TEXT,

  raw_resource JSONB NOT NULL,

  onset_date TIMESTAMP,
  sort_date TIMESTAMP NOT NULL,

  clinical_status TEXT,

  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_condition_patient_or_mail
ON condition (patient_id, hekma_mail);

CREATE INDEX IF NOT EXISTS idx_condition_sort_date
ON condition (sort_date DESC);

CREATE INDEX IF NOT EXISTS idx_condition_active_or
ON condition (clinical_status, patient_id, hekma_mail);

CREATE INDEX IF NOT EXISTS idx_condition_patient
ON condition (patient_id);

CREATE INDEX IF NOT EXISTS idx_condition_raw_resource
ON condition USING GIN (raw_resource);
