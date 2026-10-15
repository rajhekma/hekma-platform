"""Bridge to Fasten trial summary generator (sibling repo or bundled copy in Docker)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_HEKMA_DIR_NAME = "Backend API Hekma"


def _find_hekma_parent() -> Optional[Path]:
    """
    Locate the sibling Hekma repo when present.

    Uses HEKMA_DATA_PIPELINE_PARENT when set, otherwise walks ancestors for
    ``Backend API Hekma/`` (monorepo layout). Returns None in Docker when absent.
    """
    override = os.getenv("HEKMA_DATA_PIPELINE_PARENT", "").strip()
    if override:
        parent = Path(override)
        return parent if parent.is_dir() else None

    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor / _HEKMA_DIR_NAME
        if candidate.is_dir():
            return candidate
    return None


def _ensure_hekma_on_path() -> Path:
    """Add Hekma package parent to sys.path once; raise RuntimeError if missing."""
    parent = _find_hekma_parent()
    if parent is None:
        raise RuntimeError(
            "Hekma data pipeline parent not found. "
            "Set HEKMA_DATA_PIPELINE_PARENT or use bundled summary in Docker."
        )
    parent_str = str(parent)
    if parent_str not in sys.path:
        sys.path.insert(0, parent_str)
    return parent


def get_generate_trial_patient_summary() -> Callable[..., Any]:
    """Return generate_trial_patient_summary from sibling repo or bundled copy."""
    try:
        _ensure_hekma_on_path()
        from hekma_data_pipleline.fasten_health.trial_patient_summary import (  # noqa: WPS433
            generate_trial_patient_summary,
        )

        logger.debug("trial_gpt_ehr using hekma_data_pipleline from filesystem")
        return generate_trial_patient_summary
    except (RuntimeError, ImportError, ModuleNotFoundError) as exc:
        logger.info("trial_gpt_ehr using bundled trial summary (%s)", exc)
        from services.bundled_hekma.trial_patient_summary import (  # noqa: WPS433
            generate_trial_patient_summary,
        )

        return generate_trial_patient_summary


def serialize_fasten_rows(
    export_data: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Normalize datetime values so summary helpers stay JSON-safe."""
    try:
        _ensure_hekma_on_path()
        from hekma_data_pipleline.fasten_health.patient_data_exporter import (  # noqa: WPS433
            serialize_fasten_row,
        )
    except (RuntimeError, ImportError, ModuleNotFoundError):
        from services.bundled_hekma.fasten_serialize import serialize_fasten_row

    out: Dict[str, List[Dict[str, Any]]] = {}
    for table, rows in export_data.items():
        out[table] = [serialize_fasten_row(row) for row in rows]
    return out
