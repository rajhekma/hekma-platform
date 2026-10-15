"""
Incremental patient Qdrant embed from trial_gpt_ehr structured profiles.

Exports selected profiles to a temp JSON and runs TrialGPT_RAG/ingest_patients_block.py
in a subprocess (avoids TrialGPT_RAG/utils.py shadowing the project utils package).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.trial_gpt_ehr_config import get_trial_gpt_ehr_config
from repositories.trial_gpt_ehr_repo import (
    fetch_profiles_by_subject_ids,
    fetch_ready_subject_ids,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_DIR = PROJECT_ROOT / "TrialGPT_RAG"

DEFAULT_EMBED_ERROR_PATH = Path("results/patient_embed_errors.jsonl")
DEFAULT_BATCH_SIZE = 50


def _append_embed_dlq(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _preferred_llm_flag() -> bool:
    """llm column value for the configured P2T-preferred summary mode."""
    return bool(get_trial_gpt_ehr_config().p2t_preferred_llm)


def _fetch_all_ehr_patient_ids(limit: int | None = None) -> list[str]:
    """Ready trial_gpt_ehr subject_ids for the preferred llm mode."""
    return fetch_ready_subject_ids(llm=_preferred_llm_flag(), limit=limit)


# Back-compat alias for scripts that imported the compose-era name.
_fetch_all_compose_patient_ids = _fetch_all_ehr_patient_ids


def _strip_internal_keys(profile: dict) -> dict:
    return {
        k: v
        for k, v in profile.items()
        if k not in ("_generation", "_icd_diseases")
    }


def embed_patient_ids(
    patient_ids: list[str],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    recreate: bool = False,
    error_path: Path = DEFAULT_EMBED_ERROR_PATH,
) -> dict[str, Any]:
    """Embed/upsert specific trial_gpt_ehr subject profiles into Qdrant."""
    stats: dict[str, Any] = {
        "requested": len(patient_ids),
        "found_in_ehr": 0,
        "found_in_compose": 0,  # legacy key kept for older log readers
        "upserted": 0,
        "failed": 0,
        "collection": os.getenv("QDRANT_PATIENT_COLLECTION", "patient_profiles_hybrid_v1"),
        "source_table": "trial_gpt_ehr",
    }
    if not patient_ids:
        return stats

    profiles = fetch_profiles_by_subject_ids(
        patient_ids,
        llm=_preferred_llm_flag(),
    )
    stats["found_in_ehr"] = len(profiles)
    stats["found_in_compose"] = len(profiles)
    if not profiles:
        return stats

    export_payload = {
        pid: _strip_internal_keys(profile) if isinstance(profile, dict) else profile
        for pid, profile in profiles.items()
    }

    env = os.environ.copy()
    env.setdefault("QDRANT_INGEST_SKIP_QUERY_EXPANSION", "true")

    with tempfile.TemporaryDirectory(prefix="patient_embed_") as tmp:
        export_path = Path(tmp) / "patients_for_qdrant.json"
        export_path.write_text(
            json.dumps(export_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        args = [
            sys.executable,
            "ingest_patients_block.py",
            "--json-path",
            str(export_path),
            "--batch-size",
            str(batch_size),
        ]
        if recreate:
            args.append("--recreate")

        logger.info(
            "Starting patient Qdrant ingest for %s trial_gpt_ehr profiles",
            len(export_payload),
        )
        result = subprocess.run(
            args,
            cwd=str(RAG_DIR),
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            stats["failed"] = len(export_payload)
            _append_embed_dlq(
                error_path,
                {
                    "patient_ids": list(export_payload.keys()),
                    "error": (result.stderr or result.stdout or "")[:4000],
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "stage": "ingest_patients_block_subprocess",
                    "returncode": result.returncode,
                    "source_table": "trial_gpt_ehr",
                },
            )
            logger.error(
                "Patient embed failed (exit %s): %s",
                result.returncode,
                (result.stderr or result.stdout or "")[:2000],
            )
            return stats

        stats["upserted"] = len(export_payload)
        if result.stdout:
            logger.info(result.stdout[-2000:])
    return stats


def embed_from_compose(
    *,
    patient_ids: list[str] | None = None,
    limit: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    recreate: bool = False,
    error_path: Path = DEFAULT_EMBED_ERROR_PATH,
) -> dict[str, Any]:
    """Embed ready trial_gpt_ehr patients (name kept for existing job scripts)."""
    ids = patient_ids if patient_ids is not None else _fetch_all_ehr_patient_ids(limit=limit)
    if patient_ids is None and limit and limit > 0:
        ids = ids[:limit]
    return embed_patient_ids(
        ids,
        batch_size=batch_size,
        recreate=recreate,
        error_path=error_path,
    )


# Preferred name for new callers.
embed_from_trial_gpt_ehr = embed_from_compose
