# Implementation Plan: PII Anonymization Middle Layer + Reverse Tokenizer + Policy Admin Dashboard (PostgreSQL Version)

---

## 🎯 **Scope & Requirements Summary**

| Component | Requirement from Document |
|-----------|---------------------------|
| **PII Anonymization Middle Layer** | Apply per-class policies on ingest, internal transfers, external LLM exports; external-policy enforcement first for demos |
| **Reverse Tokenizer** | Persistent reversible mapping (original ↔ token) for authorized restoration (trial matching, DB storage) |
| **Policy Configuration Page** | Org-level per-class policies: **ignore**, **anonymize/normalize** (randomized/alternate), **redact** (dashes/zeros) |
| **Architecture** | Middleware approach (ASGI middleware), PostgreSQL for token mappings, separate admin dashboard |

---

## 🏗️ **High-Level Architecture**

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
                    │            POSTGRESQL (Reverse Tokenizer)          │
                    │  ┌─────────────────────────────────────────────┐  │
                    │  │ token_mappings table                        │  │
                    │  │  - id (PK)                                  │  │
                    │  │  - org_id (FK)                              │  │
                    │  │  - original_value (encrypted)               │  │
                    │  │  - tokenized_value                          │  │
                    │  │  - entity_type                              │  │
                    │  │  - policy_applied (ignore/anonymize/redact) │  │
                    │  │  - context_hash (request context hash)      │  │
                    │  │  - created_at, expires_at                   │  │
                    │  │  - restored_at, restored_by (audit)         │  │
                    │  └─────────────────────────────────────────────┘  │
                    └───────────────────────────────────────────────────┘
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
                    └───────────────────────────────────────────────────┘
```

---

## 📁 **New File Structure**

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
│   │   ├── token_store.py               # PostgreSQL token mapping CRUD
│   │   ├── policy_store.py              # Policy CRUD from DB
│   │   ├── anonymizer.py                # Anonymization strategies
│   │   ├── restorer.py                  # Reverse tokenization (authorized)
│   │   └── audit_log.py                 # Audit trail for restorations
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py                  # PostgreSQL, encryption keys
│   └── database/
│       ├── __init__.py
│       ├── connection.py                # AsyncPG/SQLAlchemy async pool
│       ├── migrations/
│       │   ├── 001_create_orgs.sql
│       │   ├── 002_create_policies.sql
│       │   ├── 003_create_token_mappings.sql
│       │   └── 004_create_audit_logs.sql
│       └── models.py                    # SQLAlchemy models
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
├── alembic.ini                          # DB migrations
├── docker-compose.yml                   # PostgreSQL + services
└── requirements.txt                     # Add: asyncpg, sqlalchemy, alembic, cryptography, pydantic-settings
```

---

## 🔧 **Component-by-Component Implementation Plan**

---

### **1. DATABASE LAYER (PostgreSQL + SQLAlchemy Async)**

**Files to create:**
- `api/database/connection.py` - Async engine, session factory
- `api/database/models.py` - SQLAlchemy models
- `api/database/migrations/*.sql` - 4 migration files
- `alembic.ini` - Migration config

**Tables:**

```sql
-- organizations
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    api_key_hash VARCHAR(255) UNIQUE NOT NULL,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- pii_policies (per-org, per-entity-type)
CREATE TABLE pii_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    entity_type VARCHAR(100) NOT NULL,
    policy_type VARCHAR(20) NOT NULL CHECK (policy_type IN ('ignore', 'anonymize', 'redact')),
    anonymize_strategy VARCHAR(20) CHECK (anonymize_strategy IN ('randomized', 'alternate')),
    custom_replacement TEXT,
    applies_to_internal BOOLEAN DEFAULT TRUE,
    applies_to_external BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, entity_type)
);

-- token_mappings (reverse tokenizer storage)
CREATE TABLE token_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    original_value TEXT NOT NULL,  -- Encrypted at rest
    tokenized_value VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    policy_applied VARCHAR(20) NOT NULL,
    context_hash VARCHAR(64),  -- SHA256 of request context for scoping
    confidence DECIMAL(4,3),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    restored_at TIMESTAMPTZ,
    restored_by UUID,
    UNIQUE(org_id, tokenized_value, entity_type, context_hash)
);

-- audit_logs (for restoration authorization trail)
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,  -- 'tokenize', 'restore', 'policy_change'
    entity_type VARCHAR(100),
    tokenized_value VARCHAR(100),
    performed_by VARCHAR(255),
    ip_address INET,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_token_mappings_org_token ON token_mappings(org_id, tokenized_value);
CREATE INDEX idx_token_mappings_original ON token_mappings(org_id, original_value);
CREATE INDEX idx_policies_org ON pii_policies(org_id);
CREATE INDEX idx_audit_logs_org_time ON audit_logs(org_id, created_at);
```

