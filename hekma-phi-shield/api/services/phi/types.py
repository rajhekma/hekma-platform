"""Catalog of PHI entity types and human-readable labels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class PhiEntityType:
    """One PHI label the detector may return."""

    name: str
    label: str
    description: str


# HIPAA Safe Harbor identifiers + common clinical PHI useful for healthcare text.
PHI_ENTITY_TYPES: List[PhiEntityType] = [
    PhiEntityType("PATIENT_NAME", "Patient Name", "Patient or subject name"),
    PhiEntityType("PROVIDER_NAME", "Provider Name", "Clinician / care provider name"),
    PhiEntityType("FACILITY_NAME", "Facility Name", "Hospital, clinic, or care facility"),
    PhiEntityType("DATE_OF_BIRTH", "Date of Birth", "Birth date or DOB"),
    PhiEntityType("ADMISSION_DATE", "Admission Date", "Admission / encounter date"),
    PhiEntityType("DISCHARGE_DATE", "Discharge Date", "Discharge date"),
    PhiEntityType("AGE_OVER_89", "Age Over 89", "Age 90+ (HIPAA Safe Harbor)"),
    PhiEntityType("PHONE_NUMBER", "Phone Number", "Telephone number"),
    PhiEntityType("FAX_NUMBER", "Fax Number", "Fax number"),
    PhiEntityType("EMAIL_ADDRESS", "Email Address", "Email address"),
    PhiEntityType("SOCIAL_SECURITY_NUMBER", "SSN", "Social Security Number"),
    PhiEntityType("MEDICAL_RECORD_NUMBER", "MRN", "Medical record number"),
    PhiEntityType(
        "HEALTH_PLAN_BENEFICIARY_NUMBER",
        "Health Plan ID",
        "Health plan beneficiary number",
    ),
    PhiEntityType("ACCOUNT_NUMBER", "Account Number", "Account or billing number"),
    PhiEntityType(
        "CERTIFICATE_LICENSE_NUMBER",
        "License Number",
        "Certificate or license number",
    ),
    PhiEntityType("VEHICLE_IDENTIFIER", "Vehicle ID", "VIN or license plate"),
    PhiEntityType("DEVICE_IDENTIFIER", "Device ID", "Device serial / identifier"),
    PhiEntityType("URL", "URL", "Web URL"),
    PhiEntityType("IP_ADDRESS", "IP Address", "IP address"),
    PhiEntityType("BIOMETRIC_IDENTIFIER", "Biometric ID", "Biometric identifier"),
    PhiEntityType("PHOTO_IDENTIFIER", "Photo ID", "Full-face photo / image identifier"),
    PhiEntityType(
        "GEOGRAPHIC_LOCATION",
        "Geographic Location",
        "Address or location smaller than state",
    ),
    PhiEntityType("DIAGNOSIS", "Diagnosis", "Diagnosis or ICD-coded condition"),
    PhiEntityType("CONDITION", "Condition", "Clinical condition / symptom"),
    PhiEntityType("MEDICATION", "Medication", "Drug or medication name/dose"),
    PhiEntityType("PROCEDURE", "Procedure", "Clinical procedure"),
    PhiEntityType("LAB_RESULT", "Lab Result", "Lab / diagnostic result"),
    PhiEntityType("TREATMENT", "Treatment", "Treatment plan or therapy"),
    PhiEntityType(
        "OTHER_UNIQUE_IDENTIFIER",
        "Other Unique ID",
        "Any other unique identifying number/code",
    ),
]

PHI_ENTITY_TYPE_NAMES: List[str] = [t.name for t in PHI_ENTITY_TYPES]
PHI_LABELS: Dict[str, str] = {t.name: t.label for t in PHI_ENTITY_TYPES}
PHI_DESCRIPTIONS: Dict[str, str] = {t.name: t.description for t in PHI_ENTITY_TYPES}


def label_for(entity_type: str) -> str:
    """Return the display label for a PHI entity type name."""
    return PHI_LABELS.get(entity_type.upper(), entity_type)
