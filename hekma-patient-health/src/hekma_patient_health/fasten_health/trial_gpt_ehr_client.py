"""
Notify gpt-api to ingest trial_gpt_ehr after Fasten export lands in Postgres.

Fire-and-forget HTTP POST so Fasten webhooks are not blocked by LLM work (~1–2 min).
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10


def _base_url() -> str:
    return os.getenv("TRIALGPT_API_BASE_URL", "").strip().rstrip("/")


def _api_key() -> str:
    return os.getenv("TRIALGPT_EHR_INGEST_API_KEY", "").strip()


def is_trial_gpt_ehr_notify_configured() -> bool:
    """True when lambda can call gpt-api internal ingest."""
    return bool(_base_url() and _api_key())


def notify_trial_gpt_ehr_ingest(
    patient_id: str,
    *,
    trigger: str = "fasten_ehi_export_success",
    force: bool = True,
) -> None:
    """
    POST to gpt-api internal ingest endpoint in a background thread.

    No-op when TRIALGPT_API_BASE_URL or TRIALGPT_EHR_INGEST_API_KEY is unset.
    """
    base = _base_url()
    key = _api_key()
    if not base or not key:
        logger.info(
            "trial_gpt_ehr notify skipped (not configured) | patient_id=%s | "
            "set TRIALGPT_API_BASE_URL and TRIALGPT_EHR_INGEST_API_KEY",
            patient_id,
        )
        return

    def _post() -> None:
        url = f"{base}/api/internal/trial-gpt-ehr/ingest"
        payload = {
            "patient_id": str(patient_id),
            "trigger": trigger,
            "force": force,
        }
        headers = {"X-Hekma-Internal-Key": key}
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
            logger.info(
                "trial_gpt_ehr notify | patient_id=%s | status=%s | body=%s",
                patient_id,
                resp.status_code,
                resp.text[:200],
            )
            resp.raise_for_status()
        except Exception:
            logger.exception(
                "trial_gpt_ehr notify failed | patient_id=%s | url=%s",
                patient_id,
                url,
            )

    thread = threading.Thread(
        target=_post,
        name=f"trial-gpt-ehr-notify-{patient_id}",
        daemon=True,
    )
    logger.info(
        "trial_gpt_ehr notify dispatch | patient_id=%s | trigger=%s | force=%s | url=%s",
        patient_id,
        trigger,
        force,
        f"{base}/api/internal/trial-gpt-ehr/ingest",
    )
    thread.start()


def notify_trial_gpt_ehr_ingest_sync(
    patient_id: str,
    *,
    trigger: str = "fasten_ehi_export_success",
    force: bool = True,
    timeout: Optional[int] = None,
) -> requests.Response:
    """Blocking variant for scripts/tests."""
    base = _base_url()
    key = _api_key()
    if not base or not key:
        raise RuntimeError(
            "TRIALGPT_API_BASE_URL and TRIALGPT_EHR_INGEST_API_KEY must be set"
        )
    return requests.post(
        f"{base}/api/internal/trial-gpt-ehr/ingest",
        json={
            "patient_id": str(patient_id),
            "trigger": trigger,
            "force": force,
        },
        headers={"X-Hekma-Internal-Key": key},
        timeout=timeout or _DEFAULT_TIMEOUT_SECONDS,
    )