**Edge Cases Handled:**
- **Encryption at rest**: `original_value` encrypted with org-specific key (Fernet/AES-GCM)
- **TTL/expiration**: `expires_at` for auto-cleanup of temporary mappings
- **Context scoping**: `context_hash` allows same value → different tokens per request context
- **Audit trail**: Every tokenization/restoration logged with actor, IP, metadata JSON for extensibility

---

### **2. POLICY ENGINE (`api/middleware/policy_engine.py`)**

**Core Classes:**

```python
# api/middleware/policy_engine.py
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Literal
import hashlib
import json

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

class PolicyEngine:
    def __init__(self, policy_store: "PolicyStore"):
        self.policy_store = policy_store
        self._cache: dict[str, list[PIIPolicy]] = {}
    
    async def get_policies_for_org(self, org_id: str, context: PolicyContext) -> list[PIIPolicy]:
        # Cache with TTL, invalidate on policy change
        cache_key = f"{org_id}:{context.direction}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        policies = await self.policy_store.get_by_org(org_id)
        filtered = [
            p for p in policies 
            if (context.direction == "external" and p.applies_to_external) or
               (context.direction == "internal" and p.applies_to_internal)
        ]
        self._cache[cache_key] = filtered
        return filtered
    
    def should_process(self, entity_type: str, policies: list[PIIPolicy]) -> Optional[PIIPolicy]:
        for policy in policies:
            if policy.entity_type.upper() == entity_type.upper():
                return policy if policy.policy_type != PolicyType.IGNORE else None
        return None  # Default: no policy = ignore
    
    def build_context_hash(self, context: "PolicyContext") -> str:
        # Hash org_id + direction + request_path + user_id for context-scoped tokens
        data = f"{context.org_id}:{context.direction}:{context.path}:{context.user_id}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]
```

**PolicyContext** - Carries request metadata through middleware:
```python
class PolicyContext(BaseModel):
    org_id: str
    direction: Literal["internal", "external"]  # internal=inter-service, external=LLM export
    path: str
    user_id: Optional[str] = None
    request_id: str
```

**Edge Cases:**
- **Policy not found for entity type** → Default to `IGNORE` (fail-open for demo, configurable)
- **Conflicting policies** → Most restrictive wins (REDACT > ANONYMIZE > IGNORE)
- **Cache invalidation** → Pub/Sub or poll on policy update; TTL 60s default

---

### **3. ANONYMIZATION STRATEGIES (`api/services/anonymizer.py`)**

```python
# api/services/anonymizer.py
from abc import ABC, abstractmethod
from typing import Protocol
import random
import string
from faker import Faker

fake = Faker()

class AnonymizerStrategy(Protocol):
    def anonymize(self, original: str, entity_type: str, policy: PIIPolicy) -> str: ...

class RedactStrategy:
    """Replace with dashes/zeros preserving length/format"""
    def anonymize(self, original: str, entity_type: str, policy: PIIPolicy) -> str:
        if entity_type in ("SSN", "PHONE", "CREDIT_CARD"):
            return re.sub(r'\d', 'X', original)
        if entity_type in ("EMAIL",):
            return "XXX@XXX.XXX"
        return "X" * len(original)

class RandomizedStrategy:
    """Replace with random but format-preserving values"""
    GENERATORS = {
        "PERSON": lambda: fake.name(),
        "EMAIL": lambda: fake.email(),
        "PHONE": lambda: fake.phone_number(),
        "SSN": lambda: f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}",
        "DATE": lambda: fake.date(),
        "ADDRESS": lambda: fake.street_address(),
        "CREDIT_CARD": lambda: fake.credit_card_number(),
        "DRIVER_LICENSE": lambda: fake.bothify(text='??#######'),
        "PASSPORT": lambda: fake.bothify(text='??#######'),
    }
    
    def anonymize(self, original: str, entity_type: str, policy: PIIPolicy) -> str:
        gen = self.GENERATORS.get(entity_type.upper())
        if gen:
            return gen()
        # Fallback: random alphanumeric same length
        return ''.join(random.choices(string.ascii_letters + string.digits, k=len(original)))

class AlternateStrategy:
    """Replace with consistent alternate (deterministic per original)"""
    def __init__(self):
        self._cache: dict[str, str] = {}
    
    def anonymize(self, original: str, entity_type: str, policy: PIIPolicy) -> str:
        if original in self._cache:
            return self._cache[original]
        # Use seeded random for deterministic but different value
        seed = hash(original) % (2**32)
        rng = random.Random(seed)
        gen = RandomizedStrategy.GENERATORS.get(entity_type.upper())
        result = gen() if gen else ''.join(rng.choices(string.ascii_letters + string.digits, k=len(original)))
        self._cache[original] = result
        return result

class Anonymizer:
    STRATEGIES = {
        PolicyType.REDACT: RedactStrategy(),
        (PolicyType.ANONYMIZE, AnonymizeStrategy.RANDOMIZED): RandomizedStrategy(),
        (PolicyType.ANONYMIZE, AnonymizeStrategy.ALTERNATE): AlternateStrategy(),
    }
    
    def apply(self, text: str, entities: list[Entity], policies: list[PIIPolicy], 
              context_hash: str, token_store: "TokenStore", org_id: str) -> tuple[str, list[TokenMapping]]:
        # Sort entities by start position descending for safe replacement
        sorted_entities = sorted(entities, key=lambda e: e.start, reverse=True)
        mappings = []
        result = text
        
        for entity in sorted_entities:
            policy = self._find_policy(entity.entity, policies)
            if not policy or policy.policy_type == PolicyType.IGNORE:
                continue
            
            original = text[entity.start:entity.end]
            strategy = self.STRATEGIES.get(
                (policy.policy_type, policy.anonymize_strategy) if policy.policy_type == PolicyType.ANONYMIZE
                else policy.policy_type
            )
            
            tokenized = strategy.anonymize(original, entity.entity, policy)
            
            # Store mapping for reverse tokenization
            mapping = TokenMapping(
                org_id=org_id,
                original_value=original,
                tokenized_value=tokenized,
                entity_type=entity.entity,
                policy_applied=policy.policy_type.value,
                context_hash=context_hash,
                confidence=entity.confidence,
            )
            await token_store.save(mapping)
            mappings.append(mapping)
            
            # Replace in text
            result = result[:entity.start] + tokenized + result[entity.end:]
        
        return result, mappings
```

