-- Medicine Details fields (Add Medication screen)
ALTER TABLE medications
    ADD COLUMN IF NOT EXISTS how_much_to_take TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS strength TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS medication_type TEXT NULL;
