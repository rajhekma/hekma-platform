import json
from datetime import date, datetime, timezone
from typing import Any, Optional

from mysql.connector import IntegrityError

from ..awsutils.mysql_db_connection import mysql_connection

_table_checked = False


class ScanHashConflictError(Exception):
    """Raised when (patient, module, content_hash) already exists in MySQL."""

    def __init__(
        self,
        patient_id: str,
        module: str,
        existing_scan_id: int = 0,
        existing: Optional[dict] = None,
    ):
        super().__init__(
            f"Duplicate clinical scan hash for patient={patient_id} module={module}"
        )
        self.patient_id = patient_id
        self.module = module
        self.existing_scan_id = existing_scan_id
        self.existing = existing


def _ensure_table_exists(cur) -> None:
    global _table_checked
    if _table_checked:
        return
    cur.execute(
        """
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
          is_deleted INT DEFAULT 0,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          KEY idx_clinical_scans_patient (patient_id),
          KEY idx_clinical_scans_module (patient_id, module),
          UNIQUE KEY uq_clinical_scans_patient_module_hash (patient_id, module, content_hash)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    try:
        cur.execute("ALTER TABLE clinical_document_scans ADD COLUMN is_deleted INT DEFAULT 0")
    except Exception:
        pass
    _table_checked = True


def _to_epoch_ms(value: Any) -> Optional[int]:
    """Convert created_at (datetime/date/ISO string) to epoch milliseconds for scannedAt."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    if isinstance(value, date):
        dt = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    if isinstance(value, (int, float)):
        # Already epoch seconds or ms — treat large values as ms.
        n = int(value)
        return n if n > 10_000_000_000 else n * 1000
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    return None


def _format_row(row: Optional[dict]) -> Optional[dict]:
    """Normalize DB row and add camelCase / scannedAt aliases for existing mobile UI."""
    if not row:
        return None
    res = dict(row)
    extracted = res.get("extracted_data")
    if isinstance(extracted, str):
        try:
            res["extracted_data"] = json.loads(extracted)
        except Exception:
            pass
    created = res.get("created_at")
    if isinstance(created, (datetime, date)):
        res["created_at"] = created.isoformat()

    # Legacy UI fields (keep snake_case keys too for newer clients).
    res["scannedAt"] = _to_epoch_ms(created if created is not None else res.get("created_at"))
    res["patientId"] = res.get("patient_id")
    res["imageUrl"] = res.get("image_path")
    res["documentDate"] = res.get("document_date")
    res["providerName"] = res.get("provider_name")
    res["extractedData"] = res.get("extracted_data")
    res["documentType"] = res.get("document_type")
    res["contentHash"] = res.get("content_hash")
    res["createdAt"] = res.get("created_at")
    res["isDeleted"] = res.get("is_deleted")
    return res


def create_clinical_scan(patient_id: str, module: str, data: dict) -> dict:
    """Insert a scan row; unique hash collisions become ClinicalScanAlreadyExistsError."""
    extracted = data.get("extractedData")
    extracted_json = json.dumps(extracted) if extracted is not None else None
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        _ensure_table_exists(cur)
        try:
            cur.execute(
                """
                INSERT INTO clinical_document_scans (
                    patient_id, module, image_path, document_date,
                    provider_name, extracted_data, document_type, content_hash, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    patient_id,
                    module,
                    data.get("imageUrl") or data.get("sourceUrl") or "upload://unknown",
                    data.get("documentDate") or data.get("prescriptionDate"),
                    data.get("providerName") or data.get("prescriberName"),
                    extracted_json,
                    data.get("documentType", "clinical_document"),
                    data.get("contentHash"),
                ),
            )
            conn.commit()
            cur.execute("SELECT * FROM clinical_document_scans WHERE id = %s", (cur.lastrowid,))
            return _format_row(cur.fetchone())
        except IntegrityError as exc:
            conn.rollback()
            existing = get_clinical_scan_by_hash(
                patient_id,
                module,
                data.get("contentHash") or "",
                include_deleted=True,
            )
            raise ScanHashConflictError(
                patient_id=patient_id,
                module=module,
                existing_scan_id=int((existing or {}).get("id") or 0),
                existing=existing,
            ) from exc


def get_clinical_scan(scan_id: int) -> Optional[dict]:
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        _ensure_table_exists(cur)
        cur.execute("SELECT * FROM clinical_document_scans WHERE id = %s", (scan_id,))
        return _format_row(cur.fetchone())


def get_clinical_scans_by_patient(patient_id: str, module: Optional[str] = None):
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        _ensure_table_exists(cur)
        if module:
            cur.execute(
                """
                SELECT * FROM clinical_document_scans
                WHERE patient_id = %s AND module = %s
                  AND (is_deleted IS NULL OR is_deleted = 0)
                ORDER BY created_at DESC, id DESC
                """,
                (patient_id, module),
            )
        else:
            cur.execute(
                """
                SELECT * FROM clinical_document_scans
                WHERE patient_id = %s
                  AND (is_deleted IS NULL OR is_deleted = 0)
                ORDER BY created_at DESC, id DESC
                """,
                (patient_id,),
            )
        return [_format_row(r) for r in cur.fetchall()]


def get_clinical_scan_by_hash(
    patient_id: str,
    module: Optional[str],
    content_hash: str,
    include_deleted: bool = False,
) -> Optional[dict]:
    """Find a scan by file hash. Unique key includes soft-deleted rows — use include_deleted for that."""
    if not content_hash:
        return None
    deleted_clause = "" if include_deleted else "AND (is_deleted IS NULL OR is_deleted = 0)"
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        _ensure_table_exists(cur)
        if module:
            cur.execute(
                f"""
                SELECT * FROM clinical_document_scans
                WHERE patient_id = %s AND module = %s AND content_hash = %s
                  {deleted_clause}
                ORDER BY id DESC LIMIT 1
                """,
                (patient_id, module, content_hash),
            )
        else:
            cur.execute(
                f"""
                SELECT * FROM clinical_document_scans
                WHERE patient_id = %s AND content_hash = %s
                  {deleted_clause}
                ORDER BY id DESC LIMIT 1
                """,
                (patient_id, content_hash),
            )
        return _format_row(cur.fetchone())


def find_existing_scan_by_semantic_data(
    patient_id: str, module: str, document_date: Optional[str]
) -> Optional[dict]:
    if not document_date:
        return None
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        _ensure_table_exists(cur)
        cur.execute(
            """
            SELECT * FROM clinical_document_scans
            WHERE patient_id = %s AND module = %s AND document_date = %s
              AND (is_deleted IS NULL OR is_deleted = 0)
            ORDER BY id DESC LIMIT 1
            """,
            (patient_id, module, document_date),
        )
        return _format_row(cur.fetchone())


def update_clinical_scan(scan_id: int, data: dict) -> Optional[dict]:
    extracted = data.get("extractedData")
    extracted_json = json.dumps(extracted) if extracted is not None else None
    with mysql_connection() as conn:
        cur = conn.cursor(dictionary=True)
        _ensure_table_exists(cur)
        cur.execute(
            """
            UPDATE clinical_document_scans
            SET image_path = COALESCE(%s, image_path),
                document_date = COALESCE(%s, document_date),
                provider_name = COALESCE(%s, provider_name),
                extracted_data = COALESCE(%s, extracted_data),
                content_hash = COALESCE(%s, content_hash),
                is_deleted = 0
            WHERE id = %s
            """,
            (
                data.get("imageUrl") or data.get("sourceUrl"),
                data.get("documentDate") or data.get("prescriptionDate"),
                data.get("providerName") or data.get("prescriberName"),
                extracted_json,
                data.get("contentHash"),
                scan_id,
            ),
        )
        conn.commit()
        cur.execute("SELECT * FROM clinical_document_scans WHERE id = %s", (scan_id,))
        return _format_row(cur.fetchone())


def soft_delete_clinical_scan(scan_id: int) -> bool:
    """Mark a clinical scan as deleted (soft delete — data preserved in DB)."""
    with mysql_connection() as conn:
        cur = conn.cursor()
        _ensure_table_exists(cur)
        cur.execute(
            "UPDATE clinical_document_scans SET is_deleted = 1 WHERE id = %s AND is_deleted = 0",
            (scan_id,),
        )
        conn.commit()
        return cur.rowcount > 0