**Edge Cases:**
- **Overlapping entities** → Sort by start desc, longer entities first
- **Format preservation** → Regex-based redaction for SSN, phone, credit cards
- **Deterministic alternates** → Same original → same token within context
- **Faker locale** → Configurable per org for locale-appropriate names

---

### **4. REVERSE TOKENIZER / RESTORER (`api/services/restorer.py`)**

```python
# api/services/restorer.py
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class RestoreRequest:
    tokenized_values: list[str]
    entity_types: Optional[list[str]] = None
    org_id: str
    requester_id: str
    ip_address: str
    purpose: str  # "trial_matching", "db_storage", "audit", etc.

@dataclass
class RestoreResult:
    original_value: str
    tokenized_value: str
    entity_type: str
    restored: bool

class Restorer:
    def __init__(self, token_store: "TokenStore", audit_log: "AuditLog"):
        self.token_store = token_store
        self.audit_log = audit_log
    
    async def restore(self, request: RestoreRequest) -> list[RestoreResult]:
        results = []
        
        for token in request.tokenized_values:
            mapping = await self.token_store.get_by_token(
                org_id=request.org_id,
                tokenized_value=token,
                entity_types=request.entity_types
            )
            
            if not mapping:
                results.append(RestoreResult(
                    original_value="", tokenized_value=token, 
                    entity_type="", restored=False
                ))
                continue
            
            # Authorization check (implement your policy)
            if not await self._authorize_restore(request, mapping):
                await self.audit_log.log_denied(request, mapping)
                results.append(RestoreResult(
                    original_value="", tokenized_value=token,
                    entity_type=mapping.entity_type, restored=False
                ))
                continue
            
            # Decrypt original value
            original = self.token_store.decrypt(mapping.original_value)
            
            # Update mapping with restoration info
            mapping.restored_at = datetime.utcnow()
            mapping.restored_by = request.requester_id
            await self.token_store.update(mapping)
            
            # Audit log
            await self.audit_log.log_restore(request, mapping)
            
            results.append(RestoreResult(
                original_value=original,
                tokenized_value=token,
                entity_type=mapping.entity_type,
                restored=True
            ))
        
        return results
    
    async def _authorize_restore(self, request: RestoreRequest, mapping: TokenMapping) -> bool:
        # Implement your auth logic: RBAC, purpose allowlist, expiry check
        ALLOWED_PURPOSES = {"trial_matching", "db_storage", "audit", "patient_care"}
        if request.purpose not in ALLOWED_PURPOSES:
            return False
        if mapping.expires_at and mapping.expires_at < datetime.utcnow():
            return False
        # Check requester has org access, appropriate role, etc.
        return True
    
    async def restore_in_text(self, text: str, org_id: str, requester_id: str, 
                               purpose: str, ip: str) -> str:
        """Find all tokens in text and restore them"""
        # Pattern: tokens are typically [TYPE] or <REDACTED> or XXXX
        # Better: store token→original mapping and do direct replacement
        mappings = await self.token_store.get_all_for_org(org_id)
        token_to_original = {m.tokenized_value: m for m in mappings}
        
        result = text
        for token, mapping in token_to_original.items():
            if token in result:
                auth_result = await self.restore(RestoreRequest(
                    tokenized_values=[token],
                    org_id=org_id,
                    requester_id=requester_id,
                    ip_address=ip,
                    purpose=purpose
                ))
                if auth_result[0].restored:
                    result = result.replace(token, auth_result[0].original_value)
        
        return result
```

