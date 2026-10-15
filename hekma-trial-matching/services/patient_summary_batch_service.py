"""
Resumable per-patient summarize pipeline → compose_summary_block.

- Skip when compose_summary_block is up-to-date vs FHIR latest timestamp
- Continue on per-patient failures
- Soft DLQ via JSONL
- LLM call retries with exponential backoff
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from repositories.compose_repo import (
    get_compose_summary_block_timestamp,
    upsert_compose_summary_block,
)
from repositories.mysql_repo import get_source_ids_page
from repositories.postgres_repo import (
    get_latest_timestamp,
    get_patient_row,
    get_table_rows,
)
from services.disease_list_util import (
    attach_icd_diseases_metadata,
    build_icd_official_disease_list,
    derive_disease_list_from_blocks,
)
from services.patient_block_service import (
    attach_generation_metadata,
    generate_block_summary_from_text,
)
from services.summary_builder import build_structured_json
from services.summary_llm_service import generate_summary
from utils.llm_config import resolve_compose_llm_service, resolve_compose_model

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 500
DEFAULT_MAX_RETRIES = 3
DEFAULT_ERROR_PATH = Path("results/patient_summary_errors.jsonl")
DEFAULT_PROGRESS_DIR = Path("results/patient_summary_progress")


def _shard_owns(subject_id: str, shards: int, shard_id: int) -> bool:
    if shards <= 1:
        return True
    digest = hashlib.md5(subject_id.encode("utf-8")).hexdigest()
    return int(digest, 16) % shards == shard_id


def append_dlq(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def load_dlq_subject_ids(path: Path) -> list[str]:
    if not path.exists():
        return []
    ids: list[str] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("resolved"):
                continue
            sid = str(row.get("subject_id") or "").strip()
            if sid and sid not in seen:
                seen.add(sid)
                ids.append(sid)
    return ids


def _call_with_retries(
    fn: Callable[[], Any],
    *,
    label: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt >= max_retries - 1:
                break
            wait = 2**attempt
            logger.warning(
                "%s failed (attempt %s/%s): %s; retrying in %ss",
                label,
                attempt + 1,
                max_retries,
                exc,
                wait,
            )
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def process_patient_summary(
    patient_id: str,
    *,
    skip_disease_llm: bool = True,
    model: str | None = None,
    llm_service: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    force: bool = False,
) -> dict[str, Any]:
    """
    Generate/upsert one patient into compose_summary_block.

    Returns status dict: status in
      no_pg_data | skipped | generated | regenerated | failed
    """
    model = resolve_compose_model(model)
    llm_service = resolve_compose_llm_service(llm_service)
    stage = "latest_timestamp"

    try:
        latest_ts = get_latest_timestamp(patient_id)
        if not latest_ts:
            return {"subject_id": patient_id, "status": "no_pg_data"}

        compose_ts = get_compose_summary_block_timestamp(patient_id)
        if not force and compose_ts and compose_ts >= latest_ts:
            return {
                "subject_id": patient_id,
                "status": "skipped",
                "compose_ts": compose_ts,
                "latest_ts": latest_ts,
            }

        stage = "fetch_fhir"
        patient_row = get_patient_row(patient_id)
        if not patient_row:
            return {"subject_id": patient_id, "status": "no_pg_data"}

        condition_rows = get_table_rows("condition", patient_id)
        allergy_rows = get_table_rows("allergy", patient_id)
        medication_rows = get_table_rows("medication_order", patient_id)
        immunization_rows = get_table_rows("immunization", patient_id)
        procedure_rows = get_table_rows("procedure", patient_id)
        observation_rows = get_table_rows("observation", patient_id)

        stage = "build_structured"
        fhir_structured = build_structured_json(
            patient_row,
            condition_rows,
            allergy_rows,
            medication_rows,
            immunization_rows,
            procedure_rows,
            observation_rows,
        )

        stage = "generate_summary"
        summary_text = _call_with_retries(
            lambda: generate_summary(
                fhir_structured,
                model=model,
                llm_service=llm_service,
            ),
            label=f"summary:{patient_id}",
            max_retries=max_retries,
        )

        stage = "generate_blocks"
        block_json = _call_with_retries(
            lambda: generate_block_summary_from_text(
                patient_id,
                summary_text,
                model=model,
                llm_service=llm_service,
            ),
            label=f"blocks:{patient_id}",
            max_retries=max_retries,
        )

        steps = ["summary", "block_summary"]
        disease_list: list[str] = []

        if skip_disease_llm:
            disease_list = derive_disease_list_from_blocks(block_json)
            steps.append("disease_list_raw")
        else:
            stage = "disease_list_icd"
            disease_list, icd_entries = _call_with_retries(
                lambda: build_icd_official_disease_list(
                    block_json,
                    model=model,
                    llm_service=llm_service,
                    patient_context=summary_text,
                ),
                label=f"icd:{patient_id}",
                max_retries=max_retries,
            )
            block_json = attach_icd_diseases_metadata(block_json, icd_entries)
            steps.append("disease_list_icd10")

        block_json = attach_generation_metadata(
            block_json,
            model=model,
            llm_service=llm_service,
            steps=steps,
        )

        stage = "upsert"
        upsert_compose_summary_block(
            patient_id,
            summary_text,
            block_json,
            disease_list,
            latest_ts,
            site_id=None,
        )

        status = "regenerated" if compose_ts else "generated"
        return {
            "subject_id": patient_id,
            "status": status,
            "disease_count": len(disease_list),
            "latest_ts": latest_ts,
        }
    except Exception as exc:
        logger.exception("Failed patient_id=%s stage=%s: %s", patient_id, stage, exc)
        return {
            "subject_id": patient_id,
            "status": "failed",
            "stage": stage,
            "error": str(exc),
        }


def run_summary_shard(
    *,
    shards: int = 1,
    shard_id: int = 0,
    limit: int | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    skip_disease_llm: bool = True,
    model: str | None = None,
    llm_service: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    force: bool = False,
    subject_ids: list[str] | None = None,
    error_path: Path = DEFAULT_ERROR_PATH,
    progress_dir: Path = DEFAULT_PROGRESS_DIR,
) -> dict[str, Any]:
    """
    Process one shard of MySQL subjectIds (or an explicit subject_ids list).
    """
    if shards < 1:
        raise ValueError("shards must be >= 1")
    if shard_id < 0 or shard_id >= shards:
        raise ValueError(f"shard_id must be in [0, {shards})")

    stats = {
        "processed": 0,
        "generated": 0,
        "regenerated": 0,
        "skipped": 0,
        "no_pg_data": 0,
        "failed": 0,
        "shards": shards,
        "shard_id": shard_id,
        "updated_patient_ids": [],
    }

    progress_dir.mkdir(parents=True, exist_ok=True)
    progress_path = progress_dir / f"shard_{shard_id}_of_{shards}.json"

    def _persist_progress() -> None:
        payload = {
            **stats,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Avoid huge progress files
        payload["updated_patient_ids"] = stats["updated_patient_ids"][-200:]
        progress_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def _eligible_done() -> int:
        return (
            stats["generated"]
            + stats["regenerated"]
            + stats["skipped"]
            + stats["failed"]
        )

    def _handle_result(result: dict[str, Any]) -> None:
        stats["processed"] += 1
        status = result.get("status")
        sid = result.get("subject_id")
        if status == "no_pg_data":
            stats["no_pg_data"] += 1
        elif status == "skipped":
            stats["skipped"] += 1
        elif status == "generated":
            stats["generated"] += 1
            if sid:
                stats["updated_patient_ids"].append(sid)
        elif status == "regenerated":
            stats["regenerated"] += 1
            if sid:
                stats["updated_patient_ids"].append(sid)
        elif status == "failed":
            stats["failed"] += 1
            append_dlq(
                error_path,
                {
                    "subject_id": sid,
                    "error": result.get("error"),
                    "stage": result.get("stage"),
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "shard_id": shard_id,
                    "shards": shards,
                },
            )
        if stats["processed"] % 25 == 0:
            _persist_progress()

    if subject_ids is not None:
        for subject_id in subject_ids:
            if not _shard_owns(subject_id, shards, shard_id):
                continue
            if limit is not None and _eligible_done() >= limit:
                break
            result = process_patient_summary(
                subject_id,
                skip_disease_llm=skip_disease_llm,
                model=model,
                llm_service=llm_service,
                max_retries=max_retries,
                force=force,
            )
            _handle_result(result)
        _persist_progress()
        return stats

    offset = 0
    while True:
        if limit is not None and _eligible_done() >= limit:
            break
        take = page_size
        page = get_source_ids_page(take, offset)
        if not page:
            break

        for subject_id in page:
            if limit is not None and _eligible_done() >= limit:
                break
            if not _shard_owns(subject_id, shards, shard_id):
                continue
            result = process_patient_summary(
                subject_id,
                skip_disease_llm=skip_disease_llm,
                model=model,
                llm_service=llm_service,
                max_retries=max_retries,
                force=force,
            )
            _handle_result(result)

        offset += len(page)
        if len(page) < take:
            break

    _persist_progress()
    return stats
