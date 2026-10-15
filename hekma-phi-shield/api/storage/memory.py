from collections import defaultdict
from typing import Optional, List
import uuid
import hashlib
from datetime import datetime
from cryptography.fernet import Fernet

from api.storage.base import TokenStore, PolicyStore, AuditLog, TokenMapping, PIIPolicy, AuditEntry


class MemoryTokenStore:
    def __init__(self, encryption_key: bytes):
        self._data: dict[str, dict[str, TokenMapping]] = defaultdict(dict)
        self._by_original: dict[str, dict[str, TokenMapping]] = defaultdict(dict)
        self._cipher = Fernet(encryption_key)

    def encrypt(self, value: str) -> str:
        return self._cipher.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self._cipher.decrypt(value.encode()).decode()

    async def save(self, mapping: TokenMapping) -> TokenMapping:
        mapping.id = mapping.id or uuid.uuid4()
        mapping.created_at = mapping.created_at or datetime.utcnow()
        # Store original plaintext for hash, but encrypt for storage
        original_plaintext = mapping.original_value
        mapping.original_value = self.encrypt(mapping.original_value)
        self._data[mapping.org_id][mapping.tokenized_value] = mapping
        orig_hash = self._hash(original_plaintext)
        self._by_original[mapping.org_id][orig_hash] = mapping
        return mapping

    async def get_by_token(
        self, org_id: str, token: str, entity_types: Optional[List[str]] = None
    ) -> Optional[TokenMapping]:
        mapping = self._data.get(org_id, {}).get(token)
        if mapping and (not entity_types or mapping.entity_type in entity_types):
            return TokenMapping(
                id=mapping.id,
                org_id=mapping.org_id,
                original_value=self.decrypt(mapping.original_value),
                tokenized_value=mapping.tokenized_value,
                entity_type=mapping.entity_type,
                policy_applied=mapping.policy_applied,
                context_hash=mapping.context_hash,
                confidence=mapping.confidence,
                created_at=mapping.created_at,
                expires_at=mapping.expires_at,
                restored_at=mapping.restored_at,
                restored_by=mapping.restored_by,
            )
        return None

    async def get_by_original(self, org_id: str, original_value: str) -> Optional[TokenMapping]:
        orig_hash = self._hash(original_value)
        mapping = self._by_original.get(org_id, {}).get(orig_hash)
        if mapping:
            return TokenMapping(
                id=mapping.id,
                org_id=mapping.org_id,
                original_value=self.decrypt(mapping.original_value),
                tokenized_value=mapping.tokenized_value,
                entity_type=mapping.entity_type,
                policy_applied=mapping.policy_applied,
                context_hash=mapping.context_hash,
                confidence=mapping.confidence,
                created_at=mapping.created_at,
                expires_at=mapping.expires_at,
                restored_at=mapping.restored_at,
                restored_by=mapping.restored_by,
            )
        return None

    async def get_all_for_org(self, org_id: str) -> List[TokenMapping]:
        mappings = list(self._data.get(org_id, {}).values())
        result = []
        for m in mappings:
            m_copy = TokenMapping(
                id=m.id,
                org_id=m.org_id,
                original_value=self.decrypt(m.original_value),
                tokenized_value=m.tokenized_value,
                entity_type=m.entity_type,
                policy_applied=m.policy_applied,
                context_hash=m.context_hash,
                confidence=m.confidence,
                created_at=m.created_at,
                expires_at=m.expires_at,
                restored_at=m.restored_at,
                restored_by=m.restored_by,
            )
            result.append(m_copy)
        return result

    async def update(self, mapping: TokenMapping) -> TokenMapping:
        original_plaintext = mapping.original_value
        if self._is_encrypted(mapping.original_value):
            original_plaintext = self.decrypt(mapping.original_value)
        else:
            mapping.original_value = self.encrypt(mapping.original_value)
        
        self._data[mapping.org_id][mapping.tokenized_value] = mapping
        
        # Update _by_original index
        orig_hash = self._hash(original_plaintext)
        self._by_original[mapping.org_id][orig_hash] = mapping
        return mapping

    def _is_encrypted(self, value: str) -> bool:
        if not value:
            return False
        try:
            self.decrypt(value)
            return True
        except Exception:
            return False

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()


class MemoryPolicyStore:
    def __init__(self):
        self._policies: dict[str, List[PIIPolicy]] = defaultdict(list)
        self._defaults: List[PIIPolicy] = []

    async def get_by_org(self, org_id: str) -> List[PIIPolicy]:
        return self._policies.get(org_id, self._defaults.copy())

    async def upsert_many(self, org_id: str, policies: List[PIIPolicy]) -> List[PIIPolicy]:
        self._policies[org_id] = policies
        return policies

    async def get_defaults(self) -> List[PIIPolicy]:
        return self._defaults.copy()

    def set_defaults(self, defaults: List[PIIPolicy]) -> None:
        self._defaults = defaults

    async def apply_preset(self, org_id: str, preset: str) -> List[PIIPolicy]:
        from api.models.policy import PRESETS, PolicyType, AnonymizeStrategy
        if preset not in PRESETS:
            raise ValueError(f"Unknown preset: {preset}")
        policies = [
            PIIPolicy(entity_type=et, policy_type=pt, anonymize_strategy=AnonymizeStrategy.RANDOMIZED)
            for et, pt in PRESETS[preset].items()
        ]
        self._policies[org_id] = policies
        return policies


class MemoryAuditLog:
    def __init__(self):
        self._logs: List[AuditEntry] = []

    async def log(self, entry: AuditEntry) -> None:
        entry.id = entry.id or uuid.uuid4()
        entry.created_at = entry.created_at or datetime.utcnow()
        self._logs.append(entry)

    async def get_for_org(self, org_id: str, limit: int = 100) -> List[AuditEntry]:
        return [e for e in reversed(self._logs) if e.org_id == org_id][:limit]