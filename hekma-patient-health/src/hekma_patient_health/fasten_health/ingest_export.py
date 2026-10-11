import logging

from ..awsutils.postgresql_utils import pg_transaction
from .connection_scope import delete_patient_connection_resources
from .table_manager import ensure_fasten_tables
from .jsonl_reader import read_jsonl
from .resource_writer import insert_fasten_resource_batch

logger = logging.getLogger("fasten_ehr")

BATCH_SIZE = 50


def ingest_fasten_export(
    patient_id: str,
    hekma_mail_id: str | None,
    file_text: str,
    total_by_resource_type: dict,
    org_connection_id: str | None = None,
):
    ensure_fasten_tables(total_by_resource_type)

    inserted = {}

    with pg_transaction(dict_cursor=False) as (_, cur):
        if org_connection_id:
            delete_patient_connection_resources(cur, patient_id, org_connection_id)
        else:
            logger.warning(
                "Ingest without org_connection_id | patient_id=%s — "
                "rows will not be scoped per health system",
                patient_id,
            )

        chunk = []
        for resource in read_jsonl(file_text):
            rtype = resource.get("resourceType")
            if not rtype:
                continue

            chunk.append(resource)
            inserted[rtype] = inserted.get(rtype, 0) + 1

            if len(chunk) >= BATCH_SIZE:
                insert_fasten_resource_batch(
                    cur,
                    patient_id=patient_id,
                    hekma_mail_id=hekma_mail_id,
                    resources=chunk,
                    org_connection_id=org_connection_id,
                )
                chunk = []

        if chunk:
            insert_fasten_resource_batch(
                cur,
                patient_id=patient_id,
                hekma_mail_id=hekma_mail_id,
                resources=chunk,
                org_connection_id=org_connection_id,
            )

    return inserted
