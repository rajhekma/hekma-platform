from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
import uuid


class Organization(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    api_key_hash: str
    settings: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OrganizationCreate(BaseModel):
    name: str


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    api_key: str
    settings: Dict[str, Any]
    created_at: str
    updated_at: str