**Edge Cases:**
- **Partial token matches** → Use word boundaries or exact match
- **Expired tokens** → Deny restoration, log attempt
- **Batch restoration** → Single audit entry with multiple tokens
- **Cascade restoration** → Restore in dependent systems via webhook

---

### **5. TOKEN STORE (`api/services/token_store.py`)**

```python
# api/services/token_store.py
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
import json

class TokenStore:
    def __init__(self, session_factory, encryption_key: bytes):
        self.session_factory = session_factory
        self.cipher = Fernet(encryption_key)
    
    def encrypt(self, value: str) -> str:
        return self.cipher.encrypt(value.encode()).decode()
    
    def decrypt(self, encrypted: str) -> str:
        return self.cipher.decrypt(encrypted.encode()).decode()
    
    async def save(self, mapping: TokenMapping) -> TokenMapping:
        async with self.session_factory() as session:
            db_mapping = TokenMappingModel(
                org_id=mapping.org_id,
                original_value=self.encrypt(mapping.original_value),
                tokenized_value=mapping.tokenized_value,
                entity_type=mapping.entity_type,
                policy_applied=mapping.policy_applied,
                context_hash=mapping.context_hash,
                confidence=mapping.confidence,
                expires_at=mapping.expires_at,
            )
            session.add(db_mapping)
            await session.commit()
            await session.refresh(db_mapping)
            return self._to_domain(db_mapping)
    
    async def get_by_token(self, org_id: str, tokenized_value: str, 
                           entity_types: list[str] = None) -> Optional[TokenMapping]:
        async with self.session_factory() as session:
            stmt = select(TokenMappingModel).where(
                TokenMappingModel.org_id == org_id,
                TokenMappingModel.tokenized_value == tokenized_value
            )
            if entity_types:
                stmt = stmt.where(TokenMappingModel.entity_type.in_(entity_types))
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            return self._to_domain(model) if model else None
    
    async def get_all_for_org(self, org_id: str) -> list[TokenMapping]:
        async with self.session_factory() as session:
            stmt = select(TokenMappingModel).where(TokenMappingModel.org_id == org_id)
            result = await session.execute(stmt)
            return [self._to_domain(m) for m in result.scalars().all()]
    
    def _to_domain(self, model: TokenMappingModel) -> TokenMapping:
        return TokenMapping(
            id=model.id,
            org_id=model.org_id,
            original_value=self.decrypt(model.original_value),
            tokenized_value=model.tokenized_value,
            entity_type=model.entity_type,
            policy_applied=model.policy_applied,
            context_hash=model.context_hash,
            confidence=model.confidence,
            created_at=model.created_at,
            expires_at=model.expires_at,
            restored_at=model.restored_at,
            restored_by=model.restored_by,
        )
```

**Edge Cases:**
- **Key rotation** → Store key version, re-encrypt on rotation
- **Large volume** → Partition by org_id, context_hash; consider Redis cache layer
- **Collision handling** → UUID-based tokens guarantee uniqueness

---

### **6. ANONYMIZATION MIDDLEWARE (`api/middleware/anonymization_middleware.py`)**

