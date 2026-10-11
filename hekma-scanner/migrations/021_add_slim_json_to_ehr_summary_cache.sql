-- Add slim_json column to ehr_summary_cache
-- slim_json is the same as summary_json but with original_record stripped
-- from every timeline event and category event. Used by the default API
-- response (include_records=false) so the DB transfers ~40% less data.
ALTER TABLE ehr_summary_cache
    ADD COLUMN IF NOT EXISTS slim_json JSONB;

COMMENT ON COLUMN ehr_summary_cache.slim_json IS
    'Summary JSON with original_record stripped from all timeline/category events. '
    'Served by default (include_records=false). Populated on every cache write.';
