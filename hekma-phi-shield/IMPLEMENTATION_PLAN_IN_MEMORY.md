# Implementation Plan: PII Anonymization Middle Layer + Reverse Tokenizer + Policy Admin Dashboard (Zero-DB In-Memory Version)

---

## 🎯 **Scope & Requirements Summary**

| Component | Requirement from Document |
|-----------|---------------------------|
| **PII Anonymization Middle Layer** | Apply per-class policies on ingest, internal transfers, external LLM exports; external-policy enforcement first for demos |
| **Reverse Tokenizer** | Persistent reversible mapping (original ↔ token) for authorized restoration (trial matching, DB storage) |
| **Policy Configuration Page** | Org-level per-class policies: **ignore**, **anonymize/normalize** (randomized/alternate), **redact** (dashes/zeros) |
| **Architecture** | Middleware approach (ASGI middleware), **In-Memory + Optional JSON Persistence** for dev/testing, separate admin dashboard |

---

## 🏗️ **High-Level Architecture (Zero-DB)**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXISTING FASTAPI APP (api/main.py)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ /predict     │  │ /validate    │  │ /mask        │  │ /batch       │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                    ┌────────────▼──────────────────────────────────────┐
                    │         ANONYMIZATION MIDDLEWARE (ASGI)            │
                    │  ┌─────────────────────────────────────────────┐  │
                    │  │  Request Interceptor → Detect PII → Apply    │  │
                    │  │  Policy → Transform → Store Mapping →        │  │
                    │  │  Forward to App / External LLM               │  │
                    │  └─────────────────────────────────────────────┘  │
                    └──────────────────────┬────────────────────────────┘
                                           │
                    ┌──────────────────────▼────────────────────────────┐
                    │         IN-MEMORY STORES (+ Optional JSON)         │
                    │  ┌─────────────────────────────────────────────┐  │
                    │  │ MemoryTokenStore                            │  │
                    │  │   - org_id -> {token -> TokenMapping}       │  │
                    │  │   - Encrypted original_value (Fernet)       │  │
                    │  │   - Context hash scoping                    │  │
                    │  │   - TTL/expiry support                      │  │
                    │  ├─────────────────────────────────────────────┤  │
                    │  │ MemoryPolicyStore                           │  │
                    │  │   - org_id -> List[PIIPolicy]               │  │
                    │  │   - Default policies (HIPAA, GDPR, etc.)    │  │
                    │  ├─────────────────────────────────────────────┤  │
                    │  │ MemoryAuditLog                              │  │
                    │  │   - Append-only list[AuditEntry]            │  │
                    │  │   - JSONL persistence for integrity         │  │
                    │  └─────────────────────────────────────────────┘  │
                    └──────────────────────┬────────────────────────────┘
                                           │
                    ┌──────────────────────▼────────────────────────────┐
                    │         POLICY ADMIN DASHBOARD (Separate App)      │
                    │  ┌──────────────┐  ┌──────────────┐               │
                    │  │ Org Settings │  │ Policy Config│               │
                    │  │              │  │ per-class:   │               │
                    │  │ - org_id     │  │ ignore       │               │
                    │  │ - name       │  │ anonymize    │               │
                    │  │ - settings   │  │ (randomized/ │               │
                    │  │ - keys       │  │  alternate)  │               │
                    │  └──────────────┘  │ redact       │               │
                    │                    └──────────────┘               │
                    │  ┌──────────────┐  ┌──────────────┐               │
                    │  │ TokenExplorer│  │  Audit Log   │               │
                    │  │ - Search     │  │ - Filter     │               │
                    │  │ - Restore    │  │ - Export     │               │
                    │  └──────────────┘  └──────────────┘               │
                    └───────────────────────────────────────────────────┘
