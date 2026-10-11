-- Common OCR scan metadata for all clinical modules (MySQL)
CREATE TABLE IF NOT EXISTS clinical_document_scans (
  id INT AUTO_INCREMENT PRIMARY KEY,
  patient_id VARCHAR(255) NOT NULL,
  module VARCHAR(50) NOT NULL,
  image_path TEXT NOT NULL,
  document_date VARCHAR(50) DEFAULT NULL,
  provider_name VARCHAR(255) DEFAULT NULL,
  extracted_data JSON,
  document_type VARCHAR(100) DEFAULT 'clinical_document',
  content_hash VARCHAR(64) DEFAULT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_clinical_scans_patient (patient_id),
  KEY idx_clinical_scans_module (patient_id, module),
  UNIQUE KEY uq_clinical_scans_patient_module_hash (patient_id, module, content_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
