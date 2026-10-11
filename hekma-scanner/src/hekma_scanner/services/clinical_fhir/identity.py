"""Mint and stamp Hekma vs FHIR identifiers without mutating caller dicts."""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional

from .models import HEKMA_CTMS_PAYLOAD_URL, HEKMA_ID_SYSTEM, HEKMA_SOURCE_SYSTEM, ClinicalSource

_HEKMA_NS = uuid.UUID("8f3c9e2a-1b4d-4a7e-9c11-7f3c9e2a1b4d")


def mint_hekma_id() -> str:
    """New Hekma id; never reuse an EHR resource.id."""
    return str(uuid.uuid4())


def stable_hekma_id(
    source: ClinicalSource,
    patient_id: str,
    module: str,
    mysql_record_id: Optional[int],
) -> str:
    """Stable UUID when the MySQL row id is known so updates hit the same FHIR row."""
    if mysql_record_id is None:
        return mint_hekma_id()
    name = f"{source.value}|{patient_id}|{module}|{int(mysql_record_id)}"
    return str(uuid.uuid5(_HEKMA_NS, name))


def stable_ehr_hekma_id(
    patient_id: str,
    org_connection_id: Optional[str],
    resource_type: str,
    fhir_id: str,
) -> str:
    """Stable Hekma id for an EHR resource across Fasten re-exports of the same FHIR id."""
    name = f"ehr|{patient_id}|{org_connection_id or ''}|{resource_type}|{fhir_id}"
    return str(uuid.uuid5(_HEKMA_NS, name))


def fhir_id_for_source(source: ClinicalSource, hekma_id: str, ehr_fhir_id: Optional[str]) -> str:
    """EHR keeps the vendor FHIR id; manual/scan use the Hekma UUID as FHIR id."""
    if source is ClinicalSource.EHR:
        if not ehr_fhir_id:
            raise ValueError("EHR rows require the inbound FHIR resource id")
        return str(ehr_fhir_id)
    return hekma_id


def stamp_hekma_identifiers(
    resource: Dict[str, Any],
    *,
    hekma_id: str,
    fhir_id: str,
    source: ClinicalSource,
) -> Dict[str, Any]:
    """Copy resource, set id, and add Hekma identifier entries."""
    stamped = copy.deepcopy(resource)
    stamped["id"] = fhir_id
    identifiers: List[Dict[str, Any]] = list(stamped.get("identifier") or [])
    identifiers = [
        item
        for item in identifiers
        if not (
            isinstance(item, dict)
            and item.get("system") in (HEKMA_ID_SYSTEM, HEKMA_SOURCE_SYSTEM)
        )
    ]
    identifiers.append({"system": HEKMA_ID_SYSTEM, "value": hekma_id})
    identifiers.append({"system": HEKMA_SOURCE_SYSTEM, "value": source.value})
    stamped["identifier"] = identifiers
    return stamped


def stamp_ctms_payload(resource: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the original API/scan fields on the FHIR resource for lossless list/get."""
    import json

    stamped = copy.deepcopy(resource)
    clean = {
        key: value
        for key, value in (payload or {}).items()
        if key not in {"extractedData", "extracted_data"}
    }
    extensions = [
        item
        for item in (stamped.get("extension") or [])
        if not (isinstance(item, dict) and item.get("url") == HEKMA_CTMS_PAYLOAD_URL)
    ]
    extensions.append(
        {"url": HEKMA_CTMS_PAYLOAD_URL, "valueString": json.dumps(clean, default=str)}
    )
    stamped["extension"] = extensions
    return stamped


def read_ctms_payload(resource: Dict[str, Any]) -> Dict[str, Any]:
    """Return the stamped API payload, or {} when the extension is missing."""
    import json

    if not isinstance(resource, dict):
        return {}
    for item in resource.get("extension") or []:
        if not isinstance(item, dict) or item.get("url") != HEKMA_CTMS_PAYLOAD_URL:
            continue
        try:
            parsed = json.loads(item.get("valueString") or "{}")
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
