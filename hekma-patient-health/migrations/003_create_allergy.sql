CREATE TABLE IF NOT EXISTS allergy (
  id TEXT PRIMARY KEY,
  patient_id TEXT,
  hekma_mail TEXT,
  source TEXT,

  raw_resource JSONB NOT NULL,

  onset_date TIMESTAMP,
  sort_date TIMESTAMP NOT NULL,

  status TEXT,
  criticality TEXT,

  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_allergy_patient_or_mail
ON allergy(patient_id, hekma_mail);

CREATE INDEX IF NOT EXISTS idx_allergy_sort_date
ON allergy(sort_date DESC);

CREATE INDEX IF NOT EXISTS idx_allergy_patient
ON allergy(patient_id);

CREATE INDEX IF NOT EXISTS idx_allergy_status
ON allergy (status);

CREATE INDEX IF NOT EXISTS idx_allergy_raw_resource
ON allergy USING GIN (raw_resource);
