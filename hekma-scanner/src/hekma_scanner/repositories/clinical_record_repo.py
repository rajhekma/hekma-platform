"""
ClinicalRecordRepo
==================
Generic CRUD repository for all 6 clinical record tables.

Key design decisions:
  - _DELETE_STYLE handles is_deleted column type inconsistency per table
    (LabReports/Vitalsign/Immunization: integer 0/1)
    (Allergies/Procedures/MedicalCondition: varchar 'Y'/'N' with possible NULL)
  - _active_where() auto-generates the correct WHERE clause per table type
  - Ownership always enforced via patientId column in every query
  - update() builds SET clause dynamically — only updates provided non-None fields
"""
from typing import Any, Dict, List, Optional
from ..awsutils.mysql_db_connection import mysql_connection


# Maps service module key → MySQL table name
_TABLE_MAP: Dict[str, str] = {
    "allergies":    "Allergies",
    "lab_reports":  "LabReports",
    "vital_signs":  "Vitalsign",
    "immunization": "Immunization",
    "procedures":   "Procedures",
    "diagnosis":    "MedicalCondition",
}

# Maps table → (is_deleted column, deleted value, active value, is varchar)
_DELETE_STYLE: Dict[str, tuple] = {
    "Allergies":        ("is_deleted", "Y", "N", True),   # varchar, NULL possible
    "LabReports":       ("is_deleted",  1,   0,  False),  # integer
    "Vitalsign":        ("is_deleted",  1,   0,  False),  # integer
    "Immunization":     ("is_deleted",  1,   0,  False),  # integer
    "Procedures":       ("is_deleted", "Y", "N", True),   # varchar, NULL possible
    "MedicalCondition": ("is_deleted", "Y", "N", True),   # varchar, NULL possible
}

# Patient foreign key column name per table (all currently patientId)
_PATIENT_COL: Dict[str, str] = {
    "Allergies":        "patientId",
    "LabReports":       "patientId",
    "Vitalsign":        "patientId",
    "Immunization":     "patientId",
    "Procedures":       "patientId",
    "MedicalCondition": "patientId",
}

# ORDER BY clause per table — most recent first
_ORDER_BY: Dict[str, str] = {
    "Allergies":        "startDate DESC, id DESC",
    "LabReports":       "resultDate DESC, id DESC",
    "Vitalsign":        "dateOfObservation DESC, id DESC",
    "Immunization":     "vaccinationDate DESC, id DESC",
    "Procedures":       "startDate DESC, id DESC",
    "MedicalCondition": "startDate DESC, id DESC",
}


class ClinicalRecordRepo:
    """Generic CRUD repository — instantiated once per module in dependencies.py."""

    def __init__(self, module: str):
        self._table    = _TABLE_MAP[module]
        col, del_val, act_val, is_varchar = _DELETE_STYLE[self._table]
        self._del_col  = col
        self._del_val  = del_val
        self._act_val  = act_val
        self._varchar  = is_varchar
        self._pat_col  = _PATIENT_COL[self._table]
        self._order    = _ORDER_BY[self._table]

    def _active_where(self) -> str:
        """Generate correct NOT-DELETED WHERE clause for this table's column type (NULL-safe)."""
        if self._varchar:
            # NULL-safe: some rows may have is_deleted=NULL meaning active
            return f"({self._del_col} IS NULL OR {self._del_col} != 'Y')"
        return f"({self._del_col} IS NULL OR {self._del_col} = 0)"

    def list_for_patient(
        self, patient_id: str, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        sql = (
            f"SELECT * FROM {self._table} "
            f"WHERE {self._pat_col} = %s AND {self._active_where()} "
            f"ORDER BY {self._order} LIMIT %s OFFSET %s"
        )
        with mysql_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, (patient_id, limit, offset))
            return [dict(r) for r in cur.fetchall()]

    def get_by_id(
        self, patient_id: str, record_id: int
    ) -> Optional[Dict[str, Any]]:
        sql = (
            f"SELECT * FROM {self._table} "
            f"WHERE id = %s AND {self._pat_col} = %s AND {self._active_where()}"
        )
        with mysql_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, (record_id, patient_id))
            row = cur.fetchone()
            return dict(row) if row else None

    def soft_delete(self, patient_id: str, record_id: int) -> bool:
        """Soft-delete: set is_deleted to the deleted value for this table's type."""
        sql = (
            f"UPDATE {self._table} SET {self._del_col} = %s "
            f"WHERE id = %s AND {self._pat_col} = %s AND {self._active_where()}"
        )
        with mysql_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, (self._del_val, record_id, patient_id))
            conn.commit()
            return cur.rowcount > 0

    def update(
        self, patient_id: str, record_id: int, fields: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Generic update — builds SET clause from non-None field values.
        Used as fallback; specialized update functions in ctms_clinical_repo.py
        are preferred for modules that have complex field mapping.
        """
        non_none = {k: v for k, v in fields.items() if v is not None}
        if not non_none:
            # No fields to update — return current record unchanged
            return self.get_by_id(patient_id, record_id)
        set_clause = ", ".join(f"{k} = %s" for k in non_none)
        sql = (
            f"UPDATE {self._table} SET {set_clause} "
            f"WHERE id = %s AND {self._pat_col} = %s AND {self._active_where()}"
        )
        with mysql_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, (*non_none.values(), record_id, patient_id))
            conn.commit()
            if cur.rowcount == 0:
                return None
            cur.execute(f"SELECT * FROM {self._table} WHERE id = %s", (record_id,))
            row = cur.fetchone()
            return dict(row) if row else None
