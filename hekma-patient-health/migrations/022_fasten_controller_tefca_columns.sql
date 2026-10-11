-- Extend fasten_controller for TEFCA connection tracking and export status.
ALTER TABLE fasten_controller
    ADD COLUMN IF NOT EXISTS org_connection_id TEXT,
    ADD COLUMN IF NOT EXISTS tefca_directory_id TEXT,
    ADD COLUMN IF NOT EXISTS export_status TEXT,
    ADD COLUMN IF NOT EXISTS failure_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_fasten_controller_org_connection_id
    ON fasten_controller (org_connection_id)
    WHERE org_connection_id IS NOT NULL;

COMMENT ON COLUMN fasten_controller.tefca_directory_id IS
    'TEFCA Directory ID from widget.complete or patient.connection_success (when present).';
COMMENT ON COLUMN fasten_controller.export_status IS
    'Export lifecycle: initiated, success, failed.';
COMMENT ON COLUMN fasten_controller.failure_reason IS
    'Fasten patient.ehi_export_failed failure_reason enum value.';
