"""
Ensure trial_gpt_ehr is populated when UI read APIs run before P2T.

LLM ingest can take 1–2 minutes; read APIs must not block (gateway timeouts).
Background ingest + poll via ehr_status or retry GET /diseases.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from config.trial_gpt_ehr_config import TrialGptEhrConfig, get_trial_gpt_ehr_config
from repositories import fastenhealth_repo, trial_gpt_ehr_repo
from repositories.trial_gpt_ehr_repo import (
    fetch_disease_list,
    fetch_icd_diseases,
    fetch_summary_text,
)
from services.trial_gpt_ehr_ingest_service import (
    TrialGptEhrIngestError,
    TrialGptEhrIngestResult,
    TrialGptEhrIngestService,
    ensure_trial_gpt_ehr_ready,
    format_worker_error,
    is_stale_ingesting_row,
    mark_worker_failure_if_still_ingesting,
    run_background_ingest_with_logging,
)
from services.trial_gpt_ehr_progress import AUTO_RETRY_COOLDOWN_SECONDS, build_ingest_progress

logger = logging.getLogger(__name__)

# Ingest older than this while still "ingesting" is treated as stale (worker died).
STALE_INGESTING_SECONDS = 180
DEFAULT_RETRY_AFTER_SECONDS = 15

_ingest_lock = threading.Lock()
_ingest_in_flight: set[int] = set()
_schema_ready = False
_schema_lock = threading.Lock()
_last_auto_retry_at: dict[int, float] = {}


def _auto_retry_cooldown_remaining(mysql_patient_id: int) -> Optional[int]:
    """Seconds until the next auto-retry is allowed; 0 if ready to retry."""
    last_retry = _last_auto_retry_at.get(mysql_patient_id)
    if last_retry is None:
        return 0
    since = time.monotonic() - last_retry
    if since >= AUTO_RETRY_COOLDOWN_SECONDS:
        return 0
    return int(AUTO_RETRY_COOLDOWN_SECONDS - since)


def _ensure_schema_once() -> None:
    """Create trial_gpt_ehr table on first read/ingest (idempotent; QA-safe)."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        trial_gpt_ehr_repo.ensure_trial_gpt_ehr_table()
        _schema_ready = True


def parse_mysql_patient_id(patient_id: str) -> int:
    """Parse API path patient_id as MySQL Patient.patientId."""
    try:
        return int(str(patient_id).strip())
    except (TypeError, ValueError) as exc:
        raise TrialGptEhrIngestError(
            "Invalid patient_id",
            status_code=400,
        ) from exc


def _fetch_disease_list(
    *,
    mysql_patient_id: int,
    subject_id: str,
    llm: bool,
) -> List[str]:
    diseases = fetch_disease_list(mysql_patient_id=mysql_patient_id, llm=llm)
    if diseases:
        return diseases
    return fetch_disease_list(subject_id=subject_id, llm=llm)


def _fetch_icd_entries(
    *,
    mysql_patient_id: int,
    subject_id: str,
    llm: bool,
) -> list:
    entries = fetch_icd_diseases(mysql_patient_id=mysql_patient_id, llm=llm)
    if entries:
        return entries
    return fetch_icd_diseases(subject_id=subject_id, llm=llm)


def _fetch_summary(
    *,
    mysql_patient_id: int,
    subject_id: str,
    llm: bool,
) -> Optional[str]:
    summary = fetch_summary_text(mysql_patient_id=mysql_patient_id, llm=llm)
    if summary:
        return summary
    return fetch_summary_text(subject_id=subject_id, llm=llm)


