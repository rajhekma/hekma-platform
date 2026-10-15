from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime, timezone
import uuid


def utcnow():
    return datetime.now(timezone.utc)


class TokenMapping(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    org_id: str
    original_value: str
    tokenized_value: str
    entity_type: str
    policy_applied: str = "anonymize"
    context_hash: Optional[str] = ""
    confidence: float = 1.0
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: Optional[datetime] = None
    restored_at: Optional[datetime] = None
    restored_by: Optional[str] = None


class RestoreRequest(BaseModel):
    tokenized_values: List[str]
    entity_types: Optional[List[str]] = None
    org_id: str = "default"
    requester_id: str = "system"
    ip_address: str = "127.0.0.1"
    purpose: str = "patient_care"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tokenized_values": [
                    "ANON_PERSON_Fisher",
                    "ANON_PERSON_Elijah",
                    "ANON_EMAIL_privacyds",
                    "ANON_PHONE_555"
                ],
                "entity_types": ["PERSON", "EMAIL", "PHONE"],
                "org_id": "203674",
                "requester_id": "dr_connor_948",
                "ip_address": "10.0.4.12",
                "purpose": "direct_patient_care_treatment"
            }
        }
    )


class RestoreResult(BaseModel):
    original_value: str
    tokenized_value: str
    entity_type: str
    restored: bool

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "original_value": "Elijah Fisher",
                "tokenized_value": "ANON_PERSON_Fisher",
                "entity_type": "PERSON",
                "restored": True
            }
        }
    )


class RestoreTextRequest(BaseModel):
    text: str
    org_id: str = "default"
    requester_id: str = "system"
    ip_address: str = "127.0.0.1"
    purpose: str = "patient_care"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "Patient ANON_PERSON_Fisher visited Dr. ANON_PERSON_Connor for Type 2 diabetes consult.",
                "org_id": "203674",
                "requester_id": "dr_connor_948",
                "ip_address": "10.0.4.12",
                "purpose": "ehr_clinical_review"
            }
        }
    )