CREATE TABLE IF NOT EXISTS patient (
  id TEXT PRIMARY KEY,
  hekma_mail TEXT,

  given_name TEXT,
  family_name TEXT,

  raw_resource JSONB NOT NULL,

  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_patient_hekma_mail
  ON patient (hekma_mail);

CREATE INDEX IF NOT EXISTS idx_patient_given_name
  ON patient (given_name);

CREATE INDEX IF NOT EXISTS idx_patient_family_name
  ON patient (family_name);