def _as_utc_naive(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    return None


class TrialGptEhrReadService:
    """Read trial_gpt_ehr for UI; schedule background ingest when missing."""

    def __init__(self, config: Optional[TrialGptEhrConfig] = None):
        self._config = config or get_trial_gpt_ehr_config()
        self._ingest = TrialGptEhrIngestService(config=self._config)

    @property
    def preferred_llm(self) -> bool:
        return self._config.p2t_preferred_llm

    def ensure_ready_sync(
        self,
        patient_id: str,
        *,
        trigger: str,
    ) -> TrialGptEhrIngestResult:
        """Blocking ingest (Postman / wait=true). Can take 1–2 minutes."""
        logger.info(
            "trial_gpt_ehr sync ensure | patient_id=%s | trigger=%s",
            patient_id,
            trigger,
        )
        return self._ingest.ensure_for_p2t(str(patient_id).strip())

    def get_ehr_status(self, patient_id: str) -> Dict[str, Any]:
        """Status payload for GET /api/patient/{id}/ehr-status."""
        return self.get_ingest_progress(patient_id, auto_retry=True)

    def get_ingest_progress(
        self,
        patient_id: str,
        *,
        subject_id: Optional[str] = None,
        auto_retry: bool = True,
    ) -> Dict[str, Any]:
        """
        Rich ingest progress for UI polling.

        auto_retry=True schedules background ingest when Fasten data exists but
        trial_gpt_ehr is missing, failed, or stale — avoids 503 on /diseases.
        """
        _ensure_schema_once()
        mysql_patient_id = parse_mysql_patient_id(patient_id)
        llm = self.preferred_llm

        fasten_present = fastenhealth_repo.has_clinical_data(str(mysql_patient_id))
        fasten_rows = 0
        if fasten_present:
            export_data = fastenhealth_repo.export_fasten_patient_data(
                str(mysql_patient_id),
                skip_large_tables=self._config.skip_large_tables,
            )
            fasten_rows = sum(len(rows) for rows in (export_data or {}).values())

        has_ready = self._has_ready_row(mysql_patient_id)
        row = trial_gpt_ehr_repo.fetch_ehr_status_row(
            mysql_patient_id=mysql_patient_id,
            llm=llm,
        )

        retry_scheduled = False
        if auto_retry and not has_ready and fasten_present:
            retry_scheduled = self._maybe_auto_retry_ingest(
                patient_id=patient_id,
                subject_id=subject_id,
                mysql_patient_id=mysql_patient_id,
                summary_row=row,
                trigger="ehr_status",
            )

        in_flight = mysql_patient_id in _ingest_in_flight
        cooldown_remaining = 0 if retry_scheduled else _auto_retry_cooldown_remaining(
            mysql_patient_id
        )

        progress = build_ingest_progress(
            mysql_patient_id=mysql_patient_id,
            llm=llm,
            in_flight=in_flight,
            has_ready=has_ready,
            summary_row=row,
            fasten_present=fasten_present,
            fasten_rows=fasten_rows,
            retry_cooldown_seconds_remaining=cooldown_remaining,
            retry_scheduled=retry_scheduled,
        )

        progress["patient_id"] = str(patient_id)
        if has_ready:
            diseases = fetch_disease_list(mysql_patient_id=mysql_patient_id, llm=llm) or []
            progress["disease_count"] = len(diseases)
        return progress

    def _maybe_auto_retry_ingest(
        self,
        *,
        patient_id: str,
        subject_id: Optional[str],
        mysql_patient_id: int,
        summary_row: Optional[Dict[str, Any]],
        trigger: str,
    ) -> bool:
        """Queue background ingest when retry is safe and likely to succeed."""
        if mysql_patient_id in _ingest_in_flight:
            return False
        if self._has_ready_row(mysql_patient_id):
            return False

        status = ((summary_row or {}).get("summary_status") or "").lower()
        needs_retry = (
            not summary_row
            or status == "failed"
            or is_stale_ingesting_row(mysql_patient_id, llm=self.preferred_llm)
        )
        if not needs_retry:
            return False

        last_retry = _last_auto_retry_at.get(mysql_patient_id)
        if last_retry is not None:
            since = time.monotonic() - last_retry
            if since < AUTO_RETRY_COOLDOWN_SECONDS:
                logger.debug(
                    "trial_gpt_ehr auto-retry skipped (cooldown) | patient_id=%s | since_sec=%.0f",
                    patient_id,
                    since,
                )
                return False

        if not subject_id:
            from repositories.mysql_repo import get_patient_identity

            identity = get_patient_identity(str(patient_id).strip())
            if not identity:
                return False
            subject_id = str(identity["subject_id"])

        logger.info(
            "trial_gpt_ehr auto-retry scheduled | patient_id=%s | trigger=%s | status=%s",
            patient_id,
            trigger,
            status or "missing",
        )
        started = self.schedule_background_ingest(
            patient_id=str(patient_id),
            subject_id=subject_id,
            trigger=trigger,
            force=True,
        )
        if started:
            _last_auto_retry_at[mysql_patient_id] = time.monotonic()
        return started

    def read_diseases_only(
        self,
        *,
        patient_id: str,
        subject_id: str,
    ) -> Tuple[List[str], list]:
        """Read diseases/ICD from trial_gpt_ehr only (no ingest)."""
        mysql_patient_id = parse_mysql_patient_id(patient_id)
        llm = self.preferred_llm
        diseases = _fetch_disease_list(
            mysql_patient_id=mysql_patient_id,
            subject_id=subject_id,
            llm=llm,
        )
        icd_entries = _fetch_icd_entries(
            mysql_patient_id=mysql_patient_id,
            subject_id=subject_id,
            llm=llm,
        )
        return diseases, icd_entries

    def read_summary_only(
        self,
        *,
        patient_id: str,
        subject_id: str,
    ) -> Optional[str]:
        mysql_patient_id = parse_mysql_patient_id(patient_id)
        return _fetch_summary(
            mysql_patient_id=mysql_patient_id,
            subject_id=subject_id,
            llm=self.preferred_llm,
        )

    def prepare_for_read(
        self,
        *,
        patient_id: str,
        subject_id: str,
        trigger: str,
        sync: bool = False,
    ) -> Dict[str, Any]:
        """
        Return read-state for diseases/summary endpoints.

        Diseases come from fastenhealth_condition (EHR, manual, and scan).
        LLM ingest is still used for P2T summaries; it does not gate the disease list.
        sync=True blocks until ingest completes (Postman / ops only).
        """
        _ensure_schema_once()
        mysql_patient_id = parse_mysql_patient_id(patient_id)
        llm = self.preferred_llm

        table_diseases, table_icd = fastenhealth_repo.fetch_condition_diseases(
            str(mysql_patient_id)
        )
        if table_diseases:
            self._maybe_refresh_summary_ingest(
                patient_id=patient_id,
                subject_id=subject_id,
                mysql_patient_id=mysql_patient_id,
                trigger=trigger,
                sync=sync,
            )
            logger.info(
                "trial_gpt_ehr diseases from Fasten tables | patient_id=%s | "
                "trigger=%s | diseases=%s",
                patient_id,
                trigger,
                len(table_diseases),
            )
            return {
                "ehr_status": "ready",
                "diseases": table_diseases,
                "icd_entries": table_icd,
                "ingest_result": None,
                "cached": self._has_ready_row(mysql_patient_id),
                "disease_source": "fastenhealth_condition",
            }

        if self._has_ready_row(mysql_patient_id):
            diseases, icd_entries = self.read_diseases_only(
                patient_id=patient_id,
                subject_id=subject_id,
            )
            logger.info(
                "trial_gpt_ehr cache hit | patient_id=%s | trigger=%s | diseases=%s",
                patient_id,
                trigger,
                len(diseases),
            )
            return {
                "ehr_status": "ready",
                "diseases": diseases,
                "icd_entries": icd_entries,
                "ingest_result": None,
                "cached": True,
                "disease_source": "trial_gpt_ehr",
            }

        diseases, icd_entries = self.read_diseases_only(
            patient_id=patient_id,
            subject_id=subject_id,
        )
        if diseases:
            return {
                "ehr_status": "ready",
                "diseases": diseases,
                "icd_entries": icd_entries,
                "ingest_result": None,
                "cached": True,
                "disease_source": "trial_gpt_ehr",
            }

        state = self._resolve_read_state(mysql_patient_id=mysql_patient_id, llm=llm)

        if not sync:
            progress = self.get_ingest_progress(
                patient_id,
                subject_id=subject_id,
                auto_retry=True,
            )
            if progress.get("ehr_status") == "ready":
                diseases, icd_entries = self.read_diseases_only(
                    patient_id=patient_id,
                    subject_id=subject_id,
                )
                return {
                    "ehr_status": "ready",
                    "diseases": diseases,
                    "icd_entries": icd_entries,
                    "ingest_result": None,
                    "cached": True,
                }
            logger.info(
                "trial_gpt_ehr preparing | patient_id=%s | trigger=%s | state=%s | stage=%s",
                patient_id,
                trigger,
                state,
                progress.get("stage"),
            )
            return {
                "ehr_status": "preparing",
                "diseases": [],
                "icd_entries": [],
                "ingest_result": None,
                "progress": progress,
            }

        self._preflight_fasten(mysql_patient_id)
        ingest_result = self.ensure_ready_sync(patient_id, trigger=trigger)
        diseases, icd_entries = self.read_diseases_only(
            patient_id=patient_id,
            subject_id=subject_id,
        )
        return {
            "ehr_status": "ready",
            "diseases": diseases,
            "icd_entries": icd_entries,
            "ingest_result": ingest_result,
        }

    def has_ready_profile(self, patient_id: str) -> bool:
        """True when trial_gpt_ehr has configured ready summary modes."""
        return self._has_ready_row(parse_mysql_patient_id(patient_id))

    def require_fasten_data(self, patient_id: str) -> None:
        """Raise if patient has no Fasten clinical rows (EHR, manual, or scan)."""
        self._preflight_fasten(parse_mysql_patient_id(patient_id))

    def _maybe_refresh_summary_ingest(
        self,
        *,
        patient_id: str,
        subject_id: str,
        mysql_patient_id: int,
        trigger: str,
        sync: bool,
    ) -> None:
        """Keep LLM summary in sync; disease list already came from Fasten tables."""
        if sync:
            self._preflight_fasten(mysql_patient_id)
            self.ensure_ready_sync(patient_id, trigger=trigger)
            return
        if self._has_ready_row(mysql_patient_id):
            row = trial_gpt_ehr_repo.fetch_ehr_status_row(
                mysql_patient_id=mysql_patient_id,
                llm=self.preferred_llm,
            )
            last_ts = row.get("last_data_timestamp") if isinstance(row, dict) else None
            if fastenhealth_repo.clinical_newer_than(str(mysql_patient_id), last_ts):
                self.schedule_background_ingest(
                    patient_id=patient_id,
                    subject_id=subject_id,
                    trigger=trigger,
                    force=True,
                )
            return
        self.get_ingest_progress(
            patient_id,
            subject_id=subject_id,
            auto_retry=True,
        )

    def schedule_background_ingest(
        self,
        *,
        patient_id: str,
        subject_id: str,
        trigger: str,
        force: bool = False,
    ) -> bool:
        """
        Start ingest in a daemon thread if not already running.

        Returns True when a new job was started.
        """
        mysql_patient_id = parse_mysql_patient_id(patient_id)

        if not force and self._has_ready_row(mysql_patient_id):
            row = trial_gpt_ehr_repo.fetch_ehr_status_row(
                mysql_patient_id=mysql_patient_id,
                llm=self.preferred_llm,
            )
            last_ts = row.get("last_data_timestamp") if isinstance(row, dict) else None
            if fastenhealth_repo.clinical_newer_than(str(mysql_patient_id), last_ts):
                force = True
            else:
                logger.info(
                    "trial_gpt_ehr skip background ingest (cached) | patient_id=%s",
                    patient_id,
                )
                return False

        if not force and is_stale_ingesting_row(
            mysql_patient_id,
            llm=self.preferred_llm,
        ):
            logger.warning(
                "trial_gpt_ehr background auto force (stale ingesting) | patient_id=%s",
                patient_id,
            )
            force = True

        with _ingest_lock:
            if mysql_patient_id in _ingest_in_flight:
                return False
            _ingest_in_flight.add(mysql_patient_id)

        config = self._config

        def _run() -> None:
            try:
                if not force and trial_gpt_ehr_repo.has_ready_modes(
                    mysql_patient_id,
                    config.required_llm_flags,
                ):
                    logger.info(
                        "trial_gpt_ehr background skip (already ready) | patient_id=%s",
                        patient_id,
                    )
                    return
                run_background_ingest_with_logging(
                    patient_id,
                    trigger=f"background:{trigger}",
                    force=force,
                )
            except Exception as exc:
                logger.exception(
                    "trial_gpt_ehr background thread error | patient_id=%s",
                    patient_id,
                )
                mark_worker_failure_if_still_ingesting(patient_id, format_worker_error(exc))
            finally:
                with _ingest_lock:
                    _ingest_in_flight.discard(mysql_patient_id)

        thread = threading.Thread(
            target=_run,
            name=f"trial-gpt-ehr-ingest-{mysql_patient_id}",
            daemon=True,
        )
        thread.start()
        logger.info(
            "trial_gpt_ehr background ingest started | patient_id=%s | trigger=%s",
            patient_id,
            trigger,
        )
        return True

    def _preflight_fasten(self, mysql_patient_id: int) -> None:
        if not fastenhealth_repo.has_clinical_data(str(mysql_patient_id)):
            raise TrialGptEhrIngestError(
                "No clinical records found in Fasten tables for this patient_id. "
                "Connect EHR, add a diagnosis, or scan a document first.",
                status_code=404,
            )

    def _resolve_read_state(self, *, mysql_patient_id: int, llm: bool) -> str:
        if self._has_ready_row(mysql_patient_id):
            return "ready"

        row = trial_gpt_ehr_repo.fetch_ehr_status_row(
            mysql_patient_id=mysql_patient_id,
            llm=llm,
        )
        if not row:
            return "missing"

        status = (row.get("summary_status") or "").lower()
        if status == "ready":
            return "ready"
        if status == "failed":
            return "failed"
        if status == "ingesting":
            updated = _as_utc_naive(row.get("updated_at"))
            if updated is not None:
                age = (datetime.utcnow() - updated).total_seconds()
                if age > STALE_INGESTING_SECONDS:
                    if mysql_patient_id not in _ingest_in_flight:
                        logger.warning(
                            "trial_gpt_ehr stale ingesting row | patient_id=%s | age_sec=%.0f",
                            mysql_patient_id,
                            age,
                        )
                    return "stale_ingesting"
            if mysql_patient_id in _ingest_in_flight:
                return "preparing"
            return "preparing"
        return "missing"

    def _has_ready_row(self, mysql_patient_id: int) -> bool:
        return trial_gpt_ehr_repo.has_ready_modes(
            mysql_patient_id,
            self._config.required_llm_flags,
        )


def load_patient_diseases_for_ui(
    *,
    patient_id: str,
    subject_id: str,
    sync: bool = False,
) -> Dict[str, Any]:
    """Module entry for GET /api/patient/{id}/diseases."""
    return TrialGptEhrReadService().prepare_for_read(
        patient_id=patient_id,
        subject_id=subject_id,
        trigger="diseases",
        sync=sync,
    )


def load_patient_summary_for_ui(
    *,
    patient_id: str,
    subject_id: str,
    sync: bool = False,
) -> Dict[str, Any]:
    """Module entry for GET /api/patient/{id}/summary."""
    svc = TrialGptEhrReadService()
    prep = svc.prepare_for_read(
        patient_id=patient_id,
        subject_id=subject_id,
        trigger="summary",
        sync=sync,
    )
    if prep["ehr_status"] == "preparing":
        prep["summary"] = None
        return prep
    summary = svc.read_summary_only(patient_id=patient_id, subject_id=subject_id)
    prep["summary"] = summary
    return prep


def get_patient_ehr_status(patient_id: str) -> Dict[str, Any]:
    """Module entry for GET /api/patient/{id}/ehr-status."""
    return TrialGptEhrReadService().get_ingest_progress(patient_id, auto_retry=True)


def get_patient_ingest_progress(patient_id: str) -> Dict[str, Any]:
    """Module entry for GET /api/patient/{id}/ehr-ingest-progress."""
    return TrialGptEhrReadService().get_ingest_progress(patient_id, auto_retry=True)
