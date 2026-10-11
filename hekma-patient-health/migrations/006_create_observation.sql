CREATE TABLE IF NOT EXISTS observation (
  id TEXT PRIMARY KEY,
  patient_id TEXT,
  hekma_mail TEXT,
  source TEXT,

  raw_resource JSONB NOT NULL,

  observation_date TIMESTAMP,
  sort_date TIMESTAMP NOT NULL,

  category_code TEXT,
  status TEXT,

  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_observation_patient_or_mail
ON observation (patient_id, hekma_mail);

CREATE INDEX IF NOT EXISTS idx_observation_sort_date
ON observation (sort_date DESC);

CREATE INDEX IF NOT EXISTS idx_observation_category
ON observation (category_code);

CREATE INDEX IF NOT EXISTS idx_observation_status
ON observation (status);

CREATE INDEX IF NOT EXISTS idx_observation_raw_resource
ON observation USING GIN (raw_resource);