```python
# api/middleware/anonymization_middleware.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
import json
import uuid

class AnonymizationMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        policy_engine: PolicyEngine,
        entity_detector: EntityDetector,
        token_store: TokenStore,
        anonymizer: Anonymizer,
        excluded_paths: set[str] = None,
    ):
        super().__init__(app)
        self.policy_engine = policy_engine
        self.entity_detector = entity_detector
        self.token_store = token_store
        self.anonymizer = anonymizer
        self.excluded_paths = excluded_paths or {"/health", "/info", "/docs", "/openapi.json"}
    
    async def dispatch(self, request: Request, call_next):
        # Skip excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)
        
        # Skip non-mutating GET requests (configurable)
        if request.method == "GET" and not self._should_process_get(request):
            return await call_next(request)
        
        # Extract org context (from API key, header, JWT, etc.)
        org_id = await self._extract_org_id(request)
        if not org_id:
            return await call_next(request)  # No org = pass through
        
        # Determine direction: external (LLM export) vs internal
        direction = self._determine_direction(request)
        
        # Read and parse request body
        body = await request.body()
        if not body:
            return await call_next(request)
        
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return await call_next(request)  # Non-JSON = pass through
        
        # Process text fields in request
        processed_data, mappings = await self._process_request_data(
            data, org_id, direction, request
        )
        
        # Store request ID for audit trail
        request.state.anonymization_mappings = mappings
        request.state.org_id = org_id
        
        # Replace request body
        request._body = json.dumps(processed_data).encode()
        
        # Process response if it contains text to anonymize (e.g., LLM responses)
        response = await call_next(request)
        
        # Optionally process response body for external LLM calls
        if direction == "external" and self._should_process_response(response):
            response = await self._process_response(response, org_id, direction, request)
        
        return response
    
    async def _process_request_data(self, data: dict, org_id: str, direction: str, 
                                     request: Request) -> tuple[dict, list]:
        # Recursively find and process string fields
        # Configurable: which fields to process (e.g., "text", "content", "prompt", "messages")
        text_fields = {"text", "content", "prompt", "query", "input", "message"}
        mappings = []
        
        async def process_value(obj, path=""):
            if isinstance(obj, str):
                if len(obj) > 10000:  # Skip huge texts
                    return obj
                entities = await self.entity_detector.detect(obj)
                context = PolicyContext(
                    org_id=org_id,
                    direction=direction,
                    path=request.url.path,
                    user_id=request.headers.get("x-user-id"),
                    request_id=str(uuid.uuid4())
                )
                context_hash = self.policy_engine.build_context_hash(context)
                policies = await self.policy_engine.get_policies_for_org(org_id, context)
                
                processed, entity_mappings = self.anonymizer.apply(
                    obj, entities, policies, context_hash, self.token_store, org_id
                )
                mappings.extend(entity_mappings)
                return processed
            elif isinstance(obj, dict):
                return {k: await process_value(v, f"{path}.{k}") for k, v in obj.items()}
            elif isinstance(obj, list):
                return [await process_value(v, f"{path}[{i}]") for i, v in enumerate(obj)]
            return obj
        
        processed = await process_value(data)
        return processed, mappings
```

**Edge Cases:**
- **Streaming responses** → Buffer and process, or skip for performance
- **Large payloads** → Chunked processing, size limits
- **Non-JSON content** → Pass through (multipart, binary)
- **Request/Response correlation** → Request ID propagated for audit
- **Middleware order** → Mount AFTER auth, BEFORE routing

---

### **7. ENTITY DETECTOR WRAPPER (`api/middleware/entity_detector.py`)**

```python
# api/middleware/entity_detector.py
from api.main import detect_entities, Entity
from typing import List

class EntityDetector:
    def __init__(self, min_confidence: float = 0.5):
        self.min_confidence = min_confidence
    
    async def detect(self, text: str) -> List[Entity]:
        """Wrapper around existing detect_entities"""
        entities = await detect_entities(text, self.min_confidence)
        return [
            Entity(
                entity=e["entity"],
                text=e["text"],
                start=e["start"],
                end=e["end"],
                confidence=e["confidence"]
            )
            for e in entities
        ]
```

**Integration:** Reuses existing `/predict` logic via `detect_entities()` function.

---

### **8. ADMIN DASHBOARD - POLICY CONFIGURATION PAGE**

**Backend API (`admin_dashboard/backend/api/policies.py`):**

```python
# admin_dashboard/backend/api/policies.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter(prefix="/api/v1/orgs/{org_id}/policies", tags=["policies"])

class PolicyCreate(BaseModel):
    entity_type: str
    policy_type: str  # ignore, anonymize, redact
    anonymize_strategy: Optional[str] = "randomized"
    custom_replacement: Optional[str] = None
    applies_to_internal: bool = True
    applies_to_external: bool = True

class PolicyResponse(PolicyCreate):
    id: uuid.UUID
    org_id: uuid.UUID
    created_at: str
    updated_at: str

class PolicyBulkUpdate(BaseModel):
    policies: list[PolicyCreate]

@router.get("", response_model=list[PolicyResponse])
async def list_policies(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    # Return all policies for org, including defaults for entity types not configured
    pass

@router.put("/bulk", response_model=list[PolicyResponse])
async def bulk_update_policies(
    org_id: uuid.UUID, 
    payload: PolicyBulkUpdate, 
    db: AsyncSession = Depends(get_db)
):
    # Upsert all policies in transaction
    pass

@router.get("/entity-types", response_model=list[str])
async def get_entity_types():
    # Return supported entity types from PII model
    pass

@router.get("/presets", response_model=dict)
async def get_presets():
    # Return policy presets: HIPAA, GDPR, PCI, Custom
    return {
        "HIPAA": {"PERSON": "anonymize", "DATE": "redact", "SSN": "redact", ...},
        "GDPR": {"PERSON": "anonymize", "EMAIL": "anonymize", "PHONE": "redact", ...},
        "PCI": {"CREDIT_CARD": "redact", "CVV": "redact", ...},
        "MINIMAL": {"SSN": "redact", "CREDIT_CARD": "redact", "PASSPORT": "redact"},
    }
```

