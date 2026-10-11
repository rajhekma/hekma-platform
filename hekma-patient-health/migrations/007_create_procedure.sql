CREATE TABLE IF NOT EXISTS procedure (
  id TEXT PRIMARY KEY,
  patient_id TEXT,
  hekma_mail TEXT,
  source TEXT,

  raw_resource JSONB NOT NULL,

  procedure_date TIMESTAMP,
  sort_date TIMESTAMP NOT NULL,

  status TEXT,

  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_procedure_patient
  ON procedure (patient_id);

CREATE INDEX IF NOT EXISTS idx_procedure_mail
  ON procedure (hekma_mail);

CREATE INDEX IF NOT EXISTS idx_procedure_patient_or_mail
  ON procedure (patient_id, hekma_mail);

CREATE INDEX IF NOT EXISTS idx_procedure_sort_date
  ON procedure (sort_date DESC);

CREATE INDEX IF NOT EXISTS idx_procedure_status
  ON procedure (status);

CREATE INDEX IF NOT EXISTS idx_procedure_raw_resource
  ON procedure USING GIN (raw_resource);
