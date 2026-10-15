"""
Ingest Fasten Health clinical data into trial_gpt_ehr before P2T.

P2T always uses trial_gpt_ehr (never trialgpt_eligible_patients).
Requires clinical rows in fastenhealth_* (EHR, manual, or scan).
Skips re-ingest when configured llm rows are already ready unless Fasten data is newer.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Set

from config.trial_gpt_ehr_config import TrialGptEhrConfig, get_trial_gpt_ehr_config
from repositories import fastenhealth_repo, trial_gpt_ehr_repo
from repositories.mysql_repo import get_patient_identity
from services.hekma_fasten_bridge import (
    get_generate_trial_patient_summary,
    serialize_fasten_rows,
)

logger = logging.getLogger(__name__)

# Treat ingesting rows older than this as dead workers (LLM usually finishes < 2 min).
STALE_INGESTING_ROW_SECONDS = 180


def format_worker_error(exc: BaseException) -> str:
    """Readable ingest error for DB/UI; avoids bare IndexError args like '3'."""
    name = type(exc).__name__
    msg = str(exc).strip()
    if isinstance(exc, IndexError) and (not msg or msg.isdigit()):
        return (
            "IndexError: Hekma summary module path missing in Docker "
            "(deploy gpt-api with bundled Fasten summary)"
        )
    if msg and msg != name:
        return f"{name}: {msg}"[:500]
    return name[:500]


def mark_worker_failure_if_still_ingesting(patient_id: str, error_note: str) -> None:
    """If worker died mid-ingest, move ingesting row to failed so force retry can run."""
    try:
        identity = get_patient_identity(str(patient_id).strip())
        if not identity:
            return
        cfg = get_trial_gpt_ehr_config()
        llm = cfg.p2t_preferred_llm
        mysql_patient_id = int(identity["mysql_patient_id"])
        subject_id = str(identity["subject_id"])
        row = trial_gpt_ehr_repo.fetch_ehr_status_row(
            mysql_patient_id=mysql_patient_id,
            llm=llm,
        )
        if not row or (row.get("summary_status") or "").lower() != "ingesting":
            return
        trial_gpt_ehr_repo.mark_failed(
            subject_id=subject_id,
            mysql_patient_id=mysql_patient_id,
            llm=llm,
            error_note=error_note[:500],
        )
        logger.warning(
            "trial_gpt_ehr marked failed after worker error | patient_id=%s",
            patient_id,
        )
    except Exception:
        logger.exception(
            "trial_gpt_ehr could not mark failed after worker error | patient_id=%s",
            patient_id,
        )


def is_stale_ingesting_row(
    mysql_patient_id: int,
    *,
    llm: bool,
    max_age_seconds: int = STALE_INGESTING_ROW_SECONDS,
) -> bool:
    """True when summary_status=ingesting and updated_at is older than max_age."""
    row = trial_gpt_ehr_repo.fetch_ehr_status_row(
        mysql_patient_id=mysql_patient_id,
        llm=llm,
    )
    if not row or (row.get("summary_status") or "").lower() != "ingesting":
        return False
    updated = row.get("updated_at")
    if updated is None:
        return True
    if isinstance(updated, datetime):
        age = (datetime.utcnow() - updated).total_seconds()
        return age > max_age_seconds
    return False


class TrialGptEhrIngestError(Exception):
    """Raised when ingest must block P2T."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class TrialGptEhrIngestResult:
    """Outcome of ensure_trial_gpt_ehr_for_p2t."""

    status: str  # already_present | ingested
    mysql_patient_id: int
    subject_id: str
    modes_written: tuple[bool, ...]
    detail: str = ""