**Frontend - PolicyConfig Page (`admin_dashboard/frontend/src/pages/PolicyConfig.tsx`):**

```tsx
// admin_dashboard/frontend/src/pages/PolicyConfig.tsx
import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { PolicyCard } from '../components/PolicyCard';
import { EntityTypeSelector } from '../components/EntityTypeSelector';
import { api } from '../lib/api';

const POLICY_TYPES = [
  { value: 'ignore', label: 'Ignore', description: 'No action taken, pass through as-is' },
  { value: 'anonymize', label: 'Anonymize/Normalize', description: 'Replace with realistic but fake values' },
  { value: 'redact', label: 'Redact', description: 'Replace with placeholder characters (XXX, ---)' },
];

const ANONYMIZE_STRATEGIES = [
  { value: 'randomized', label: 'Randomized', description: 'Different fake value each time' },
  { value: 'alternate', label: 'Consistent Alternate', description: 'Same original → same token (deterministic)' },
];

export const PolicyConfig: React.FC = () => {
  const { orgId } = useParams<{ orgId: string }>();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [entityTypes, setEntityTypes] = useState<string[]>([]);
  const [presets, setPresets] = useState<Record<string, PolicyPreset>>({});
  const [selectedPreset, setSelectedPreset] = useState<string>('');
  const [saving, setSaving] = useState(false);
  const [direction, setDirection] = useState<'internal' | 'external'>('external');

  useEffect(() => {
    loadData();
  }, [orgId]);

  const loadData = async () => {
    const [policiesRes, typesRes, presetsRes] = await Promise.all([
      api.get(`/orgs/${orgId}/policies`),
      api.get(`/orgs/${orgId}/policies/entity-types`),
      api.get(`/orgs/${orgId}/policies/presets`),
    ]);
    setPolicies(policiesRes.data);
    setEntityTypes(typesRes.data);
    setPresets(presetsRes.data);
  };

  const handlePresetApply = async (presetName: string) => {
    const preset = presets[presetName];
    const newPolicies = entityTypes.map(et => ({
      entity_type: et,
      ...preset[et],
      applies_to_internal: direction === 'internal',
      applies_to_external: direction === 'external',
    }));
    setPolicies(newPolicies);
    setSelectedPreset(presetName);
  };

  const handleSave = async () => {
    setSaving(true);
    await api.put(`/orgs/${orgId}/policies/bulk`, { policies });
    setSaving(false);
    // Show toast success
  };

  return (
    <div className="policy-config-page">
      <header className="page-header">
        <h1>PII Policy Configuration</h1>
        <p className="subtitle">Configure per-entity-type policies for {direction} data flows</p>
      </header>

      <div className="controls-bar">
        <div className="direction-toggle">
          <label>Policy Scope:</label>
          <select value={direction} onChange={e => setDirection(e.target.value as any)}>
            <option value="external">External (LLM Exports)</option>
            <option value="internal">Internal (Inter-service)</option>
            <option value="both">Both</option>
          </select>
        </div>
        
        <div className="preset-selector">
          <label>Apply Preset:</label>
          <select value={selectedPreset} onChange={e => handlePresetApply(e.target.value)}>
            <option value="">-- Select Preset --</option>
            {Object.keys(presets).map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>

        <button className="btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save Policies'}
        </button>
      </div>

      <div className="policy-grid">
        {entityTypes.map(entityType => {
          const policy = policies.find(p => p.entity_type === entityType) || {
            entity_type: entityType,
            policy_type: 'ignore',
            anonymize_strategy: 'randomized',
            applies_to_internal: true,
            applies_to_external: true,
          };
          return (
            <PolicyCard
              key={entityType}
              policy={policy}
              entityType={entityType}
              policyTypes={POLICY_TYPES}
              anonymizeStrategies={ANONYMIZE_STRATEGIES}
              onChange={updated => setPolicies(p => 
                p.map(pol => pol.entity_type === entityType ? updated : pol)
              )}
            />
          )
        })}
      </div>

      {entityTypes.length === 0 && (
        <div className="empty-state">
          <p>No entity types found. Ensure PII detection model is loaded.</p>
        </div>
      )}
    </div>
  );
};
```

**PolicyCard Component (`admin_dashboard/frontend/src/components/PolicyCard.tsx`):**

