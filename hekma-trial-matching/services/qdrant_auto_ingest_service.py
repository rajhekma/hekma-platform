"""
Automatic Qdrant patient + trial ingest (no manual shell scripts).

Enable with QDRANT_AUTO_INGEST_ON_STARTUP=true on the API deployment.
Runs in a background thread so uvicorn starts immediately.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

from utils.qdrant_util import get_qdrant_client

logger = logging.getLogger("qdrant_auto_ingest")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RAG_DIR = _REPO_ROOT / "TrialGPT_RAG"

_lock = threading.Lock()
_state = {
    "status": "idle",  # idle | running | completed | failed | skipped
    "message": "",
    "patients_ingested": False,
    "trials_ingested": False,
}


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


def _collection_point_count(collection_name: str) -> int:
    client = get_qdrant_client()
    names = {c.name for c in client.get_collections().collections}
    if collection_name not in names:
        return 0
    info = client.get_collection(collection_name)
    return int(getattr(info, "points_count", 0) or 0)


def get_ingest_status() -> dict:
    patient_collection = os.getenv(
        "QDRANT_PATIENT_COLLECTION", "patient_profiles_hybrid_v1"
    )
    trial_collection = os.getenv(
        "QDRANT_TRIAL_COLLECTION", "clinical_trials_hybrid_v1"
    )
    try:
        patient_points = _collection_point_count(patient_collection)
        trial_points = _collection_point_count(trial_collection)
    except Exception as exc:
        return {
            **_state,
            "error": str(exc),
            "patient_collection": patient_collection,
            "trial_collection": trial_collection,
        }

    return {
        **_state,
        "patient_collection": patient_collection,
        "trial_collection": trial_collection,
        "patient_points": patient_points,
        "trial_points": trial_points,
        "auto_ingest_enabled": _env_bool("QDRANT_AUTO_INGEST_ON_STARTUP"),
    }


def _friendly_subprocess_error(label: str, returncode: int, stderr: str, stdout: str) -> str:
    blob = f"{stderr}\n{stdout}"
    if "insufficient_quota" in blob:
        return (
            f"{label} failed: OpenAI quota exceeded. "
            "Add billing/credits at https://platform.openai.com/account/billing "
            "or ingest from dev server with a valid OPENAI_API_KEY. "
            f"Details: {stderr[:800]}"
        )
    return (
        f"{label} failed (exit {returncode}). "
        f"stderr={stderr[:2000]} stdout={stdout[:2000]}"
    )


def _assert_openai_ready_for_ingest() -> None:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for Qdrant ingest (embeddings).")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    try:
        client.embeddings.create(model="text-embedding-3-large", input="ping")
    except Exception as exc:
        msg = str(exc)
        if "insufficient_quota" in msg:
            raise RuntimeError(
                "OpenAI quota exceeded. Patient/trial ingest needs embeddings API. "
                "Fix billing at https://platform.openai.com/account/billing "
                "or run ingest on dev with a funded OPENAI_API_KEY."
            ) from exc
        raise RuntimeError(f"OpenAI API check failed before ingest: {msg}") from exc


def _run_subprocess(args: list[str], *, cwd: Path, label: str) -> None:
    logger.info("[QDRANT_INGEST] Starting %s: %s", label, " ".join(args))
    result = subprocess.run(
        args,
        cwd=str(cwd),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        raise RuntimeError(_friendly_subprocess_error(label, result.returncode, stderr, stdout))
    if result.stdout:
        logger.info("[QDRANT_INGEST] %s stdout: %s", label, result.stdout[-1500:])
    logger.info("[QDRANT_INGEST] Finished %s", label)


def run_qdrant_ingest(*, force: bool = False) -> dict:
    """
    Export patients from Postgres and ingest patients + trials into Qdrant.
    Skips collections that already have points unless force=True.
    """
    if not _lock.acquire(blocking=False):
        return {**get_ingest_status(), "message": "Ingest already running"}

    try:
        _state["status"] = "running"
        _state["message"] = "Ingest started"
        _state["patients_ingested"] = False
        _state["trials_ingested"] = False

        patient_collection = os.getenv(
            "QDRANT_PATIENT_COLLECTION", "patient_profiles_hybrid_v1"
        )
        trial_collection = os.getenv(
            "QDRANT_TRIAL_COLLECTION", "clinical_trials_hybrid_v1"
        )
        batch_size = int(os.getenv("QDRANT_INGEST_BATCH_SIZE", "50"))
        recreate = _env_bool("QDRANT_INGEST_RECREATE", False) or force
        trials_corpus = os.getenv(
            "QDRANT_TRIALS_CORPUS_PATH",
            str(_REPO_ROOT / "dataset" / "trials.jsonl"),
        )
        export_path = _RAG_DIR / "patient_block_summaries.from_compose.json"
        trials_export_path = _RAG_DIR / "trials.from_corpus.jsonl"
        python = sys.executable

        patient_points = _collection_point_count(patient_collection)
        trial_points = _collection_point_count(trial_collection)

        need_patients = force or patient_points == 0
        need_trials = force or trial_points == 0

        if not need_patients and not need_trials:
            _state["status"] = "skipped"
            _state["message"] = "Collections already populated; ingest skipped"
            return get_ingest_status()

        _assert_openai_ready_for_ingest()

        if need_patients:
            _run_subprocess(
                [
                    python,
                    str(_REPO_ROOT / "scripts" / "export_compose_profiles_for_qdrant.py"),
                    "--output",
                    str(export_path),
                ],
                cwd=_REPO_ROOT,
                label="export_trial_gpt_ehr_profiles",
            )
            patient_args = [
                python,
                "ingest_patients_block.py",
                "--json-path",
                str(export_path),
                "--batch-size",
                str(batch_size),
            ]
            if recreate or patient_points == 0:
                patient_args.append("--recreate")
            _run_subprocess(patient_args, cwd=_RAG_DIR, label="ingest_patients")
            _state["patients_ingested"] = True

        if need_trials:
            if _env_bool("QDRANT_TRIALS_FROM_POSTGRES", True):
                try:
                    _run_subprocess(
                        [
                            python,
                            str(_REPO_ROOT / "scripts" / "export_trialgpt_corpus_for_qdrant.py"),
                            "--output",
                            str(trials_export_path),
                        ],
                        cwd=_REPO_ROOT,
                        label="export_trialgpt_corpus",
                    )
                    trials_corpus = str(trials_export_path)
                except Exception as exc:
                    logger.warning(
                        "[QDRANT_INGEST] Postgres trial export failed (%s); using file corpus",
                        exc,
                    )
                    if not Path(trials_corpus).is_file():
                        raise
            elif not Path(trials_corpus).is_file():
                raise FileNotFoundError(f"Trials corpus not found: {trials_corpus}")
            trial_args = [
                python,
                "ingest_trials.py",
                "--json-path",
                trials_corpus,
                "--batch-size",
                str(batch_size),
            ]
            if recreate or trial_points == 0:
                trial_args.append("--recreate")
            _run_subprocess(trial_args, cwd=_RAG_DIR, label="ingest_trials")
            _state["trials_ingested"] = True

        _state["status"] = "completed"
        _state["message"] = "Qdrant ingest completed"
        return get_ingest_status()

    except Exception as exc:
        logger.exception("[QDRANT_INGEST] Failed")
        _state["status"] = "failed"
        _state["message"] = str(exc)
        return get_ingest_status()

    finally:
        _lock.release()


def maybe_start_background_ingest() -> None:
    """Start ingest on API boot when QDRANT_AUTO_INGEST_ON_STARTUP is enabled."""
    if not _env_bool("QDRANT_AUTO_INGEST_ON_STARTUP"):
        logger.info("[QDRANT_INGEST] Auto-ingest disabled (QDRANT_AUTO_INGEST_ON_STARTUP)")
        return

    def _worker():
        try:
            run_qdrant_ingest(force=_env_bool("QDRANT_INGEST_FORCE_ON_STARTUP"))
        except Exception:
            logger.exception("[QDRANT_INGEST] Background ingest worker failed")

    thread = threading.Thread(target=_worker, name="qdrant-auto-ingest", daemon=True)
    thread.start()
    logger.info("[QDRANT_INGEST] Background ingest thread started")
