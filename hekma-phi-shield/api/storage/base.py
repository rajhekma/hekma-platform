from typing import Protocol, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class TokenMapping:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    org_id: str = ""
    original_value: str = ""
    tokenized_value: str = ""
    entity_type: str = ""
    policy_applied: str = ""
    context_hash: str = ""
    confidence: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    restored_at: Optional[datetime] = None
    restored_by: Optional[str] = None


@dataclass
class PIIPolicy:
    entity_type: str = ""
    policy_type: str = "ignore"
    anonymize_strategy: str = "randomized"
    custom_replacement: Optional[str] = None
    applies_to_internal: bool = True
    applies_to_external: bool = True


@dataclass
class AuditEntry:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    org_id: str = ""
    action: str = ""
    entity_type: Optional[str] = None
    tokenized_value: Optional[str] = None
    performed_by: str = ""
    ip_address: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


class TokenStore(Protocol):
    async def save(self, mapping: TokenMapping) -> TokenMapping: ...
    async def get_by_token(
        self, org_id: str, token: str, entity_types: Optional[List[str]] = None
    ) -> Optional[TokenMapping]: ...
    async def get_by_original(self, org_id: str, original_value: str) -> Optional[TokenMapping]: ...
    async def get_all_for_org(self, org_id: str) -> List[TokenMapping]: ...
    async def update(self, mapping: TokenMapping) -> TokenMapping: ...
    def encrypt(self, value: str) -> str: ...
    def decrypt(self, value: str) -> str: ...


class PolicyStore(Protocol):
    async def get_by_org(self, org_id: str) -> List[PIIPolicy]: ...
    async def upsert_many(self, org_id: str, policies: List[PIIPolicy]) -> List[PIIPolicy]: ...
    async def get_defaults(self) -> List[PIIPolicy]: ...
    async def apply_preset(self, org_id: str, preset: str) -> List[PIIPolicy]: ...


class AuditLog(Protocol):
    async def log(self, entry: AuditEntry) -> None: ...
    async def get_for_org(self, org_id: str, limit: int = 100) -> List[AuditEntry]: ...


@dataclass
class OrgRecord:
    org_id: str = "default-org"
    name: str = "Default Organization"
    contact_email: Optional[str] = "admin@hekma.ai"
    api_key_hash: Optional[str] = None
    raw_api_key_preview: Optional[str] = "org_sk_live_••••••••••••••••"
    audit_retention_days: int = 0
    token_ttl_days: int = 0
    settings_json: str = "{}"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class OrgStore(Protocol):
    async def list_orgs(self) -> List[OrgRecord]: ...
    async def get_org(self, org_id: str) -> OrgRecord: ...
    async def save_org(self, org: OrgRecord) -> OrgRecord: ...
    async def rotate_key(self, org_id: str) -> tuple[OrgRecord, str]: ...