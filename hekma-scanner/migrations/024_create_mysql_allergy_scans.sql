-- DEPRECATED / SUPERSEDED by 025_create_mysql_clinical_document_scans.sql
-- Table `clinical_document_scans` handles all document scans across all 6 clinical modules (including allergies).
-- DDL Migration for MySQL allergy_scans table (Legacy standalone allergy scans)
CREATE TABLE IF NOT EXISTS allergy_scans (
  id INT AUTO_INCREMENT PRIMARY KEY,
  patient_id VARCHAR(255) NOT NULL,
  image_path TEXT NOT NULL,
  scanned_at BIGINT NOT NULL,
  prescriber_name VARCHAR(255),
  prescription_date VARCHAR(50),
  extracted_data JSON,
  document_type VARCHAR(100) DEFAULT 'allergy_report',
  content_hash VARCHAR(64) DEFAULT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_patient_id (patient_id),
  UNIQUE KEY uq_allergy_scans_patient_content_hash (patient_id, content_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
