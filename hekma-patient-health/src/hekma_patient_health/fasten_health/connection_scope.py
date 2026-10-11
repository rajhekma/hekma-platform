import logging

logger = logging.getLogger("fasten_ehr")


def list_fastenhealth_tables(cur) -> list[str]:
    cur.execute(
        """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename LIKE 'fastenhealth\\_%' ESCAPE '\\'
        ORDER BY tablename
        """
    )
    return [row[0] for row in cur.fetchall()]


def delete_patient_connection_resources(
    cur,
    patient_id: str,
    org_connection_id: str,
) -> dict[str, int]:
    """
    Remove all ingested Fasten rows for one patient + health-system connection.
    Called before re-ingesting a full EHI export (Option B).
    """
    deleted: dict[str, int] = {}
    for table in list_fastenhealth_tables(cur):
        cur.execute(
            f"""
            DELETE FROM {table}
            WHERE patient_id = %s
              AND org_connection_id = %s
            """,
            (patient_id, org_connection_id),
        )
        if cur.rowcount:
            deleted[table] = cur.rowcount

    if deleted:
        logger.info(
            "Removed prior Fasten rows | patient_id=%s | org_connection_id=%s | deleted=%s",
            patient_id,
            org_connection_id,
            deleted,
        )
    else:
        logger.info(
            "No prior Fasten rows to remove | patient_id=%s | org_connection_id=%s",
            patient_id,
            org_connection_id,
        )

    return deleted
