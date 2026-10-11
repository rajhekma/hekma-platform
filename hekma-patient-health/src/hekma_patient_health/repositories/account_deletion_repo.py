"""MySQL + Postgres persistence for staged account deletion + PHI archive purge."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..awsutils.mysql_db_connection import mysql_connection
from ..awsutils.postgresql_utils import pg_transaction

logger = logging.getLogger(__name__)

# Non-PHI / operational app data purged immediately (step 3).
_PG_NON_PHI_TABLES: Tuple[str, ...] = (
    "medication_notification_log",
    "patient_device_tokens",
    "ehr_summary_cache",
    "fasten_controller",
)

# PHI / clinical tables — locked on request, hard-deleted only after retention (step 6).
_PG_PHI_PATIENT_ID_TABLES: Tuple[str, ...] = (
    "medications",
    "prescriptions",
    "condition",
    "allergy",
    "medication_order",
    "immunization",
    "observation",
    "procedure",
)

_PG_PHI_ID_KEY_TABLES: Tuple[str, ...] = (
    "patient",
    "healthkit",
)

_PG_ARCHIVE_PATIENT_ID_TABLES: Tuple[str, ...] = (
    "medications",
    "prescriptions",
    "condition",
    "allergy",
    "medication_order",
    "immunization",
    "observation",
    "procedure",
    "hekma_fhir_link",
)

_PG_ARCHIVE_EMAIL_COLUMNS = {
    "condition": "hekma_mail",
    "allergy": "hekma_mail",
    "medication_order": "hekma_mail",
    "immunization": "hekma_mail",
    "observation": "hekma_mail",
    "procedure": "hekma_mail",
}

_PG_ARCHIVE_ID_TABLES: Tuple[str, ...] = (
    "patient",
    "healthkit",
)

_PG_ARCHIVE_MED_CHILD_TABLES: Tuple[str, ...] = (
    "medication_reminders",
    "medication_history",
    "medication_daily_counts",
)

_MYSQL_SCAN_TABLES: Tuple[str, ...] = (
    "clinical_document_scans",
    "allergy_scans",
)

_MYSQL_SOFT_DELETE_VARCHAR = (
    ("Allergies", "patientId"),
    ("Procedures", "patientId"),
    ("MedicalCondition", "patientId"),
)
_MYSQL_SOFT_DELETE_INT = (
    ("LabReports", "patientId"),
    ("Vitalsign", "patientId"),
    ("Immunization", "patientId"),
)


class AccountDeletionRepository:
    """Immediate archive (steps 1–5) and delayed PHI hard purge (step 6)."""

    def get_patient_by_id(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Load Patient row by numeric/string patientId."""
        sql = (
            "SELECT patientId, subjectId, email, firstName, lastName, status "
            "FROM Patient WHERE CAST(patientId AS CHAR) = %s LIMIT 1"
        )
        with mysql_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, (str(patient_id).strip(),))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_patient_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Load Patient by email (case-insensitive)."""
        sql = (
            "SELECT patientId, subjectId, email, firstName, lastName, status "
            "FROM Patient WHERE LOWER(TRIM(email)) = LOWER(TRIM(%s)) LIMIT 1"
        )
        with mysql_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, (email.strip(),))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_auth_user(
        self, *, patient_id: Optional[str] = None, email: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Load AUTH_USER_DETAILS by sponsorAccountUserId or email/login id."""
        clauses: List[str] = []
        params: List[Any] = []
        if patient_id:
            clauses.append("CAST(sponsorAccountUserId AS CHAR) = %s")
            params.append(str(patient_id).strip())
        if email:
            clauses.append("LOWER(TRIM(emailId)) = LOWER(TRIM(%s))")
            params.append(email.strip())
            clauses.append("LOWER(TRIM(userLoginId)) = LOWER(TRIM(%s))")
            params.append(email.strip())
        if not clauses:
            return None
        sql = (
            "SELECT sponsorAccountUserId, emailId, userLoginId, passwordHash, "
            "activatedInd FROM AUTH_USER_DETAILS WHERE "
            + " OR ".join(clauses)
            + " LIMIT 1"
        )
        with mysql_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
            return dict(row) if row else None

    def archive_account_on_deletion_request(
        self,
        *,
        patient_id: str,
        email: Optional[str],
        reason: Optional[str],
        retention_years: int,
        retention_days: int,
    ) -> Dict[str, Any]:
        """
        Steps 1–5: revoke access, purge non-PHI, lock PHI archive, write audit.

        PHI clinical rows stay stored but inaccessible until scheduled purge.
        """
        patient_id = str(patient_id).strip()
        now = datetime.now(timezone.utc)
        purge_eligible_at = now + timedelta(days=max(int(retention_days), 0))
        subject_id = None
        original_email = email

        with mysql_connection() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT patientId, subjectId, email, status FROM Patient "
                "WHERE CAST(patientId AS CHAR) = %s LIMIT 1",
                (patient_id,),
            )
            patient = cur.fetchone()
            if not patient:
                raise LookupError("patient_not_found")
            status = str(patient.get("status") or "").upper()
            if status in ("DELETED", "ARCHIVED"):
                raise LookupError("already_deleted")

            subject_id = patient.get("subjectId")
            auth = self.get_auth_user(patient_id=patient_id)
            auth_email = (auth.get("emailId") or auth.get("userLoginId") or "").strip() if auth else ""
            original_email = auth_email or (patient.get("email") or "").strip() or email
            locked_email = f"archived+{patient_id}@deleted.hekma.local"
            reason_text = (reason or "").strip()[:500] or None

            # Profile contact scrubbed for Play; clinical PHI stays in other tables.
            self._lock_patient_profile(
                cur, patient_id, locked_email, reason_text, now
            )
            # Non-PHI contacts removed immediately.
            cur.execute(
                "DELETE FROM PatientContact WHERE CAST(patientId AS CHAR) = %s",
                (patient_id,),
            )
            # Revoke login / deactivate auth credentials.
            cur.execute(
                "DELETE FROM AUTH_USER_DETAILS WHERE CAST(sponsorAccountUserId AS CHAR) = %s",
                (patient_id,),
            )
            # Lock clinical modules from app reads (soft-delete); do not hard-delete PHI.
            self._soft_delete_mysql_clinical(cur, patient_id)
            self._soft_delete_mysql_scans(cur, patient_id)
            self._write_audit_log(
                cur,
                patient_id,
                reason_text,
                now,
                note_prefix=(
                    "Patient account deletion requested; PHI archived until "
                    f"{purge_eligible_at.date().isoformat()}"
                ),
            )
            conn.commit()

        non_phi_purged = self._purge_postgres_tables(
            tables=_PG_NON_PHI_TABLES,
            patient_id=patient_id,
            subject_id=subject_id,
            email=original_email,
            also_by_mail=False,
        )
        self._archive_postgres_phi(
            patient_id=patient_id,
            subject_id=subject_id,
            locked_email=locked_email,
            now=now,
        )
        self._ensure_archive_ledger(
            patient_id=patient_id,
            subject_id=subject_id,
            original_email=original_email,
            reason=reason_text,
            requested_at=now,
            purge_eligible_at=purge_eligible_at,
            retention_years=int(retention_years),
        )

        return {
            "patientId": patient_id,
            "subjectId": subject_id,
            "email": original_email,
            "deletedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "phiPurgeEligibleAt": purge_eligible_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "phiRetentionYears": int(retention_years),
            "nonPhiTablesPurged": non_phi_purged,
            "flow": [
                "DELETE_REQUEST",
                "REVOKE_AND_DEACTIVATE",
                "PURGE_NON_PHI",
                "ARCHIVE_PHI",
                "AUDIT_LOG",
                "SCHEDULED_PURGE_PENDING",
            ],
        }

    def purge_due_archived_phi(
        self, *, limit: int = 100, retention_years: int
    ) -> Dict[str, Any]:
        """Step 6: hard-delete PHI for archives whose retention window has elapsed."""
        due = self._list_due_archives(limit=limit)
        purged: List[str] = []
        errors: List[Dict[str, str]] = []

        for row in due:
            patient_id = str(row["patient_id"])
            try:
                self._hard_purge_phi_for_patient(
                    patient_id=patient_id,
                    subject_id=row.get("subject_id"),
                )
                self._mark_archive_purged(patient_id=patient_id)
                purged.append(patient_id)
            except Exception as exc:
                logger.exception("Scheduled PHI purge failed patient_id=%s", patient_id)
                errors.append({"patientId": patient_id, "error": str(exc)[:200]})

        return {
            "checked": len(due),
            "purgedPatientIds": purged,
            "errors": errors,
            "retentionYears": int(retention_years),
        }

    def _lock_patient_profile(
        self,
        cur,
        patient_id: str,
        locked_email: str,
        reason: Optional[str],
        now: datetime,
    ) -> None:
        """Mark profile deleted/archived and remove login-facing contact fields."""
        has_deleted_ts = self._has_patient_column("deletedTs")
        has_deletion_reason = self._has_patient_column("deletionReason")
        has_modified_ts = self._has_patient_column("modifiedTs")

        sets = [
            "status = 'DELETED'",
            "firstName = 'DELETED'",
            "middleName = NULL",
            "lastName = 'DELETED'",
            "email = %s",
            "phone = NULL",
            "address1 = NULL",
            "address2 = NULL",
            "city = NULL",
            "state = NULL",
            "zip = NULL",
            "deactivationReason = NULL",
        ]
        params: List[Any] = [locked_email]

        for optional_null_col in ("gender", "dob", "ethnicity", "height", "weight", "language"):
            if self._has_patient_column(optional_null_col):
                sets.append(f"{optional_null_col} = NULL")

        if has_deletion_reason:
            sets.append("deletionReason = %s")
            params.append(reason)
        if has_deleted_ts:
            sets.append("deletedTs = %s")
            params.append(now.replace(tzinfo=None))
        if self._has_patient_column("deactivatedTs"):
            sets.append("deactivatedTs = NULL")
        if has_modified_ts:
            sets.append("modifiedTs = %s")
            params.append(now.replace(tzinfo=None))

        params.append(patient_id)
        sql = f"UPDATE Patient SET {', '.join(sets)} WHERE CAST(patientId AS CHAR) = %s"
        cur.execute(sql, tuple(params))

    def _soft_delete_mysql_clinical(self, cur, patient_id: str) -> None:
        """Lock MySQL clinical modules from app queries without destroying PHI."""
        for table, col in _MYSQL_SOFT_DELETE_VARCHAR:
            try:
                cur.execute(
                    f"UPDATE {table} SET is_deleted = 'Y' "
                    f"WHERE CAST({col} AS CHAR) = %s",
                    (patient_id,),
                )
            except Exception:
                logger.warning("Clinical lock skipped for %s", table, exc_info=True)
        for table, col in _MYSQL_SOFT_DELETE_INT:
            try:
                cur.execute(
                    f"UPDATE {table} SET is_deleted = 1 "
                    f"WHERE CAST({col} AS CHAR) = %s",
                    (patient_id,),
                )
            except Exception:
                logger.warning("Clinical lock skipped for %s", table, exc_info=True)

    def _soft_delete_mysql_scans(self, cur, patient_id: str) -> None:
        """Hide scan documents that still surface in the app after deletion."""
        for table in _MYSQL_SCAN_TABLES:
            try:
                cur.execute(
                    f"UPDATE {table} SET is_deleted = 1 "
                    f"WHERE CAST(patient_id AS CHAR) = %s",
                    (patient_id,),
                )
            except Exception:
                logger.warning("Scan lock skipped for %s", table, exc_info=True)

    def _archive_postgres_phi(
        self,
        *,
        patient_id: str,
        subject_id: Optional[str],
        locked_email: str,
        now: datetime,
    ) -> None:
        """Tombstone email and set archived_at on Postgres PHI for this patient only."""
        ids = {str(patient_id)}
        if subject_id:
            ids.add(str(subject_id))
        id_list = sorted(ids)
        archived_at = now
        try:
            with pg_transaction(dict_cursor=True) as (_, cur):
                self._ensure_archived_at_columns(cur)
                for table in self._list_fastenhealth_tables(cur):
                    self._archive_table_rows(
                        cur,
                        table,
                        id_column="patient_id",
                        id_list=id_list,
                        locked_email=locked_email,
                        email_column="hekma_mail_id",
                        archived_at=archived_at,
                        extra_sets=None,
                    )
                for table in _PG_ARCHIVE_PATIENT_ID_TABLES:
                    self._archive_table_rows(
                        cur,
                        table,
                        id_column="patient_id",
                        id_list=id_list,
                        locked_email=locked_email,
                        email_column=_PG_ARCHIVE_EMAIL_COLUMNS.get(table),
                        archived_at=archived_at,
                        extra_sets=None,
                    )
                for table in _PG_ARCHIVE_ID_TABLES:
                    extra = None
                    if table == "patient":
                        extra = [
                            "given_name = 'DELETED'",
                            "family_name = 'DELETED'",
                        ]
                    self._archive_table_rows(
                        cur,
                        table,
                        id_column="id",
                        id_list=id_list,
                        locked_email=locked_email,
                        email_column="hekma_mail" if table == "patient" else None,
                        archived_at=archived_at,
                        extra_sets=extra,
                    )
                self._archive_medication_children(cur, id_list, archived_at)
        except Exception:
            logger.warning(
                "Postgres PHI archive failed patient_id=%s",
                patient_id,
                exc_info=True,
            )

    def _ensure_archived_at_columns(self, cur) -> None:
        tables = list(_PG_ARCHIVE_PATIENT_ID_TABLES) + list(_PG_ARCHIVE_ID_TABLES)
        tables.extend(_PG_ARCHIVE_MED_CHILD_TABLES)
        tables.extend(self._list_fastenhealth_tables(cur))
        for table in tables:
            if not self._pg_table_exists(cur, table):
                continue
            try:
                cur.execute(
                    f'ALTER TABLE "{table}" '
                    "ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL"
                )
            except Exception:
                logger.warning(
                    "Could not add archived_at to %s", table, exc_info=True
                )

    @staticmethod
    def _list_fastenhealth_tables(cur) -> List[str]:
        cur.execute(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename LIKE 'fastenhealth\\_%' "
            "ESCAPE '\\' ORDER BY tablename"
        )
        names = []
        for row in cur.fetchall() or []:
            if isinstance(row, dict):
                names.append(row["tablename"])
            else:
                names.append(row[0])
        return names

    def _archive_table_rows(
        self,
        cur,
        table: str,
        *,
        id_column: str,
        id_list: Sequence[str],
        locked_email: str,
        email_column: Optional[str],
        archived_at: datetime,
        extra_sets: Optional[List[str]],
    ) -> None:
        if not self._pg_table_exists(cur, table):
            return
        placeholders = ",".join(["%s"] * len(id_list))
        sets = ["archived_at = %s"]
        params: List[Any] = [archived_at]
        if email_column and self._pg_column_exists(cur, table, email_column):
            sets.append(f"{email_column} = %s")
            params.append(locked_email)
        if extra_sets:
            sets.extend(extra_sets)
        params.extend(id_list)
        try:
            cur.execute(
                f'UPDATE "{table}" SET {", ".join(sets)} '
                f"WHERE {id_column} IN ({placeholders})",
                tuple(params),
            )
        except Exception:
            logger.warning("Postgres archive skipped table=%s", table, exc_info=True)

    def _archive_medication_children(
        self, cur, id_list: Sequence[str], archived_at: datetime
    ) -> None:
        if not self._pg_table_exists(cur, "medications"):
            return
        placeholders = ",".join(["%s"] * len(id_list))
        for table in _PG_ARCHIVE_MED_CHILD_TABLES:
            if not self._pg_table_exists(cur, table):
                continue
            try:
                cur.execute(
                    f'UPDATE "{table}" child SET archived_at = %s '
                    "FROM medications m "
                    f"WHERE child.medication_id = m.id "
                    f"AND m.patient_id IN ({placeholders})",
                    tuple([archived_at, *id_list]),
                )
            except Exception:
                logger.warning(
                    "Postgres archive skipped child table=%s", table, exc_info=True
                )

    @staticmethod
    def _pg_column_exists(cur, table: str, column_name: str) -> bool:
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
            (table, column_name),
        )
        return cur.fetchone() is not None

    def _write_audit_log(
        self,
        cur,
        patient_id: str,
        reason: Optional[str],
        now: datetime,
        *,
        note_prefix: str,
    ) -> None:
        """Immutable deletion-request audit entry (step 5)."""
        note = note_prefix
        if reason:
            note = f"{note}. Reason: {reason[:200]}"
        try:
            cur.execute(
                "INSERT INTO AuditLog (buArea, buId, type, userId, note, `timestamp`) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    "Patient",
                    patient_id,
                    "AccountDeletion",
                    patient_id,
                    note,
                    now.replace(tzinfo=None),
                ),
            )
        except Exception:
            logger.warning("AuditLog insert skipped for patient deletion", exc_info=True)

    def _ensure_archive_ledger(
        self,
        *,
        patient_id: str,
        subject_id: Optional[str],
        original_email: Optional[str],
        reason: Optional[str],
        requested_at: datetime,
        purge_eligible_at: datetime,
        retention_years: int,
    ) -> None:
        email_hash = None
        if original_email:
            email_hash = hashlib.sha256(original_email.strip().lower().encode()).hexdigest()
        try:
            with pg_transaction(dict_cursor=True) as (_, cur):
                if not self._pg_table_exists(cur, "account_deletion_archive"):
                    logger.warning("account_deletion_archive missing; ledger not written")
                    return
                cur.execute(
                    "INSERT INTO account_deletion_archive ("
                    "patient_id, subject_id, original_email_hash, reason, status, "
                    "requested_at, purge_eligible_at, retention_years, audit_note, updated_at"
                    ") VALUES (%s, %s, %s, %s, 'ARCHIVED', %s, %s, %s, %s, NOW()) "
                    "ON CONFLICT (patient_id) DO UPDATE SET "
                    "status = 'ARCHIVED', "
                    "subject_id = EXCLUDED.subject_id, "
                    "original_email_hash = EXCLUDED.original_email_hash, "
                    "reason = EXCLUDED.reason, "
                    "requested_at = EXCLUDED.requested_at, "
                    "purge_eligible_at = EXCLUDED.purge_eligible_at, "
                    "retention_years = EXCLUDED.retention_years, "
                    "purged_at = NULL, "
                    "audit_note = EXCLUDED.audit_note, "
                    "updated_at = NOW()",
                    (
                        patient_id,
                        subject_id,
                        email_hash,
                        reason,
                        requested_at,
                        purge_eligible_at,
                        retention_years,
                        "PHI locked pending scheduled purge",
                    ),
                )
        except Exception:
            logger.warning("Archive ledger upsert failed", exc_info=True)

    def _list_due_archives(self, *, limit: int) -> List[Dict[str, Any]]:
        try:
            with pg_transaction(dict_cursor=True) as (_, cur):
                if not self._pg_table_exists(cur, "account_deletion_archive"):
                    return []
                cur.execute(
                    "SELECT patient_id, subject_id, purge_eligible_at "
                    "FROM account_deletion_archive "
                    "WHERE status = 'ARCHIVED' AND purge_eligible_at <= NOW() "
                    "ORDER BY purge_eligible_at ASC LIMIT %s",
                    (max(int(limit), 1),),
                )
                return [dict(r) for r in cur.fetchall()]
        except Exception:
            logger.warning("Failed listing due PHI archives", exc_info=True)
            return []

    def _mark_archive_purged(self, *, patient_id: str) -> None:
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                "UPDATE account_deletion_archive "
                "SET status = 'PURGED', purged_at = NOW(), updated_at = NOW() "
                "WHERE patient_id = %s AND status = 'ARCHIVED'",
                (patient_id,),
            )

    def _hard_purge_phi_for_patient(
        self, *, patient_id: str, subject_id: Optional[str]
    ) -> None:
        """Hard-delete archived PHI after retention (MySQL clinical + Postgres PHI)."""
        with mysql_connection() as conn:
            cur = conn.cursor()
            for table, col in list(_MYSQL_SOFT_DELETE_VARCHAR) + list(_MYSQL_SOFT_DELETE_INT):
                try:
                    cur.execute(
                        f"DELETE FROM {table} WHERE CAST({col} AS CHAR) = %s",
                        (patient_id,),
                    )
                except Exception:
                    logger.warning("Hard purge skipped MySQL %s", table, exc_info=True)
            for table in ("clinical_document_scans", "allergy_scans"):
                try:
                    cur.execute(
                        f"DELETE FROM {table} WHERE CAST(patient_id AS CHAR) = %s",
                        (patient_id,),
                    )
                except Exception:
                    logger.warning("Hard purge skipped MySQL %s", table, exc_info=True)
            conn.commit()

        self._purge_postgres_tables(
            tables=_PG_PHI_PATIENT_ID_TABLES,
            patient_id=patient_id,
            subject_id=subject_id,
            email=None,
            also_by_mail=False,
        )
        self._purge_postgres_id_tables(
            tables=_PG_PHI_ID_KEY_TABLES,
            patient_id=patient_id,
            subject_id=subject_id,
        )

        with mysql_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO AuditLog (buArea, buId, type, userId, note, `timestamp`) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        "Patient",
                        patient_id,
                        "AccountDeletionPhiPurge",
                        patient_id,
                        "Scheduled PHI hard purge completed after retention window",
                        datetime.now(timezone.utc).replace(tzinfo=None),
                    ),
                )
                conn.commit()
            except Exception:
                logger.warning("PHI purge audit insert skipped", exc_info=True)

    def _purge_postgres_tables(
        self,
        *,
        tables: Sequence[str],
        patient_id: str,
        subject_id: Optional[str],
        email: Optional[str],
        also_by_mail: bool,
    ) -> List[str]:
        touched: List[str] = []
        ids = {str(patient_id)}
        if subject_id:
            ids.add(str(subject_id))
        id_list = sorted(ids)
        try:
            with pg_transaction(dict_cursor=True) as (_, cur):
                for table in tables:
                    if not self._pg_table_exists(cur, table):
                        continue
                    if self._delete_by_patient_id(cur, table, id_list):
                        touched.append(table)
                    if also_by_mail and email:
                        if self._delete_by_hekma_mail(cur, table, email):
                            if table not in touched:
                                touched.append(table)
        except Exception:
            logger.warning(
                "Postgres purge failed patient_id=%s tables=%s",
                patient_id,
                tables,
                exc_info=True,
            )
        return touched

    def _purge_postgres_id_tables(
        self,
        *,
        tables: Sequence[str],
        patient_id: str,
        subject_id: Optional[str],
    ) -> List[str]:
        touched: List[str] = []
        ids = {str(patient_id)}
        if subject_id:
            ids.add(str(subject_id))
        id_list = sorted(ids)
        try:
            with pg_transaction(dict_cursor=True) as (_, cur):
                for table in tables:
                    if not self._pg_table_exists(cur, table):
                        continue
                    if self._delete_by_id(cur, table, id_list):
                        touched.append(table)
        except Exception:
            logger.warning(
                "Postgres id-key purge failed patient_id=%s", patient_id, exc_info=True
            )
        return touched

    @staticmethod
    def _pg_table_exists(cur, table: str) -> bool:
        cur.execute(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s"
            ") AS exists",
            (table,),
        )
        row = cur.fetchone()
        return bool(row["exists"] if isinstance(row, dict) else row[0])

    @staticmethod
    def _delete_by_patient_id(cur, table: str, id_list: Sequence[str]) -> bool:
        placeholders = ",".join(["%s"] * len(id_list))
        try:
            cur.execute(
                f'DELETE FROM "{table}" WHERE patient_id IN ({placeholders})',
                tuple(id_list),
            )
            return cur.rowcount > 0
        except Exception:
            logger.warning("Postgres purge skipped table=%s", table, exc_info=True)
            return False

    @staticmethod
    def _delete_by_id(cur, table: str, id_list: Sequence[str]) -> bool:
        placeholders = ",".join(["%s"] * len(id_list))
        try:
            cur.execute(
                f'DELETE FROM "{table}" WHERE id IN ({placeholders})',
                tuple(id_list),
            )
            return cur.rowcount > 0
        except Exception:
            logger.warning("Postgres purge skipped table=%s", table, exc_info=True)
            return False

    @staticmethod
    def _delete_by_hekma_mail(cur, table: str, email: str) -> bool:
        try:
            cur.execute(
                f'DELETE FROM "{table}" WHERE LOWER(TRIM(hekma_mail)) = LOWER(TRIM(%s))',
                (email,),
            )
            return cur.rowcount > 0
        except Exception:
            logger.warning(
                "Postgres hekma_mail purge skipped table=%s", table, exc_info=True
            )
            return False

    def _has_patient_column(self, column_name: str) -> bool:
        cache_attr = f"_col_{column_name}"
        cached = getattr(self, cache_attr, None)
        if cached is not None:
            return cached
        present = False
        try:
            with mysql_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Patient' "
                    "AND COLUMN_NAME = %s",
                    (column_name,),
                )
                row = cur.fetchone()
                present = bool(row and row[0] > 0)
        except Exception:
            logger.warning(
                "Could not detect Patient.%s column; treating as absent",
                column_name,
                exc_info=True,
            )
            present = False
        setattr(self, cache_attr, present)
        return present
