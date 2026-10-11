"""Persist FHIR JSON into fastenhealth_* without changing Fasten EHR semantics."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from psycopg2.extras import Json

from ...awsutils.postgresql_utils import pg_transaction
from ...fasten_health.db_schema import create_fasten_table, ensure_hekma_identity_columns
from .models import ClinicalSource


class FhirResourceStore(Protocol):
    def upsert(
        self,
        *,
        patient_id: str,
        hekma_mail_id: Optional[str],
        org_connection_id: Optional[str],
        resource_id: str,
        hekma_id: str,
        source: ClinicalSource,
        resource: Dict[str, Any],
    ) -> Optional[int]:
        ...

    def mark_entered_in_error(
        self,
        *,
        resource_type: str,
        patient_id: str,
        org_connection_id: Optional[str],
        resource_id: str,
    ) -> None:
        ...


_verified_tables: set[str] = set()

_CONDITION_VER_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
_ALLERGY_VER_SYSTEM = (
    "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification"
)


def _retire_fhir_resource(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Soft-delete a FHIR row. Do not reuse clinicalStatus=inactive for this."""
    retired = dict(raw)
    resource_type = retired.get("resourceType")
    if resource_type == "AllergyIntolerance":
        retired["verificationStatus"] = {
            "coding": [
                {
                    "code": "entered-in-error",
                    "system": _ALLERGY_VER_SYSTEM,
                    "display": "Entered in Error",
                }
            ]
        }
    elif resource_type == "Condition":
        retired["verificationStatus"] = {
            "coding": [
                {
                    "code": "entered-in-error",
                    "system": _CONDITION_VER_SYSTEM,
                    "display": "Entered in Error",
                }
            ]
        }
    else:
        retired["status"] = "entered-in-error"
    return retired


class PostgresFastenStore:
    """Writes the same fastenhealth_{type} tables Fasten ingest uses."""

    def _ensure_table(self, cur, resource_type: str, table: str) -> None:
        if table in _verified_tables:
            return
        create_fasten_table(cur, str(resource_type))
        ensure_hekma_identity_columns(cur, table)
        _verified_tables.add(table)

    def upsert(
        self,
        *,
        patient_id: str,
        hekma_mail_id: Optional[str],
        org_connection_id: Optional[str],
        resource_id: str,
        hekma_id: str,
        source: ClinicalSource,
        resource: Dict[str, Any],
    ) -> None:
        resource_type = resource.get("resourceType")
        if not resource_type:
            raise ValueError("FHIR resourceType is required")
        table = f"fastenhealth_{str(resource_type).lower()}"
        with pg_transaction(dict_cursor=False) as (_, cur):
            self._ensure_table(cur, str(resource_type), table)
            cur.execute(
                f"""
                INSERT INTO {table}
                    (patient_id, hekma_mail_id, org_connection_id, resource_id,
                     hekma_id, source, raw_resource)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (hekma_id)
                DO UPDATE SET
                    raw_resource = EXCLUDED.raw_resource,
                    source = EXCLUDED.source,
                    resource_id = EXCLUDED.resource_id,
                    org_connection_id = EXCLUDED.org_connection_id,
                    hekma_mail_id = COALESCE(EXCLUDED.hekma_mail_id, {table}.hekma_mail_id)
                RETURNING id
                """,
                (
                    patient_id,
                    hekma_mail_id,
                    org_connection_id,
                    resource_id,
                    hekma_id,
                    source.value,
                    Json(resource),
                ),
            )
            row = cur.fetchone()
        return int(row[0]) if row else None

    def get_hekma_row(
        self,
        *,
        resource_type: str,
        patient_id: str,
        record_id: int,
    ) -> Optional[Dict[str, Any]]:
        table = f"fastenhealth_{resource_type.lower()}"
        with pg_transaction(dict_cursor=True) as (_, cur):
            self._ensure_table(cur, resource_type, table)
            cur.execute(
                f"""
                SELECT id, patient_id, hekma_id, source, resource_id, raw_resource, created_at
                FROM {table}
                WHERE id = %s AND patient_id = %s
                LIMIT 1
                """,
                (record_id, patient_id),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def list_hekma_rows(
        self,
        *,
        resource_type: str,
        patient_id: str,
        limit: int = 100,
        offset: int = 0,
        observation_category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        table = f"fastenhealth_{resource_type.lower()}"
        extra = ""
        params: list = [patient_id]
        if observation_category:
            extra = " AND raw_resource->'category'->0->'coding'->0->>'code' = %s"
            params.append(observation_category)
        params.extend([limit, offset])
        with pg_transaction(dict_cursor=True) as (_, cur):
            self._ensure_table(cur, resource_type, table)
            cur.execute(
                f"""
                SELECT id, patient_id, hekma_id, source, resource_id, raw_resource, created_at
                FROM {table}
                WHERE patient_id = %s
                  AND (
                    COALESCE(source, '') IN ('manual', 'scan')
                    OR org_connection_id IN ('hekma:manual', 'hekma:scan')
                  )
                  AND COALESCE(raw_resource->>'status', '') <> 'entered-in-error'
                  AND COALESCE(
                        raw_resource->'verificationStatus'->'coding'->0->>'code',
                        ''
                      ) <> 'entered-in-error'
                  {extra}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def mark_entered_in_error(

        self,
        *,
        resource_type: str,
        patient_id: str,
        org_connection_id: Optional[str],
        resource_id: str,
        hekma_id: Optional[str] = None,
    ) -> None:
        """Soft-retire a Hekma-sourced FHIR row so dashboard counts drop."""
        table = f"fastenhealth_{resource_type.lower()}"
        with pg_transaction(dict_cursor=True) as (_, cur):
            self._ensure_table(cur, resource_type, table)
            # Prefer lookup by hekma_id (stable deterministic key); fall back to resource_id
            if hekma_id:
                cur.execute(
                    f"SELECT raw_resource FROM {table} WHERE hekma_id = %s LIMIT 1",
                    (hekma_id,),
                )
            else:
                cur.execute(
                    f"""
                    SELECT raw_resource FROM {table}
                    WHERE patient_id = %s
                      AND resource_id = %s
                      AND org_connection_id IS NOT DISTINCT FROM %s
                    LIMIT 1
                    """,
                    (patient_id, resource_id, org_connection_id),
                )
            row = cur.fetchone()
            if not row:
                return
            raw = row["raw_resource"] if isinstance(row, dict) else row[0]
            if not isinstance(raw, dict):
                return
            retired = _retire_fhir_resource(raw)
            # Update by hekma_id if available (most reliable), else fall back to resource_id
            if hekma_id:
                cur.execute(
                    f"UPDATE {table} SET raw_resource = %s WHERE hekma_id = %s",
                    (Json(retired), hekma_id),
                )
            else:
                cur.execute(
                    f"""
                    UPDATE {table}
                    SET raw_resource = %s
                    WHERE patient_id = %s
                      AND resource_id = %s
                      AND org_connection_id IS NOT DISTINCT FROM %s
                    """,
                    (Json(retired), patient_id, resource_id, org_connection_id),
                )

