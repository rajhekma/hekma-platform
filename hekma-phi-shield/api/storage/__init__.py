import json
import aiofiles
from pathlib import Path
from datetime import datetime, timezone
import uuid

from api.config.settings import settings
from api.storage.memory import MemoryTokenStore, MemoryPolicyStore, MemoryAuditLog
from api.storage.json_persist import JsonPersistenceMixin
from api.storage.base import TokenStore, PolicyStore, AuditLog, TokenMapping, PIIPolicy, AuditEntry


def get_token_store() -> TokenStore:
    backend = settings.STORAGE_BACKEND.lower()
    if backend == "postgresql":
        from api.storage.postgres import PostgresTokenStore
        return PostgresTokenStore()

    if backend == "json":
        class PersistentTokenStore(JsonPersistenceMixin, MemoryTokenStore):
            def __init__(self, *args, **kwargs):
                super().__init__(settings.DATA_DIR, *args, **kwargs)

            def _load(self):
                path = self._get_path("tokens")
                if path.exists():
                    self._data.clear()
                    self._by_original.clear()
                    with open(path) as f:
                        try:
                            items = json.load(f)
                            for item in items:
                                token = self._deserialize_token(item)
                                self._data[token.org_id][token.tokenized_value] = token
                                plaintext = self.decrypt(token.original_value)
                                orig_hash = self._hash(plaintext)
                                self._by_original[token.org_id][orig_hash] = token
                        except Exception as e:
                            print(f"Error loading tokens: {e}")

            async def save(self, mapping):
                result = await super().save(mapping)
                flat_data = [m for org_data in self._data.values() for m in org_data.values()]
                await self._persist("tokens", flat_data)
                return result

            async def update(self, mapping):
                result = await super().update(mapping)
                flat_data = [m for org_data in self._data.values() for m in org_data.values()]
                await self._persist("tokens", flat_data)
                return result

            async def get_all_for_org(self, org_id: str):
                self._load()
                return await super().get_all_for_org(org_id)

            async def get_by_token(self, org_id: str, token: str, entity_types = None):
                self._load()
                return await super().get_by_token(org_id, token, entity_types)

            async def get_by_original(self, org_id: str, original_value: str):
                self._load()
                return await super().get_by_original(org_id, original_value)

        return PersistentTokenStore(settings.ENCRYPTION_KEY.encode())
    return MemoryTokenStore(settings.ENCRYPTION_KEY.encode())


def get_policy_store() -> PolicyStore:
    backend = settings.STORAGE_BACKEND.lower()
    if backend == "postgresql":
        from api.storage.postgres import PostgresPolicyStore
        return PostgresPolicyStore()

    if backend == "json":
        class PersistentPolicyStore(JsonPersistenceMixin, MemoryPolicyStore):
            def __init__(self, *args, **kwargs):
                super().__init__(settings.DATA_DIR, *args, **kwargs)

            def _load(self):
                path = self._get_path("policies")
                if path.exists():
                    with open(path) as f:
                        for org_id, policies in json.load(f).items():
                            self._policies[org_id] = [PIIPolicy(**p) for p in policies]

            async def upsert_many(self, org_id, policies):
                result = await super().upsert_many(org_id, policies)
                await self._persist("policies", {k: [self._serialize(p) for p in v] for k, v in self._policies.items()})
                return result

            async def get_by_org(self, org_id: str):
                self._load()
                return await super().get_by_org(org_id)

        return PersistentPolicyStore()
    return MemoryPolicyStore()


def get_audit_log() -> AuditLog:
    backend = settings.STORAGE_BACKEND.lower()
    if backend == "postgresql":
        from api.storage.postgres import PostgresAuditLog
        return PostgresAuditLog()

    if backend == "json":
        class PersistentAuditLog(JsonPersistenceMixin, MemoryAuditLog):
            def __init__(self, *args, **kwargs):
                super().__init__(settings.DATA_DIR, *args, **kwargs)

            def _load(self):
                path = self._get_path("audit")
                if path.exists():
                    with open(path) as f:
                        for line in f:
                            entry = json.loads(line)
                            entry['id'] = uuid.UUID(entry['id'])
                            entry['created_at'] = datetime.fromisoformat(entry['created_at'])
                            self._logs.append(AuditEntry(**entry))

            async def log(self, entry):
                await super().log(entry)
                path = self._get_path("audit")
                async with aiofiles.open(path, 'a') as f:
                    await f.write(json.dumps(self._serialize(entry)) + '\n')

        return PersistentAuditLog()
    return MemoryAuditLog()


def get_org_store():
    backend = settings.STORAGE_BACKEND.lower()
    if backend == "postgresql":
        from api.storage.postgres import PostgresOrgStore
        return PostgresOrgStore()

    from api.storage.postgres import PostgresOrgStore
    return PostgresOrgStore()