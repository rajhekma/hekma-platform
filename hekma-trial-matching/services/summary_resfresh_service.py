"""
Refresh patient summaries from Postgres FHIR into compose_summary_block.

Legacy entrypoint used by POST /batch/refresh-patient-summaries.
Prefer scripts/run_patient_summary_embed_job.py for sharded production backfills.
"""

from __future__ import annotations

import logging

from repositories.mysql_repo import get_all_source_ids
from services.patient_summary_batch_service import process_patient_summary

logger = logging.getLogger(__name__)


def refresh_summaries(
    *,
    skip_disease_llm: bool = True,
    limit: int | None = None,
):
    stats = {
        "total_mysql_patients": 0,
        "patients_with_pg_data": 0,
        "generated": 0,
        "regenerated": 0,
        "skipped": 0,
        "no_pg_data": 0,
        "failed": 0,
    }

    logger.info("Starting patient summary refresh job (compose_summary_block)")

    processed = 0
    for patient_id in get_all_source_ids():
        if limit is not None and processed >= limit:
            break
        processed += 1
        stats["total_mysql_patients"] += 1
        logger.info("Processing patient_id=%s", patient_id)

        result = process_patient_summary(
            patient_id,
            skip_disease_llm=skip_disease_llm,
        )
        status = result.get("status")
        if status == "no_pg_data":
            stats["no_pg_data"] += 1
        elif status == "skipped":
            stats["patients_with_pg_data"] += 1
            stats["skipped"] += 1
        elif status == "generated":
            stats["patients_with_pg_data"] += 1
            stats["generated"] += 1
        elif status == "regenerated":
            stats["patients_with_pg_data"] += 1
            stats["regenerated"] += 1
        elif status == "failed":
            stats["failed"] += 1
            logger.error(
                "Failed processing patient_id=%s: %s",
                patient_id,
                result.get("error"),
            )

    logger.info("Refresh completed. Final stats: %s", stats)
    return stats
