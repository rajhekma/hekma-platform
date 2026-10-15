"""
Trigger trial_gpt_ehr ingest from internal callers (lambda after Fasten export).

Runs in a background thread so the HTTP caller returns immediately.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from repositories.mysql_repo import get_patient_identity
from repositories import trial_gpt_ehr_repo
from services.trial_gpt_ehr_ingest_service import (
    TrialGptEhrIngestError,
    is_stale_ingesting_row,
)
from services.trial_gpt_ehr_read_service import TrialGptEhrReadService, _ingest_in_flight

logger = logging.getLogger(__name__)


class TrialGptEhrTriggerService:
    """Accept ingest requests from trusted backend services."""

    def __init__(self, read_service: Optional[TrialGptEhrReadService] = None):
        self._read = read_service or TrialGptEhrReadService()

    def trigger_ingest(
        self,
        patient_id: str,
        *,
        trigger: str = "fasten_export",
        force: bool = True,
    ) -> Dict[str, Any]:
        """
        Queue Fasten → trial_gpt_ehr ingest for patient_id (MySQL patientId).

        force=True re-runs ingest after Fasten re-export (patient updated).
        Returns immediately; LLM work runs in a background thread.
        """
        trial_gpt_ehr_repo.ensure_trial_gpt_ehr_table()

        identity = get_patient_identity(str(patient_id).strip())
        if not identity:
            raise TrialGptEhrIngestError(
                "Patient not found in MySQL Patient table.",
                status_code=404,
            )

        mysql_patient_id = int(identity["mysql_patient_id"])
        subject_id = str(identity["subject_id"])

        logger.info(
            "trial_gpt_ehr internal trigger received | patient_id=%s | subject_id=%s | "
            "trigger=%s | force=%s",
            patient_id,
            subject_id,
            trigger,
            force,
        )

        if not force and self._read.has_ready_profile(str(patient_id)):
            diseases, _ = self._read.read_diseases_only(
                patient_id=str(patient_id),
                subject_id=subject_id,
            )
            logger.info(
                "trial_gpt_ehr internal trigger cache hit | patient_id=%s | trigger=%s",
                patient_id,
                trigger,
            )
            return {
                "patient_id": str(patient_id),
                "status": "already_present",
                "ehr_status": "ready",
                "cached": True,
                "disease_count": len(diseases),
            }

        if mysql_patient_id in _ingest_in_flight:
            logger.info(
                "trial_gpt_ehr internal trigger already running | patient_id=%s",
                patient_id,
            )
            return {
                "patient_id": str(patient_id),
                "status": "preparing",
                "ehr_status": "preparing",
            }

        llm = self._read.preferred_llm
        stale = is_stale_ingesting_row(mysql_patient_id, llm=llm)
        if stale and not force:
            logger.warning(
                "trial_gpt_ehr stale ingesting — auto force retry | patient_id=%s",
                patient_id,
            )
            force = True

        self._read.require_fasten_data(str(patient_id))
        started = self._read.schedule_background_ingest(
            patient_id=str(patient_id),
            subject_id=subject_id,
            trigger=trigger,
            force=force,
        )
        if not started:
            logger.info(
                "trial_gpt_ehr internal trigger not started (already queued) | patient_id=%s",
                patient_id,
            )
            return {
                "patient_id": str(patient_id),
                "status": "preparing",
                "ehr_status": "preparing",
            }

        logger.info(
            "trial_gpt_ehr internal trigger accepted | patient_id=%s | trigger=%s | force=%s",
            patient_id,
            trigger,
            force,
        )
        return {
            "patient_id": str(patient_id),
            "status": "accepted",
            "ehr_status": "preparing",
            "retry_after_seconds": 15,
        }


def trigger_trial_gpt_ehr_ingest(
    patient_id: str,
    *,
    trigger: str = "fasten_export",
    force: bool = True,
) -> Dict[str, Any]:
    """Module entry for internal ingest API."""
    return TrialGptEhrTriggerService().trigger_ingest(
        patient_id,
        trigger=trigger,
        force=force,
    )
