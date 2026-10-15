"""
Phase 0 coverage: MySQL subjectIds vs Postgres FHIR vs compose_summary_block.
"""

from __future__ import annotations

from datetime import datetime, timezone

from repositories.compose_repo import count_compose_summary_block
from repositories.mysql_repo import count_source_ids, get_source_ids_page
from repositories.postgres_repo import (
    fetch_compose_block_timestamps,
    filter_patient_ids_with_pg_row,
    get_latest_timestamp,
)

PAGE_SIZE = 500


def build_coverage_report(*, limit: int | None = None, page_size: int = PAGE_SIZE) -> dict:
    mysql_total = count_source_ids()
    scanned = 0
    with_pg_clinical = 0
    already_in_compose = 0
    eligible_to_generate = 0
    no_pg_data = 0
    up_to_date = 0
    stale_or_missing = 0

    offset = 0
    while True:
        if limit is not None and scanned >= limit:
            break
        take = page_size
        if limit is not None:
            take = min(page_size, limit - scanned)
        page = get_source_ids_page(take, offset)
        if not page:
            break

        pg_ids = filter_patient_ids_with_pg_row(page)
        compose_ts = fetch_compose_block_timestamps(page)

        for subject_id in page:
            scanned += 1
            if subject_id not in pg_ids:
                no_pg_data += 1
                continue

            latest_ts = get_latest_timestamp(subject_id)
            if not latest_ts:
                no_pg_data += 1
                continue

            with_pg_clinical += 1
            compose_row_ts = compose_ts.get(subject_id)
            if compose_row_ts is not None:
                already_in_compose += 1

            if compose_row_ts and compose_row_ts >= latest_ts:
                up_to_date += 1
            else:
                eligible_to_generate += 1
                stale_or_missing += 1

        offset += len(page)
        if len(page) < take:
            break

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mysql_with_subject": mysql_total,
        "scanned": scanned,
        "limit": limit,
        "with_pg_clinical": with_pg_clinical,
        "already_in_compose_summary_block": already_in_compose,
        "compose_summary_block_total_rows": count_compose_summary_block(),
        "up_to_date": up_to_date,
        "eligible_to_generate": eligible_to_generate,
        "stale_or_missing": stale_or_missing,
        "no_pg_data": no_pg_data,
        "note": (
            "Only eligible_to_generate should be summarized. "
            "no_pg_data IDs have MySQL mapping but no usable Postgres FHIR clinical data."
        ),
    }