```tsx
// admin_dashboard/frontend/src/components/PolicyCard.tsx
import React from 'react';

interface PolicyCardProps {
  policy: Policy;
  entityType: string;
  policyTypes: PolicyType[];
  anonymizeStrategies: AnonymizeStrategy[];
  onChange: (policy: Policy) => void;
}

export const PolicyCard: React.FC<PolicyCardProps> = ({ 
  policy, entityType, policyTypes, anonymizeStrategies, onChange 
}) => {
  const updatePolicy = (field: string, value: any) => {
    onChange({ ...policy, [field]: value });
  };

  return (
    <div className={`policy-card ${policy.policy_type}`}>
      <div className="policy-header">
        <span className="entity-type-badge">{entityType}</span>
        <span className="policy-badge">{policy.policy_type}</span>
      </div>

      <div className="policy-options">
        {policyTypes.map(pt => (
          <label key={pt.value} className="radio-option">
            <input
              type="radio"
              name={`policy-${entityType}`}
              value={pt.value}
              checked={policy.policy_type === pt.value}
              onChange={e => updatePolicy('policy_type', e.target.value)}
            />
            <span className="option-label">{pt.label}</span>
            <span className="option-desc">{pt.description}</span>
          </label>
        ))}
      </div>

      {policy.policy_type === 'anonymize' && (
        <div className="anonymize-options">
          <label>Strategy:</label>
          <select 
            value={policy.anonymize_strategy} 
            onChange={e => updatePolicy('anonymize_strategy', e.target.value)}
          >
            {anonymizeStrategies.map(s => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
          <span className="help-text">
            {policy.anonymize_strategy === 'alternate' 
              ? 'Same original value always maps to same token within context'
              : 'New random value generated each time'}
          </span>
        </div>
      )}

      <div className="scope-options">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={policy.applies_to_internal}
            onChange={e => updatePolicy('applies_to_internal', e.target.checked)}
          />
          Apply to internal data flows
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={policy.applies_to_external}
            onChange={e => updatePolicy('applies_to_external', e.target.checked)}
          />
          Apply to external LLM exports
        </label>
      </div>

      {policy.policy_type === 'redact' && (
        <div className="redact-preview">
          Preview: {getRedactPreview(entityType)}
        </div>
      )}
    </div>
  );
};

function getRedactPreview(entityType: string): string {
  const previews: Record<string, string> = {
    PERSON: '[PERSON]',
    EMAIL: 'XXX@XXX.XXX',
    PHONE: 'XXX-XXX-XXXX',
    SSN: 'XXX-XX-XXXX',
    DATE: 'XX/XX/XXXX',
    CREDIT_CARD: 'XXXX-XXXX-XXXX-XXXX',
  };
  return previews[entityType] || 'XXXX';
}
```

---

### **9. ADMIN DASHBOARD - TOKEN EXPLORER & AUDIT LOG**

**TokenExplorer Page** - Search/browse token mappings:
```tsx
// Features:
// - Search by tokenized value, original value (decrypted), entity type
// - Filter by date range, policy applied, context
// - Pagination, export CSV
// - "Restore" button (with auth challenge)
```

**AuditLog Page** - Compliance trail:
```tsx
// Features:
// - Filter by action (tokenize/restore/policy_change), org, user, date
// - Show metadata: IP, purpose, entity types affected
// - Export for compliance reports
```

---

### **10. INTEGRATION INTO EXISTING API (`api/main.py`)**

```python
# api/main.py - Additions only (don't modify existing endpoints)

from api.middleware.anonymization_middleware import AnonymizationMiddleware
from api.services.token_store import TokenStore
from api.services.policy_store import PolicyStore
from api.services.anonymizer import Anonymizer
from api.middleware.policy_engine import PolicyEngine
from api.middleware.entity_detector import EntityDetector
from api.database.connection import get_session_factory, init_db
from api.config.settings import settings

# Initialize services at startup
@app.on_event("startup")
async def startup():
    await init_db()
    session_factory = get_session_factory()
    
    # Initialize services
    token_store = TokenStore(session_factory, settings.ENCRYPTION_KEY)
    policy_store = PolicyStore(session_factory)
    policy_engine = PolicyEngine(policy_store)
    entity_detector = EntityDetector(min_confidence=0.5)
    anonymizer = Anonymizer()
    
    # Store in app state for access in endpoints
    app.state.token_store = token_store
    app.state.policy_store = policy_store
    app.state.policy_engine = policy_engine
    app.state.entity_detector = entity_detector
    app.state.anonymizer = anonymizer
    
    # Add middleware
    app.add_middleware(
        AnonymizationMiddleware,
        policy_engine=policy_engine,
        entity_detector=entity_detector,
        token_store=token_store,
        anonymizer=anonymizer,
        excluded_paths={"/health", "/info", "/docs", "/openapi.json", "/entities", "/predict", "/validate", "/mask", "/predict/batch"}
    )

# New endpoints for reverse tokenization (authorized only)
@app.post("/internal/restore", tags=["Reverse Tokenization"])
async def restore_tokens(
    request: RestoreRequest,
    current_user: User = Depends(get_current_user),  # Auth required
):
    restorer = Restorer(app.state.token_store, app.state.audit_log)
    results = await restorer.restore(request)
    return {"results": results}

@app.post("/internal/restore-text", tags=["Reverse Tokenization"])
async def restore_in_text(
    request: RestoreTextRequest,
    current_user: User = Depends(get_current_user),
):
    restorer = Restorer(app.state.token_store, app.state.audit_log)
    restored = await restorer.restore_in_text(
        request.text, request.org_id, current_user.id, request.purpose, request.ip
    )
    return {"restored_text": restored}
```

