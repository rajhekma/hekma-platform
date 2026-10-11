import logging
from uuid import UUID

from psycopg2.extras import Json
from ..services.privacy.privacy_client import privacy_client

logger = logging.getLogger("fasten_ehr")


from .db_schema import ensure_hekma_identity_columns


def insert_fasten_resource(
    cur,
    patient_id: str,
    hekma_mail_id: str | None,
    resource: dict,
    org_connection_id: str | None = None,
    hekma_id: str | None = None,
    source: str = "ehr",
    anonymized_resource: dict | None = None,
):
    """Insert one EHR FHIR resource. Existing (patient, org, resource_id) rows are left unchanged."""
    resource_type = resource.get("resourceType")
    resource_id = resource.get("id")

    if not resource_type:
        return

    table = f"fastenhealth_{resource_type.lower()}"
    ensure_hekma_identity_columns(cur, table)

    if hekma_id is None and resource_id:
        from ..services.clinical_fhir.identity import stable_ehr_hekma_id
        from ..services.clinical_fhir.identity import stamp_hekma_identifiers
        from ..services.clinical_fhir.models import ClinicalSource

        hekma_id = stable_ehr_hekma_id(
            patient_id, org_connection_id, str(resource_type), str(resource_id)
        )
        resource = stamp_hekma_identifiers(
            resource,
            hekma_id=hekma_id,
            fhir_id=str(resource_id),
            source=ClinicalSource.EHR,
        )
    elif hekma_id is None:
        from ..services.clinical_fhir.identity import mint_hekma_id

        hekma_id = mint_hekma_id()

    try:
        UUID(str(hekma_id))
    except (TypeError, ValueError):
        return

    ## Step 3 & 4: Intercept & Anonymize FHIR resource via Privacy Microservice (if not pre-anonymized)
    if anonymized_resource is None:
        try:
            anonymized_resource = privacy_client.anonymize_fhir_resource(resource, org_id=patient_id)
        except Exception as e:
            logger.warning("Privacy anonymization fallback for %s/%s: %s", resource_type, resource_id, e)
            anonymized_resource = resource

    cur.execute(
        f"""
        INSERT INTO {table}
            (patient_id, hekma_mail_id, org_connection_id, resource_id,
             hekma_id, source, raw_resource)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (patient_id, org_connection_id, resource_id) DO NOTHING
        """,
        (
            patient_id,
            hekma_mail_id,
            org_connection_id,
            resource_id,
            hekma_id,
            source,
            Json(anonymized_resource),
        ),
    )



def insert_fasten_resource_batch(
    cur,
    patient_id: str,
    hekma_mail_id: str | None,
    resources: list[dict],
    org_connection_id: str | None = None,
    source: str = "ehr",
) -> int:
    """Batch-anonymizes multiple FHIR resources via PDS and inserts them into PostgreSQL."""
    if not resources:
        return 0

    try:
        anonymized_batch = privacy_client.anonymize_fhir_batch(resources, org_id=patient_id)
    except Exception as e:
        logger.warning("Batch anonymization fallback: %s", e)
        anonymized_batch = resources

    count = 0
    for orig_res, anon_res in zip(resources, anonymized_batch):
        insert_fasten_resource(
            cur,
            patient_id=patient_id,
            hekma_mail_id=hekma_mail_id,
            resource=orig_res,
            org_connection_id=org_connection_id,
            source=source,
            anonymized_resource=anon_res,
        )
        count += 1
    return count