```

---

## 📁 **New File Structure (Zero-DB)**

```
PHI-PII/
├── api/
│   ├── main.py                          # Existing - add middleware mount
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── anonymization_middleware.py  # Core ASGI middleware
│   │   ├── policy_engine.py             # Policy evaluation & application
│   │   ├── entity_detector.py           # Wrapper around existing /predict
│   │   └── exceptions.py                # Custom exceptions
│   ├── models/
│   │   ├── __init__.py
│   │   ├── policy.py                    # Pydantic models for policies
│   │   ├── token_mapping.py             # Token mapping models
│   │   └── org.py                       # Organization models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── token_store.py               # Uses storage.MemoryTokenStore
│   │   ├── policy_store.py              # Uses storage.MemoryPolicyStore
│   │   ├── anonymizer.py                # Anonymization strategies
│   │   ├── restorer.py                  # Reverse tokenization (authorized)
│   │   └── audit_log.py                 # Audit trail for restorations
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py                  # STORAGE_BACKEND=memory|json
│   └── storage/
│       ├── __init__.py                  # Factory functions
│       ├── base.py                      # Abstract interfaces (Protocols)
│       ├── memory.py                    # In-memory implementations
│       └── json_persist.py              # Optional JSON file persistence mixin
├── admin_dashboard/
│   ├── pyproject.toml                   # Separate FastAPI + React/Vue app
│   ├── backend/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── orgs.py
│   │   │   ├── policies.py
│   │   │   ├── tokens.py
│   │   │   └── audit.py
│   │   ├── models/
│   │   └── services/
│   └── frontend/
│       ├── package.json
│       ├── src/
│       │   ├── pages/
│       │   │   ├── OrgSettings.tsx
│       │   │   ├── PolicyConfig.tsx     # Main policy configuration page
│       │   │   ├── TokenExplorer.tsx    # Browse/search token mappings
│       │   │   └── AuditLog.tsx
│       │   ├── components/
│       │   │   ├── PolicyCard.tsx
│       │   │   ├── EntityTypeSelector.tsx
│       │   │   └── TokenTable.tsx
│       │   └── App.tsx
│       └── vite.config.ts
├── tests/
│   ├── test_middleware.py
│   ├── test_policy_engine.py
│   ├── test_anonymizer.py
│   ├── test_restorer.py
│   ├── test_token_store.py
│   └── test_admin_api.py
├── data/                                # Gitignored, for JSON persistence
│   ├── tokens.json
│   ├── policies.json
│   └── audit.log
├── .env.example                         # STORAGE_BACKEND=memory
└── requirements.txt                     # Add: aiofiles, cryptography, pydantic-settings
```

---

## 🔧 **Storage Strategy**

| Data | Dev Implementation | Persistence |
|------|-------------------|-------------|
| **Token Mappings** | `dict[org_id, dict[token, TokenMapping]]` | Optional JSON file (`./data/tokens.json`) |
| **Policies** | `dict[org_id, list[PIIPolicy]]` | Optional JSON file (`./data/policies.json`) |
| **Audit Logs** | `list[AuditEntry]` (append-only) | Optional JSONL file (`./data/audit.log`) |
| **Encryption** | Fernet (same) | Key in `.env` |

**No SQLAlchemy, no Alembic, no asyncpg, no aiosqlite** — pure Python.

---

## 🎯 **Core Interfaces (`api/storage/base.py`)**

```python
# api/storage/base.py
from typing import Protocol, Optional, List
from dataclasses import dataclass
from datetime import datetime
import uuid

@dataclass
class TokenMapping:
    id: uuid.UUID
    org_id: str
    original_value: str          # Encrypted at rest
    tokenized_value: str
    entity_type: str
    policy_applied: str
    context_hash: str
    confidence: float
    created_at: datetime
    expires_at: Optional[datetime] = None
    restored_at: Optional[datetime] = None
    restored_by: Optional[str] = None

@dataclass
class PIIPolicy:
    entity_type: str
    policy_type: str             # ignore, anonymize, redact
    anonymize_strategy: str = "randomized"
    custom_replacement: Optional[str] = None
    applies_to_internal: bool = True
    applies_to_external: bool = True

