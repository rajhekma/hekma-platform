"""SQL predicates so EHR tiles and Internal tiles do not double-count."""

from ..utils.vital_signs_normalization import normalize_vital_sign_record

HEKMA_SOURCE_PREDICATE = """(
  COALESCE(source, '') IN ('manual', 'scan')
  OR COALESCE(org_connection_id, '') IN ('hekma:manual', 'hekma:scan')
)"""

EHR_SOURCE_PREDICATE = """(
  COALESCE(source, 'ehr') = 'ehr'
  AND (org_connection_id IS NULL OR org_connection_id NOT LIKE 'hekma:%%')
)"""

# Soft-deleted Hekma rows (plus-button / scan delete) must drop from Internal tiles.
# clinicalStatus inactive/resolved is a living user-selected status, not a delete.
HEKMA_ACTIVE_PREDICATE = """(
  COALESCE(raw_resource->>'status', '') <> 'entered-in-error'
  AND COALESCE(raw_resource->'verificationStatus'->'coding'->0->>'code', '') <> 'entered-in-error'
)"""

INTERNAL_TO_MODULE = {
    "InternalCondition": "diagnosis",
    "InternalAllergyIntolerance": "allergies",
    "InternalProcedure": "procedures",
    "InternalImmunization": "immunization",
    "InternalObservation": "lab_reports",
    "InternalObservationVital": "vital_signs",
}

INTERNAL_TO_TABLE = {
    "InternalCondition": ("fastenhealth_condition", None),
    "InternalAllergyIntolerance": ("fastenhealth_allergyintolerance", None),
    "InternalProcedure": ("fastenhealth_procedure", None),
    "InternalImmunization": ("fastenhealth_immunization", None),
    "InternalObservation": ("fastenhealth_observation", "laboratory"),
    "InternalObservationVital": ("fastenhealth_observation", "vital-signs"),
}


def to_internal_dashboard_row(sub_type: str, record: dict, patient_id: str) -> dict:
    """Shape a Postgres Hekma row like the old MySQL Internal* SELECT."""
    rid = record.get("id")
    date = (
        record.get("startDate")
        or record.get("onsetDate")
        or record.get("onsetDateTime")
        or record.get("resultDate")
        or record.get("dateOfObservation")
        or record.get("vaccinationDate")
        or record.get("onset")
        or ""
    )
    date = str(date)[:10] if date else ""
    substance = record.get("substance") or record.get("name")
    base = {
        "internal": "Y",
        "internal_ref": rid,
        "notes": record.get("notes"),
        "sort_date": date,
        "createdBy": patient_id,
    }
    if sub_type == "InternalCondition":
        status_str = str(record.get("status") or "").lower()
        end_date = str(record.get("endDate") or "")[:10] or None
        if status_str in ("active", "recurrence", "relapse"):
            end_date = None
        base.update(
            {
                "Condition": record.get("conditionName") or record.get("name"),
                "Status": status_str,
                "date_of_diagnosis": date,
                "start_date": date,
                "end_date": end_date,
            }
        )
    elif sub_type == "InternalAllergyIntolerance":
        status_str = str(record.get("status") or "").lower()
        end_date = str(record.get("endDate") or "")[:10] or None
        if status_str in ("active", ""):
            end_date = None
        base.update(
            {
                "name": substance,
                "Name": substance,
                "substance": substance,
                "status": status_str,
                "criticality": record.get("severity") or record.get("criticality"),
                "severity": record.get("severity") or record.get("criticality"),
                "onset": date,
                "allergy_type": record.get("allergyType"),
                "allergyType": record.get("allergyType"),
                "category": record.get("category"),
                "start_date": date,
                "startDate": date,
                "end_date": end_date,
                "endDate": end_date,
            }
        )
    elif sub_type == "InternalProcedure":
        base.update(
            {
                "Name": record.get("procedureName"),
                "Status": str(record.get("status") or "").lower(),
                "date_of_procedure": date,
                "location": record.get("location"),
                "reason": record.get("reason"),
                "start_date": date,
                "end_date": str(record.get("endDate") or "")[:10] or None,
            }
        )
    elif sub_type == "InternalImmunization":
        base.update(
            {
                "Name": record.get("vaccineName"),
                "date_of_immunization": date,
            }
        )
    elif sub_type == "InternalObservation":
        base.update(
            {
                "Name": record.get("testName"),
                "Status": "final",
                "date_of_observation": date,
                "category_code": "laboratory",
                "testValue": record.get("testValue"),
                "unit": record.get("unit"),
                "referenceRange": record.get("referenceRange"),
            }
        )
    elif sub_type == "InternalObservationVital":
        record = normalize_vital_sign_record(record)
        base.update(
            {
                "Name": record.get("type"),
                "Status": "final",
                "date_of_observation": date,
                "category_code": "vital-signs",
                "refValue1": record.get("refValue1"),
                "refValue2": record.get("refValue2"),
                "metric": record.get("metric"),
            }
        )
    return base
