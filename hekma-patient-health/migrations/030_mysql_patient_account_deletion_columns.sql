-- Optional Patient columns for permanent account deletion audit fields.
-- MySQL 8 may not support ADD COLUMN IF NOT EXISTS; apply manually if missing.
-- The deletion API detects these columns at runtime and falls back safely.

-- ALTER TABLE Patient ADD COLUMN deletionReason VARCHAR(500) NULL;
-- ALTER TABLE Patient ADD COLUMN deletedTs DATETIME NULL;

SET @db := DATABASE();

SET @sql := (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE Patient ADD COLUMN deletionReason VARCHAR(500) NULL',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'Patient' AND COLUMN_NAME = 'deletionReason'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE Patient ADD COLUMN deletedTs DATETIME NULL',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'Patient' AND COLUMN_NAME = 'deletedTs'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