class TrialGptEhrIngestService:
    """Orchestrates Fasten export, summary gen, upserts, and patient Qdrant embed."""

    def __init__(self, config: Optional[TrialGptEhrConfig] = None):
        self._config = config or get_trial_gpt_ehr_config()

    def ensure_for_p2t(
        self,
        mysql_patient_id_raw: str,
        *,
        skip_inflight_guard: bool = False,
        force: bool = False,
        trigger: str = "p2t",
    ) -> TrialGptEhrIngestResult:
        """
        Ensure configured trial_gpt_ehr rows exist before P2T starts.

        Fail closed when Fasten clinical rows are missing — no eligible_patients fallback.
        skip_inflight_guard=True for the background worker that owns the ingesting row.
        force=True re-ingests after Fasten re-export (patient updated).
        """
        trial_gpt_ehr_repo.ensure_trial_gpt_ehr_table()

        identity = get_patient_identity(str(mysql_patient_id_raw).strip())
        if not identity:
            raise TrialGptEhrIngestError(
                "Patient not found in MySQL Patient table.",
                status_code=404,
            )

        mysql_patient_id = int(identity["mysql_patient_id"])
        subject_id = str(identity["subject_id"])
        required_flags = set(self._config.required_llm_flags)
        llm = self._config.p2t_preferred_llm

        if not force and trial_gpt_ehr_repo.has_ready_modes(mysql_patient_id, required_flags):
            status_row = trial_gpt_ehr_repo.fetch_ehr_status_row(
                mysql_patient_id=mysql_patient_id,
                llm=llm,
            )
            last_ts = status_row.get("last_data_timestamp") if isinstance(status_row, dict) else None
            if fastenhealth_repo.clinical_newer_than(str(mysql_patient_id), last_ts):
                logger.info(
                    "trial_gpt_ehr cache stale vs Fasten tables | mysql_patient_id=%s",
                    mysql_patient_id,
                )
                force = True
            else:
                trial_gpt_ehr_repo.sync_subject_id(mysql_patient_id, subject_id)
                logger.info(
                    "trial_gpt_ehr already present | mysql_patient_id=%s | modes=%s",
                    mysql_patient_id,
                    sorted(required_flags),
                )
                return TrialGptEhrIngestResult(
                    status="already_present",
                    mysql_patient_id=mysql_patient_id,
                    subject_id=subject_id,
                    modes_written=tuple(sorted(required_flags)),
                    detail="Configured summary modes already ready.",
                )

        status_row = trial_gpt_ehr_repo.fetch_ehr_status_row(
            mysql_patient_id=mysql_patient_id,
            llm=llm,
        )
        ingesting = (
            status_row
            and (status_row.get("summary_status") or "").lower() == "ingesting"
        )
        stale_ingesting = ingesting and is_stale_ingesting_row(
            mysql_patient_id,
            llm=llm,
        )
        if ingesting and stale_ingesting:
            logger.warning(
                "trial_gpt_ehr retry stale ingesting row | patient_id=%s | trigger=%s",
                mysql_patient_id,
                trigger,
            )
        if (
            not skip_inflight_guard
            and ingesting
            and not force
            and not stale_ingesting
        ):
            raise TrialGptEhrIngestError(
                "EHR profile is still being prepared. Wait a moment and retry.",
                status_code=409,
            )

        if not fastenhealth_repo.has_clinical_data(str(mysql_patient_id)):
            raise TrialGptEhrIngestError(
                "No clinical records found in Fasten tables for this patient_id. "
                "P2T needs EHR, manual, or scan data in fastenhealth_*.",
                status_code=404,
            )

        return self._ingest(
            mysql_patient_id=mysql_patient_id,
            subject_id=subject_id,
            required_flags=required_flags,
            trigger=trigger,
        )

    def _ingest(
        self,
        *,
        mysql_patient_id: int,
        subject_id: str,
        required_flags: Set[bool],
        trigger: str = "ingest",
    ) -> TrialGptEhrIngestResult:
        started = time.monotonic()
        logger.info(
            "trial_gpt_ehr ingest start | patient_id=%s | subject_id=%s | trigger=%s",
            mysql_patient_id,
            subject_id,
            trigger,
        )

        export_data = None
        row_count = 0
        for attempt in range(1, 7):
            export_data = fastenhealth_repo.export_fasten_patient_data(
                str(mysql_patient_id),
                skip_large_tables=self._config.skip_large_tables,
            )
            row_count = sum(len(rows) for rows in (export_data or {}).values())
            if row_count >= 5:
                break
            if attempt < 6:
                logger.info(
                    "trial_gpt_ehr waiting for fasten rows | patient_id=%s | rows=%s | "
                    "attempt=%s/6",
                    mysql_patient_id,
                    row_count,
                    attempt,
                )
                time.sleep(10)

        if not export_data or row_count == 0:
            raise TrialGptEhrIngestError(
                "Fasten Health tables have no clinical rows for this patient.",
                status_code=404,
            )

        row_count = sum(len(rows) for rows in export_data.values())
        logger.info(
            "trial_gpt_ehr ingest fasten_export | patient_id=%s | tables=%s | rows=%s",
            mysql_patient_id,
            len(export_data),
            row_count,
        )

        trial_gpt_ehr_repo.mark_ingesting(
            subject_id=subject_id,
            mysql_patient_id=mysql_patient_id,
            llm=self._config.p2t_preferred_llm,
        )
        logger.info(
            "trial_gpt_ehr ingest status=ingesting | patient_id=%s",
            mysql_patient_id,
        )

        try:
            serialized = serialize_fasten_rows(export_data)
            clinical_latest = fastenhealth_repo.get_fasten_clinical_latest_ts(
                str(mysql_patient_id)
            )
            generate = get_generate_trial_patient_summary()
            written: List[bool] = []

            for llm_flag in sorted(required_flags, reverse=True):
                try:
                    llm_started = time.monotonic()
                    logger.info(
                        "trial_gpt_ehr ingest llm_start | patient_id=%s | llm=%s",
                        mysql_patient_id,
                        llm_flag,
                    )
                    summary = generate(
                        serialized,
                        use_llm=llm_flag,
                        include_disease_llm=llm_flag,
                    )
                    if not summary.summary_text or not str(summary.summary_text).strip():
                        raise RuntimeError("Empty summary_text generated")

                    trial_gpt_ehr_repo.upsert_trial_gpt_ehr_row(
                        subject_id=subject_id,
                        mysql_patient_id=mysql_patient_id,
                        llm=llm_flag,
                        summary_text=summary.summary_text,
                        structured_json=summary.structured_json,
                        disease_list=summary.disease_list,
                        has_pg_patient=True,
                        clinical_latest_ts=clinical_latest,
                        last_data_timestamp=clinical_latest,
                        summary_status="ready",
                    )
                    written.append(llm_flag)
                    disease_count = len(summary.disease_list or [])
                    logger.info(
                        "trial_gpt_ehr ingest llm_done | patient_id=%s | llm=%s | "
                        "generated_by=%s | diseases=%s | llm_elapsed_sec=%.1f",
                        mysql_patient_id,
                        llm_flag,
                        summary.generated_by,
                        disease_count,
                        time.monotonic() - llm_started,
                    )
                except Exception as exc:
                    logger.exception(
                        "trial_gpt_ehr ingest failed | mysql_patient_id=%s | llm=%s",
                        mysql_patient_id,
                        llm_flag,
                    )
                    try:
                        trial_gpt_ehr_repo.mark_failed(
                            subject_id=subject_id,
                            mysql_patient_id=mysql_patient_id,
                            llm=llm_flag,
                            error_note=format_worker_error(exc),
                        )
                    except Exception:
                        logger.exception("Failed to mark trial_gpt_ehr row as failed")
                    raise TrialGptEhrIngestError(
                        f"Failed to generate trial_gpt_ehr summary (llm={llm_flag}): {exc}",
                        status_code=500,
                    ) from exc

            if not set(written).issuperset(required_flags):
                raise TrialGptEhrIngestError(
                    "Ingest incomplete for configured summary modes.",
                    status_code=500,
                )
        except Exception as exc:
            mark_worker_failure_if_still_ingesting(str(mysql_patient_id), format_worker_error(exc))
            raise

        self._embed_patient_profile(subject_id)

        logger.info(
            "trial_gpt_ehr ingest complete | patient_id=%s | status=ready | "
            "modes=%s | elapsed_sec=%.1f",
            mysql_patient_id,
            sorted(written),
            time.monotonic() - started,
        )

        return TrialGptEhrIngestResult(
            status="ingested",
            mysql_patient_id=mysql_patient_id,
            subject_id=subject_id,
            modes_written=tuple(written),
            detail="Ingested configured summary modes into trial_gpt_ehr.",
        )

    def _embed_patient_profile(self, subject_id: str) -> None:
        """Upsert this patient's trial_gpt_ehr profile into the Qdrant patient collection."""
        try:
            from services.patient_qdrant_embed_service import embed_patient_ids

            stats = embed_patient_ids([subject_id])
            logger.info(
                "trial_gpt_ehr patient embed | subject_id=%s | upserted=%s | found=%s",
                subject_id,
                stats.get("upserted"),
                stats.get("found_in_ehr") or stats.get("found_in_compose"),
            )
        except Exception:
            # Ingest succeeded; RAG can still query from raw_profile at request time.
            logger.exception(
                "trial_gpt_ehr patient embed failed | subject_id=%s",
                subject_id,
            )