---

### **Testing Strategy**

| Test File | Coverage |
|-----------|----------|
| `tests/test_middleware.py` | Middleware interception, request/response processing, excluded paths |
| `tests/test_policy_engine.py` | Policy lookup, caching, context hashing, direction filtering |
| `tests/test_anonymizer.py` | All 3 strategies, overlapping entities, format preservation, determinism |
| `tests/test_restorer.py` | Authorization, decryption, audit logging, expiry, batch restore |
| `tests/test_token_store.py` | CRUD, encryption/decryption, context scoping, collision handling |
| `tests/test_admin_api.py` | Policy CRUD, presets, bulk update, entity types |

**Test Fixtures:**
- Sample texts with various PII types
- Mock organizations with different policy configs
- PostgreSQL testcontainer for integration tests

---

### **Dependencies to Add**

```txt
# requirements.txt additions
asyncpg>=0.28.0
sqlalchemy[asyncio]>=2.0.0
alembic>=1.11.0
cryptography>=41.0.0
pydantic-settings>=2.0.0
python-multipart>=0.0.6
faker>=20.0.0
redis>=4.5.0  # Optional: for policy cache
pytest-asyncio>=0.21.0
pytest-mock>=3.11.0
```

---

### **Deployment & Migration Steps**

1. **Add PostgreSQL** to `docker-compose.yml`
2. **Run migrations**: `alembic upgrade head`
3. **Create default org** with API key for existing API
4. **Deploy middleware** - test with excluded paths first
5. **Deploy admin dashboard** separately (Vercel/Netlify + Railway/Render for backend)
6. **Configure DNS**: `admin.yourdomain.com` → dashboard, `api.yourdomain.com` → FastAPI
7. **Load test** with synthetic PII data

---

### **Security Considerations**

| Concern | Mitigation |
|---------|------------|
| Token mapping DB exposure | Encrypt `original_value` at rest; separate DB user with minimal perms |
| Unauthorized restoration | RBAC + purpose-based auth + audit log + IP allowlist |
| Token collision | UUIDv7 tokens + unique constraint on (org, token, entity_type, context_hash) |
| Policy bypass | Middleware runs before routing; excluded paths explicitly listed |
| Audit tampering | Append-only audit table; consider WORM storage for compliance |
| Key rotation | Store key version; background job to re-encrypt on rotation |

---

### **Edge Cases & Mitigations**

| Edge Case | Mitigation |
|-----------|------------|
| **Nested/overlapping entities** | Sort by start desc, length desc; replace in place |
| **Huge request bodies (>10KB)** | Stream processing or reject with 413 |
| **Streaming LLM responses** | Buffer chunks or skip response anonymization (configurable) |
| **Policy cache stale** | TTL 60s + webhook invalidation on policy update |
| **Token mapping DB unavailable** | Fail-open (log warning, pass through) or fail-closed (configurable) |
| **Multiple orgs, same PII value** | Org-scoped tokens + context hash = different tokens |
| **Restoration of expired tokens** | Check `expires_at` before restore; deny if expired |
| **Concurrent policy updates** | DB transactions + row-level locks on policy table |
| **Faker locale mismatch** | Org setting for locale; fallback to en_US |

---

### **Implementation Phases**

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| **1. Foundation** | 1 week | DB schema, migrations, token store, policy store, config |
| **2. Core Engine** | 1 week | Policy engine, anonymizer strategies, entity detector wrapper |
| **3. Middleware** | 3 days | ASGI middleware, request/response processing, integration |
| **4. Reverse Tokenizer** | 3 days | Restorer service, authorization, audit logging |
| **5. Admin Dashboard** | 1.5 weeks | Backend API + React frontend (PolicyConfig, TokenExplorer, AuditLog) |
| **6. Testing & Hardening** | 1 week | Unit/integration tests, load testing, security review |
| **7. Deployment** | 2 days | Docker compose, migrations, monitoring, docs |

**Total: ~5-6 weeks**

---

### **What's NOT in Scope (per your request)**

- ❌ Modifying existing `/predict`, `/validate`, `/mask`, `/batch` endpoints
- ❌ Changing existing UI tabs (Predict/Validate/Mask/Batch/Entities)
- ❌ Model retraining or PHI labeling pipeline
- ❌ OCR integration
- ❌ Vector DB / patient summary features

---

This plan covers all edge cases from the Hekma document (external vs internal policies, reversible mappings, per-class config, audit trails) while keeping the existing API and UI intact. The middleware approach ensures zero changes to current endpoints.