"""Maps MySQL CTMS row ids to stable Hekma FHIR ids."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from ..awsutils.postgresql_utils import pg_transaction


class FhirLinkRepository(Protocol):
    def get(
        self, patient_id: str, module: str, mysql_record_id: int
    ) -> Optional[Dict[str, Any]]:
        ...

    def save(
        self,
        *,
        hekma_id: str,
        patient_id: str,
        module: str,
        mysql_record_id: Optional[int],
        fhir_resource_type: str,
        fhir_id: str,
        source: str,
        document_id: Optional[str],
    ) -> None:
        ...


class PostgresFhirLinkRepository:
    """Persistence for hekma_fhir_link; no FHIR mapping here."""

    def get(
        self, patient_id: str, module: str, mysql_record_id: int
    ) -> Optional[Dict[str, Any]]:
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                """
                SELECT hekma_id, patient_id, module, mysql_record_id,
                       fhir_resource_type, fhir_id, source, document_id
                FROM hekma_fhir_link
                WHERE patient_id = %s AND module = %s AND mysql_record_id = %s
                LIMIT 1
                """,
                (str(patient_id), module, int(mysql_record_id)),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def save(
        self,
        *,
        hekma_id: str,
        patient_id: str,
        module: str,
        mysql_record_id: Optional[int],
        fhir_resource_type: str,
        fhir_id: str,
        source: str,
        document_id: Optional[str],
    ) -> None:
        with pg_transaction(dict_cursor=False) as (_, cur):
            cur.execute(
                """
                INSERT INTO hekma_fhir_link (
                    hekma_id, patient_id, module, mysql_record_id,
                    fhir_resource_type, fhir_id, source, document_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (hekma_id) DO UPDATE SET
                    fhir_id = EXCLUDED.fhir_id,
                    source = EXCLUDED.source,
                    document_id = COALESCE(EXCLUDED.document_id, hekma_fhir_link.document_id),
                    mysql_record_id = COALESCE(EXCLUDED.mysql_record_id, hekma_fhir_link.mysql_record_id),
                    updated_at = NOW()
                """,
                (
                    hekma_id,
                    str(patient_id),
                    module,
                    mysql_record_id,
                    fhir_resource_type,
                    fhir_id,
                    source,
                    document_id,
                ),
            )
