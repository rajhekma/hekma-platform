"""Drop stale GET /patientdetail Redis snapshots after clinical writes.

The mobile dashboard reads combinedFlag=Y from Redis (24h TTL). GraphQL
add/update already calls /cachereprocess; scans and FastAPI CRUD did not,
so QA tiles stayed empty until a manual add of the same type.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Iterable, Optional, Protocol, Set

from .modules import ClinicalModule

logger = logging.getLogger(__name__)


class CacheReprocessor(Protocol):
    def invalidate(self, event: dict) -> dict: ...

    def regenerate(self, inv: dict) -> None: ...


class _PipelineCacheReprocessor:
    """Adapter over cache_service.reprocess_cache (same path as GraphQL)."""

    def invalidate(self, event: dict) -> dict:
        from ...cache_service.reprocess_cache import (
            invalidate_patient_detail_cache_from_event,
        )

        return invalidate_patient_detail_cache_from_event(event)

    def regenerate(self, inv: dict) -> None:
        from ...cache_service.reprocess_cache import run_background_cache_regeneration

        run_background_cache_regeneration(
            inv["explicit_keys"],
            inv["subject_id"],
            inv["bu_id"],
            inv["email"],
            inv["object_type"],
        )


class DashboardCacheInvalidator:
    """Best-effort unlink + background warm of patientdetail/header keys."""

    def __init__(self, reprocessor: Optional[CacheReprocessor] = None):
        self._reprocessor = reprocessor or _PipelineCacheReprocessor()

    def invalidate_for_modules(self, patient_id: str, modules: Iterable[str]) -> None:
        """Drop dashboard cache for each distinct FHIR objectType in modules."""
        object_types: Set[str] = set()
        for raw in modules:
            try:
                object_types.add(ClinicalModule.from_value(raw).dashboard_object_type)
            except ValueError:
                logger.debug("Skip dashboard cache bust for unknown module=%s", raw)
        for object_type in sorted(object_types):
            self.invalidate_object_type(patient_id, object_type)

    def invalidate_object_type(self, patient_id: str, object_type: str) -> None:
        """Unlink details_{objectType}_* and warm in a daemon thread so HTTP responses return immediately."""
        pid = str(patient_id or "").strip()
        if not pid or not object_type:
            return
        event = {
            "params": {
                "querystring": {
                    "env": (os.getenv("APP_ENV") or "dev").strip() or "dev",
                    "buType": "Patient",
                    "buId": pid,
                    "objectType": object_type,
                }
            }
        }
        thread = threading.Thread(
            target=self._async_invalidate_and_regenerate,
            args=(event, pid, object_type),
            name=f"p360-cache-{object_type}-{pid}",
            daemon=True,
        )
        thread.start()

    def _async_invalidate_and_regenerate(
        self, event: dict, patient_id: str, object_type: str
    ) -> None:
        try:
            inv = self._reprocessor.invalidate(event)
            if inv:
                self._reprocessor.regenerate(inv)
        except Exception:
            logger.exception(
                "Dashboard cache async invalidate/regenerate failed patient_id=%s objectType=%s",
                patient_id,
                object_type,
            )