def ensure_trial_gpt_ehr_ready(
    mysql_patient_id: str,
    *,
    config: Optional[TrialGptEhrConfig] = None,
    trigger: str = "p2t",
    skip_inflight_guard: Optional[bool] = None,
    force: bool = False,
) -> TrialGptEhrIngestResult:
    """Ensure Fasten → trial_gpt_ehr rows exist (P2T gate, diseases/summary reads)."""
    if skip_inflight_guard is None:
        skip_inflight_guard = trigger.startswith("background:")
    logger.info(
        "trial_gpt_ehr ensure | patient_id=%s | trigger=%s | skip_inflight_guard=%s | force=%s",
        mysql_patient_id,
        trigger,
        skip_inflight_guard,
        force,
    )
    return TrialGptEhrIngestService(config=config).ensure_for_p2t(
        mysql_patient_id,
        skip_inflight_guard=skip_inflight_guard,
        force=force,
        trigger=trigger,
    )


def run_background_ingest_with_logging(
    patient_id: str,
    *,
    trigger: str,
    force: bool = False,
) -> None:
    """Run ensure in a worker thread with start/finish progress logs."""
    started = time.monotonic()
    logger.info(
        "trial_gpt_ehr background worker start | patient_id=%s | trigger=%s | force=%s",
        patient_id,
        trigger,
        force,
    )
    try:
        result = ensure_trial_gpt_ehr_ready(
            patient_id,
            trigger=trigger,
            force=force,
        )
        logger.info(
            "trial_gpt_ehr background worker done | patient_id=%s | trigger=%s | "
            "result=%s | modes=%s | elapsed_sec=%.1f",
            patient_id,
            trigger,
            result.status,
            result.modes_written,
            time.monotonic() - started,
        )
    except Exception as exc:
        logger.exception(
            "trial_gpt_ehr background worker failed | patient_id=%s | trigger=%s | "
            "elapsed_sec=%.1f | error=%s",
            patient_id,
            trigger,
            time.monotonic() - started,
            exc,
        )
        mark_worker_failure_if_still_ingesting(patient_id, format_worker_error(exc))
        raise


def ensure_trial_gpt_ehr_for_p2t(
    mysql_patient_id: str,
    *,
    config: Optional[TrialGptEhrConfig] = None,
) -> TrialGptEhrIngestResult:
    """Module-level entry used by the P2T API."""
    return ensure_trial_gpt_ehr_ready(
        mysql_patient_id,
        config=config,
        trigger="p2t",
    )