@dataclass
class AuditEntry:
    id: uuid.UUID
    org_id: str
    action: str                  # tokenize, restore, policy_change
    entity_type: Optional[str]
    tokenized_value: Optional[str]
    performed_by: str
    ip_address: Optional[str]
    metadata: dict
    created_at: datetime

class TokenStore(Protocol):
    async def save(self, mapping: TokenMapping) -> TokenMapping: ...
    async def get_by_token(self, org_id: str, token: str, entity_types: List[str] = None) -> Optional[TokenMapping]: ...
    async def get_all_for_org(self, org_id: str) -> List[TokenMapping]: ...
    async def update(self, mapping: TokenMapping) -> TokenMapping: ...
    def encrypt(self, value: str) -> str: ...
    def decrypt(self, value: str) -> str: ...

class PolicyStore(Protocol):
    async def get_by_org(self, org_id: str) -> List[PIIPolicy]: ...
    async def upsert_many(self, org_id: str, policies: List[PIIPolicy]) -> List[PIIPolicy]: ...
    async def get_defaults(self) -> List[PIIPolicy]: ...

class AuditLog(Protocol):
    async def log(self, entry: AuditEntry) -> None: ...
    async def get_for_org(self, org_id: str, limit: int = 100) -> List[AuditEntry]: ...
```

---

## 💾 **In-Memory Implementation (`api/storage/memory.py`)**

```python
# api/storage/memory.py
from collections import defaultdict
from api.storage.base import TokenStore, PolicyStore, AuditLog, TokenMapping, PIIPolicy, AuditEntry
from cryptography.fernet import Fernet
import uuid
from datetime import datetime
from typing import Optional, List

class MemoryTokenStore:
    def __init__(self, encryption_key: bytes):
        self._data: dict[str, dict[str, TokenMapping]] = defaultdict(dict)  # org_id -> token -> mapping
        self._by_original: dict[str, dict[str, TokenMapping]] = defaultdict(dict)  # org_id -> original_hash -> mapping
        self._cipher = Fernet(encryption_key)
    
    def encrypt(self, value: str) -> str:
        return self._cipher.encrypt(value.encode()).decode()
    
    def decrypt(self, value: str) -> str:
        return self._cipher.decrypt(value.encode()).decode()
    
    async def save(self, mapping: TokenMapping) -> TokenMapping:
        mapping.id = mapping.id or uuid.uuid4()
        mapping.created_at = mapping.created_at or datetime.utcnow()
        self._data[mapping.org_id][mapping.tokenized_value] = mapping
        # Index by original for reverse lookup
        orig_hash = self._hash(mapping.original_value)
        self._by_original[mapping.org_id][orig_hash] = mapping
        return mapping
    
    async def get_by_token(self, org_id: str, token: str, entity_types: List[str] = None) -> Optional[TokenMapping]:
        mapping = self._data.get(org_id, {}).get(token)
        if mapping and (not entity_types or mapping.entity_type in entity_types):
            return mapping
        return None
    
    async def get_all_for_org(self, org_id: str) -> List[TokenMapping]:
        return list(self._data.get(org_id, {}).values())
    
    async def update(self, mapping: TokenMapping) -> TokenMapping:
        self._data[mapping.org_id][mapping.tokenized_value] = mapping
        return mapping
    
    def _hash(self, value: str) -> str:
        import hashlib
        return hashlib.sha256(value.encode()).hexdigest()

class MemoryPolicyStore:
    def __init__(self):
        self._policies: dict[str, List[PIIPolicy]] = defaultdict(list)
        self._defaults: List[PIIPolicy] = []  # Built-in defaults
    
    async def get_by_org(self, org_id: str) -> List[PIIPolicy]:
        return self._policies.get(org_id, self._defaults.copy())
    
    async def upsert_many(self, org_id: str, policies: List[PIIPolicy]) -> List[PIIPolicy]:
        self._policies[org_id] = policies
        return policies
    
    async def get_defaults(self) -> List[PIIPolicy]:
        return self._defaults.copy()

