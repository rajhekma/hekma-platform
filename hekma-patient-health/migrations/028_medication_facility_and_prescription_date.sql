-- Add facility_name and prescription_date columns to medications table
ALTER TABLE medications ADD COLUMN IF NOT EXISTS facility_name TEXT;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS prescription_date DATE;
