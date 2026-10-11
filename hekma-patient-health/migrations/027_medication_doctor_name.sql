-- Add optional doctor_name column to medications table
ALTER TABLE medications ADD COLUMN IF NOT EXISTS doctor_name TEXT;
