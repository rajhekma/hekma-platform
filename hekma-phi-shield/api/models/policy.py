from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class PolicyType(str, Enum):
    IGNORE = "ignore"
    ANONYMIZE = "anonymize"
    REDACT = "redact"


class AnonymizeStrategy(str, Enum):
    RANDOMIZED = "randomized"
    ALTERNATE = "alternate"


class PIIPolicy(BaseModel):
    entity_type: str
    policy_type: PolicyType
    anonymize_strategy: AnonymizeStrategy = AnonymizeStrategy.RANDOMIZED
    custom_replacement: Optional[str] = None
    applies_to_internal: bool = True
    applies_to_external: bool = True


class PIIPolicyCreate(BaseModel):
    entity_type: str
    policy_type: PolicyType
    anonymize_strategy: AnonymizeStrategy = AnonymizeStrategy.RANDOMIZED
    custom_replacement: Optional[str] = None
    applies_to_internal: bool = True
    applies_to_external: bool = True


class PIIPolicyResponse(PIIPolicyCreate):
    org_id: str
    created_at: str
    updated_at: str


class PolicyPreset(str, Enum):
    HIPAA = "HIPAA"
    GDPR = "GDPR"
    PCI = "PCI"
    MINIMAL = "MINIMAL"


PRESETS = {
    PolicyPreset.HIPAA: {
        "PERSON": PolicyType.ANONYMIZE,
        "PATIENT_ID": PolicyType.ANONYMIZE,
        "DATE": PolicyType.ANONYMIZE,
        "DATE_TIME": PolicyType.ANONYMIZE,
        "PHONE": PolicyType.ANONYMIZE,
        "EMAIL": PolicyType.ANONYMIZE,
        "ADDRESS": PolicyType.ANONYMIZE,
        "CITY": PolicyType.ANONYMIZE,
        "ZIP_CODE": PolicyType.ANONYMIZE,
        "ORGANIZATION": PolicyType.ANONYMIZE,
        "MEDICAL_RECORD_NUMBER": PolicyType.ANONYMIZE,
        "HEALTH_PLAN_NUMBER": PolicyType.ANONYMIZE,
        "IDENTIFIER": PolicyType.ANONYMIZE,
        "SSN": PolicyType.REDACT,
        "CREDIT_CARD": PolicyType.REDACT,
        "PASSPORT": PolicyType.REDACT,
        "SECRET_KEY": PolicyType.REDACT,
        "ACCOUNT_NUMBER": PolicyType.ANONYMIZE,
        "LICENSE_PLATE": PolicyType.REDACT,
        "DEVICE_ID": PolicyType.REDACT,
        "IP_ADDRESS": PolicyType.REDACT,
        "URL": PolicyType.REDACT,
    },
    PolicyPreset.GDPR: {
        "PERSON": PolicyType.ANONYMIZE,
        "EMAIL": PolicyType.ANONYMIZE,
        "PHONE": PolicyType.ANONYMIZE,
        "ADDRESS": PolicyType.ANONYMIZE,
        "CITY": PolicyType.ANONYMIZE,
        "ZIP_CODE": PolicyType.ANONYMIZE,
        "IP_ADDRESS": PolicyType.REDACT,
        "DATE": PolicyType.ANONYMIZE,
        "IDENTIFIER": PolicyType.REDACT,
    },
    PolicyPreset.PCI: {
        "CREDIT_CARD": PolicyType.REDACT,
        "CVV": PolicyType.REDACT,
        "EXPIRY_DATE": PolicyType.REDACT,
        "ACCOUNT_NUMBER": PolicyType.REDACT,
    },
    PolicyPreset.MINIMAL: {
        "SSN": PolicyType.REDACT,
        "CREDIT_CARD": PolicyType.REDACT,
        "PASSPORT": PolicyType.REDACT,
    },
}