class MemoryAuditLog:
    def __init__(self):
        self._logs: List[AuditEntry] = []
    
    async def log(self, entry: AuditEntry) -> None:
        entry.id = entry.id or uuid.uuid4()
        entry.created_at = entry.created_at or datetime.utcnow()
        self._logs.append(entry)
    
    async def get_for_org(self, org_id: str, limit: int = 100) -> List[AuditEntry]:
        return [e for e in reversed(self._logs) if e.org_id == org_id][:limit]
```

---

## 📄 **Optional JSON Persistence (`api/storage/json_persist.py`)**

```python
# api/storage/json_persist.py
import json
import aiofiles
from pathlib import Path
from datetime import datetime
from typing import Any, Callable, TypeVar
from api.storage.base import TokenMapping, PIIPolicy, AuditEntry
import uuid

T = TypeVar('T')

class JsonPersistenceMixin:
    """Mixin to add JSON file persistence to any memory store"""
    
    def __init__(self, data_dir: Path = Path("./data"), *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._load()
    
    def _get_path(self, name: str) -> Path:
        return self.data_dir / f"{name}.json"
    
    def _serialize(self, obj: Any) -> Any:
        """Convert dataclass to JSON-serializable dict"""
        if hasattr(obj, '__dataclass_fields__'):
            return {k: self._serialize(v) for k, v in obj.__dict__.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._serialize(v) for v in obj]
        elif isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, uuid.UUID):
            return str(obj)
        return obj
    
    def _deserialize_token(self, data: dict) -> TokenMapping:
        data['id'] = uuid.UUID(data['id'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        if data.get('expires_at'): data['expires_at'] = datetime.fromisoformat(data['expires_at'])
        if data.get('restored_at'): data['restored_at'] = datetime.fromisoformat(data['restored_at'])
        return TokenMapping(**data)
    
    def _load(self):
        """Override in subclass"""
        pass
    
    async def _persist(self, name: str, data: Any):
        if not getattr(self, '_persist_enabled', True):
            return
        path = self._get_path(name)
        async with aiofiles.open(path, 'w') as f:
            await f.write(json.dumps(self._serialize(data), indent=2))
```

**Usage:** `class PersistentTokenStore(JsonPersistenceMixin, MemoryTokenStore): ...`

---

## ⚙️ **Settings (`api/config/settings.py`)**

```python
# api/config/settings.py
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    STORAGE_BACKEND: str = "memory"           # memory | json
    DATA_DIR: Path = Path("./data")
    ENCRYPTION_KEY: str = "dev-key-change-in-production-32-bytes!!"
    POLICY_CACHE_TTL: int = 60
    ANONYMIZATION_ENABLED: bool = True
    EXCLUDED_PATHS: set[str] = {"/health", "/info", "/docs", "/openapi.json", "/entities", "/predict", "/validate", "/mask", "/predict/batch"}
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 🔌 **Factory (`api/storage/__init__.py`)**

```python
# api/storage/__init__.py
from api.config.settings import settings
from api.storage.memory import MemoryTokenStore, MemoryPolicyStore, MemoryAuditLog
from api.storage.json_persist import JsonPersistenceMixin
from api.storage.base import TokenStore, PolicyStore, AuditLog
import json
import aiofiles
import uuid
from datetime import datetime
from pathlib import Path

def get_token_store() -> TokenStore:
    if settings.STORAGE_BACKEND == "json":
        class PersistentTokenStore(JsonPersistenceMixin, MemoryTokenStore):
            def __init__(self, *args, **kwargs):
                super().__init__(settings.DATA_DIR, *args, **kwargs)
            def _load(self):
                path = self._get_path("tokens")
                if path.exists():
                    with open(path) as f:
                        for item in json.load(f):
                            self._data[item['org_id']][item['tokenized_value']] = self._deserialize_token(item)
            async def save(self, mapping):
                result = await super().save(mapping)
                await self._persist("tokens", list(self._data.values()))
                return result
            async def update(self, mapping):
                result = await super().update(mapping)
                await self._persist("tokens", list(self._data.values()))
                return result
        return PersistentTokenStore(settings.ENCRYPTION_KEY.encode())
    return MemoryTokenStore(settings.ENCRYPTION_KEY.encode())

def get_policy_store() -> PolicyStore:
    if settings.STORAGE_BACKEND == "json":
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
        return PersistentPolicyStore()
    return MemoryPolicyStore()

def get_audit_log() -> AuditLog:
    if settings.STORAGE_BACKEND == "json":
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
                # Append to JSONL for audit integrity
                path = self._get_path("audit")
                async with aiofiles.open(path, 'a') as f:
                    await f.write(json.dumps(self._serialize(entry)) + '\n')
        return PersistentAuditLog()
    return MemoryAuditLog()
```

---

## ✅ **What This Gives You**

| Feature | Implementation |
|---------|----------------|
| **Zero external deps** | Only `cryptography` (already in requirements) + `aiofiles` (new, lightweight) |
| **Fast dev iteration** | In-memory dict = microsecond operations |
| **Survives restarts** | `STORAGE_BACKEND=json` writes to `./data/*.json` |
| **Audit integrity** | JSONL append-only for audit log |
| **Swap to SQL later** | Same `TokenStore`/`PolicyStore`/`AuditLog` protocols |
| **Test isolation** | New instance per test = clean state |

---

## 📦 **One New Dependency**

```txt
# requirements.txt (add)
aiofiles>=23.0.0    # Async file I/O for JSON persistence
```

---

## 🧪 **Testing Helper**

```python
# tests/conftest.py
import pytest
from api.storage.memory import MemoryTokenStore, MemoryPolicyStore, MemoryAuditLog
from api.services.token_store import TokenStore
from api.services.policy_store import PolicyStore

@pytest.fixture
def token_store():
    return MemoryTokenStore(b"test-key-32-bytes-long-for-fernet!!")

@pytest.fixture
def policy_store():
    return MemoryPolicyStore()

@pytest.fixture
def audit_log():
    return MemoryAuditLog()
```

---

## 🎯 **Phase 1 Deliverables (Zero-DB)**

1. **Storage Protocols** → `api/storage/base.py`
2. **In-Memory Impl** → `api/storage/memory.py`
3. **JSON Persistence Mixin** → `api/storage/json_persist.py`
4. **Factory** → `api/storage/__init__.py`
5. **Settings** → `api/config/settings.py` (add `STORAGE_BACKEND`)
6. **Wire into Services** → `token_store.py`, `policy_store.py`, `audit_log.py` use factory

**No database, no migrations, no containers — pure Python.**

---

## ❓ **Admin Dashboard Integration**

**Option A (Recommended)**: Dashboard calls FastAPI endpoints (e.g., `GET /admin/policies`, `POST /admin/policies`) — same stores, consistent
**Option B**: Dashboard reads `./data/policies.json` directly — simpler, but separate process

**Recommendation**: Option A (API-driven) — keeps single source of truth, works with both memory and JSON backends.

---

## 🔄 **Migration Path to PostgreSQL**

When ready for production, only these files change:
1. `api/storage/memory.py` → `api/storage/postgres.py` (implements same Protocols)
2. `api/storage/__init__.py` factory → returns Postgres implementations
3. `api/config/settings.py` → `DATABASE_URL` instead of `STORAGE_BACKEND`
4. Add `asyncpg`, `sqlalchemy`, `alembic` to requirements
5. Run `alembic upgrade head`

**Zero changes** to middleware, policy engine, anonymizer, restorer, or admin dashboard.