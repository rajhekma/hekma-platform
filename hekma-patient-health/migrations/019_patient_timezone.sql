-- Store IANA timezone per patient (e.g. UTC, America/New_York). Used when API timezone query param is omitted.
ALTER TABLE patient
    ADD COLUMN IF NOT EXISTS timezone TEXT NULL;
