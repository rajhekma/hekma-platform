# Architecture Document: PII Anonymization Middle Layer

---

## 🏗️ **System Architecture Overview**

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    CLIENT APPLICATIONS                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                    │
│  │ EHR Systems  │  │ Internal     │  │ External     │  │ Admin UI     │                    │
│  │ (Ingest)     │  │ Services     │  │ LLMs         │  │ (Dashboard)  │                    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                    │
└─────────│─────────────────│─────────────────│─────────────────│────────────────────────────┘
          │                 │                 │                 │
          ▼                 ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                              ANONYMIZATION MIDDLEWARE (ASGI)                                │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│  │                        REQUEST PROCESSING PIPELINE                                   │   │
│  │                                                                                     │   │
│  │  1. EXTRACT ORG CONTEXT          2. DETERMINE DIRECTION                              │   │
│  │     - API Key / JWT                  - Internal (inter-service)                      │   │
│  │     - Header: X-Org-ID               - External (LLM export)                         │   │
│  │     - Default org for testing                                                  │   │
│  │                                                                                     │   │
│  │  3. DETECT PII ENTITIES          4. LOOKUP POLICIES                                  │   │
│  │     - Reuse existing /predict      - Per-org, per-entity-type                        │   │
│  │     - Min confidence threshold     - Direction-aware (internal/external)             │   │
│  │     - Merge BIO tags to spans      - Cache with TTL                                  │   │
│  │                                                                                     │   │
│  │  5. APPLY ANONYMIZATION          6. STORE REVERSE MAPPINGS                           │   │
│  │     - Ignore / Anonymize / Redact  - Encrypted original values                       │   │
│  │     - Randomized / Alternate       - Context hash for scoping                        │   │
│  │     - Format-preserving            - TTL/expiry support                              │   │
│  │     - Deterministic alternates     - Audit trail                                     │   │
│  │                                                                                     │   │
│  │  7. REWRITE REQUEST BODY         8. FORWARD TO APP                                   │   │
│  │     - Recursive field processing   - Transparent to existing endpoints               │   │
│  │     - Preserve non-text fields     - Response processing for external                │   │
│  └─────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
│  MemoryTokenStore   │ │  MemoryPolicyStore  │ │   MemoryAuditLog    │
│  (In-Memory Dict)   │ │  (In-Memory Dict)   │ │  (Append-only List) │
│                     │ │                     │ │                     │
│ • org_id →          │ │ • org_id →          │ │ • Sequential log    │
│   {token → mapping} │ │   [PIIPolicy]       │ │ • JSONL persistence │
│ • Encrypted values  │ │ • Default policies  │ │ • Filter by org,    │
│ • Context hash      │ │   (HIPAA, GDPR)     │ │   action, date      │
│ • TTL/expiry        │ │ • Bulk upsert       │ │ • Tamper-evident    │
└─────────────────────┘ └─────────────────────┘ └─────────────────────┘
          │                        │                        │
          └────────────────────────┼────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │      ADMIN DASHBOARD        │
                    │  (Separate FastAPI + React) │
                    │                             │
                    │ • PolicyConfig Page         │
                    │   - Per-entity radio buttons│
                    │   - Strategy selector       │
                    │   - Scope checkboxes        │
                    │   - Preset templates        │
                    │                             │
                    │ • TokenExplorer Page        │
                    │   - Search/filter tokens    │
                    │   - Authorized restore      │
                    │                             │
                    │ • AuditLog Page             │
                    │   - Compliance trail        │
                    │   - Export CSV/JSON         │
                    └─────────────────────────────┘
```

---

## 🔄 **Data Flow Diagrams**

### **1. External LLM Export Flow (Primary Demo Path)**

```
Client (EHR)                              FastAPI App                              External LLM
    │                                        │                                           │
    │  POST /api/v1/llm/query                │                                           │
    │  {                                     │                                           │
    │    "prompt": "Patient John Doe...",    │                                           │
    │    "context": "trial_matching"         │                                           │
    │  }                                     │                                           │
    │───────────────────────────────────────>│                                           │
    │                                        │  [Middleware Intercepts]                   │
    │                                        │  1. Extract org_id from API key           │
    │                                        │  2. Direction = "external"                │
    │                                        │  3. Detect PII: "John Doe" → PERSON       │
    │                                        │  4. Lookup policy: PERSON → anonymize     │
    │                                        │  5. Apply: "John Doe" → "Jane Smith"      │
    │                                        │  6. Store mapping: "Jane Smith" ↔ "John   │
    │                                        │     Doe" (encrypted, context_hash)        │
    │                                        │  7. Rewrite body: "Patient Jane Smith..." │
    │                                        │                                           │
    │                                        │  POST /internal/llm/proxy                  │
    │                                        │  { "prompt": "Patient Jane Smith..." }    │
    │                                        │─────────────────────────────────────────>  │
    │                                        │                                           │
    │                                        │  Response: "Patient qualifies..."         │
    │                                        │<─────────────────────────────────────────  │
    │                                        │  [Optional: Process response for PII]     │
    │                                        │                                           │
    │  Response: "Patient qualifies..."      │                                           │
    │<───────────────────────────────────────│                                           │
    │                                        │                                           │
```

### **2. Internal Service-to-Service Flow**

```
Service A                                  FastAPI App                                  Service B
    │                                        │                                           │
    │  POST /internal/patient/123            │                                           │
    │  { "notes": "Patient Jane Smith..." }  │                                           │
    │───────────────────────────────────────>│                                           │
    │                                        │  [Middleware Intercepts]                   │
    │                                        │  1. Direction = "internal"                │
    │                                        │  2. Policy: PERSON → ignore (internal)    │
    │                                        │  3. Pass through unchanged                │
    │                                        │                                           │
    │                                        │  POST /internal/patient/123                │
    │                                        │─────────────────────────────────────────>  │
    │                                        │                                           │
```

### **3. Authorized Restoration Flow (Trial Matching)**

```
Authorized User                          Admin Dashboard / API                      Token Store
    │                                        │                                           │
    │  POST /admin/tokens/restore            │                                           │
    │  {                                     │                                           │
    │    "tokens": ["Jane Smith"],           │                                           │
    │    "purpose": "trial_matching",        │                                           │
    │    "org_id": "org-123"                 │                                           │
    │  }                                     │                                           │
    │───────────────────────────────────────>│                                           │
    │                                        │  1. Verify auth (RBAC, purpose allowlist) │
    │                                        │  2. Lookup token mappings                 │
    │                                        │  3. Check expiry, authorization           │
    │                                        │  4. Decrypt original values               │
    │                                        │  5. Update mapping: restored_at, by       │
    │                                        │  6. Audit log entry                       │
    │                                        │                                           │
    │  Response: {                           │                                           │
    │    "results": [                        │                                           │
    │      {"token": "Jane Smith",           │                                           │
    │       "original": "John Doe",          │                                           │
    │       "restored": true}                │                                           │
    │    ]                                   │                                           │
    │  }                                     │                                           │
    │<───────────────────────────────────────│                                           │
    │                                        │                                           │
```

---

## 🧩 **Component Responsibilities**

| Component | File | Responsibility |
|-----------|------|----------------|
| **AnonymizationMiddleware** | `api/middleware/anonymization_middleware.py` | ASGI middleware; intercepts requests, applies policies, stores mappings |
| **PolicyEngine** | `api/middleware/policy_engine.py` | Evaluates policies per org/entity/direction; caching; context hashing |
| **EntityDetector** | `api/middleware/entity_detector.py` | Wrapper around existing `detect_entities()`; converts to `Entity` dataclass |
| **Anonymizer** | `api/services/anonymizer.py` | Three strategies: Redact, Randomized, Alternate; format preservation |
| **TokenStore** | `api/services/token_store.py` | CRUD for token mappings; encryption; context scoping; TTL |
| **PolicyStore** | `api/services/policy_store.py` | CRUD for policies; defaults (HIPAA, GDPR); bulk operations |
| **Restorer** | `api/services/restorer.py` | Authorized reverse tokenization; audit logging; batch restore |
| **AuditLog** | `api/services/audit_log.py` | Append-only log; tokenize/restore/policy_change events |
| **MemoryStorage** | `api/storage/memory.py` | In-memory implementations of all store protocols |
| **JsonPersistence** | `api/storage/json_persist.py` | Mixin for optional JSON/JSONL file persistence |
| **Settings** | `api/config/settings.py` | Environment-based config; `STORAGE_BACKEND=memory\|json` |

---

## 🔐 **Security Architecture**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEFENSE IN DEPTH LAYERS                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  LAYER 1: NETWORK                                                           │
│  ├─ TLS 1.3 for all external traffic                                        │
│  ├─ Private network for internal services                                   │
│  └─ Admin dashboard on separate subdomain with IP allowlist                │
│                                                                             │
│  LAYER 2: AUTHENTICATION                                                    │
│  ├─ API Keys (hashed in store) for service-to-service                      │
│  ├─ JWT with org_id claim for user requests                                │
│  └─ Separate admin credentials (OAuth2/OIDC)                               │
│                                                                             │
│  LAYER 3: AUTHORIZATION                                                     │
│  ├─ Org-scoped data isolation (org_id on every record)                     │
│  ├─ Purpose-based restoration (trial_matching, db_storage, audit, care)   │
│  ├─ RBAC: admin/policy_editor/auditor roles                                │
│  └─ IP allowlist for sensitive operations                                  │
│                                                                             │
│  LAYER 4: DATA PROTECTION                                                   │
│  ├─ Encryption at rest: Fernet (AES-256) for original values              │
│  ├─ Encryption in transit: TLS                                              │
│  ├─ Key rotation support (versioned keys)                                  │
│  └─ Context hashing prevents cross-request token correlation              │
│                                                                             │
│  LAYER 5: AUDIT & COMPLIANCE                                                │
│  ├─ Append-only audit log (JSONL)                                           │
│  ├─ Every tokenization/restoration logged with actor, IP, purpose         │
│  ├─ Tamper-evident: hash chain on audit entries                            │
│  └─ Export for compliance reports (HIPAA, GDPR, SOC2)                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 **Data Models**

### **TokenMapping**
```python
@dataclass
class TokenMapping:
    id: UUID                          # Primary key
    org_id: str                       # Organization scope
    original_value: str               # ENCRYPTED at rest
    tokenized_value: str              # The replacement token
    entity_type: str                  # PERSON, EMAIL, SSN, etc.
    policy_applied: str               # ignore, anonymize, redact
    context_hash: str                 # SHA256(org:direction:path:user)[:32]
    confidence: float                 # Model confidence (0-1)
    created_at: datetime              # When tokenized
    expires_at: Optional[datetime]    # TTL for auto-cleanup
    restored_at: Optional[datetime]   # When restored (audit)
    restored_by: Optional[str]        # Who restored (audit)
```

### **PIIPolicy**
```python
@dataclass
class PIIPolicy:
    entity_type: str                  # PERSON, EMAIL, DATE, etc.
    policy_type: str                  # ignore | anonymize | redact
    anonymize_strategy: str           # randomized | alternate
    custom_replacement: Optional[str] # For redact: custom placeholder
    applies_to_internal: bool         # Apply to internal flows
    applies_to_external: bool         # Apply to external LLM exports
```

### **AuditEntry**
```python
@dataclass
class AuditEntry:
    id: UUID
    org_id: str
    action: str                       # tokenize | restore | policy_change
    entity_type: Optional[str]
    tokenized_value: Optional[str]
    performed_by: str                 # API key ID, user ID, system
    ip_address: Optional[str]
    metadata: dict                    # Extensible: purpose, request_id, etc.
    created_at: datetime
```

---

## 🔀 **Policy Resolution Logic**

```
POLICY LOOKUP (per entity in request)
│
├─ 1. Get org policies (cached, TTL 60s)
│
├─ 2. Filter by direction
│    ├─ direction=external → policies where applies_to_external=true
│    └─ direction=internal → policies where applies_to_internal=true
│
├─ 3. Match entity_type (case-insensitive)
│    ├─ Exact match → use that policy
│    ├─ No match → DEFAULT: ignore
│    └─ Multiple matches (shouldn't happen) → most restrictive
│
├─ 4. Evaluate policy_type
│    ├─ ignore → skip entity, pass through unchanged
│    ├─ redact → apply RedactStrategy (format-preserving X's)
│    └─ anonymize → apply strategy:
│         ├─ randomized → new fake value each time (Faker)
│         └─ alternate → deterministic per original (seeded random)
│
└─ 5. Generate context_hash for token scoping
     hash = SHA256(f"{org_id}:{direction}:{path}:{user_id}")[:32]
```

**Precedence**: `REDACT > ANONYMIZE > IGNORE` (most restrictive wins)

---

## 🎯 **Anonymization Strategies Detail**

| Strategy | Use Case | Example (Input → Output) | Reversible |
|----------|----------|--------------------------|------------|
| **Redact** | Maximum privacy, compliance | "John Doe" → "XXXX XXXX"<br>"555-123-4567" → "XXX-XXX-XXXX"<br>"john@email.com" → "XXX@XXX.XXX" | ✅ Yes (stored) |
| **Randomized** | Analytics, ML training | "John Doe" → "Sarah Johnson"<br>"555-123-4567" → "212-555-0199"<br>"john@email.com" → "fake@domain.com" | ✅ Yes (stored) |
| **Alternate** | Consistent de-identification | "John Doe" → "Person_7f3a" (always same)<br>"john@email.com" → "user_7f3a@anon.com" | ✅ Yes (stored) |

**Format Preservation Rules:**
- SSN: `XXX-XX-XXXX` (preserve dashes)
- Phone: `XXX-XXX-XXXX` or `(XXX) XXX-XXXX`
- Credit Card: `XXXX-XXXX-XXXX-XXXX`
- Email: `XXX@XXX.XXX`
- Date: `XX/XX/XXXX` or `XXXX-XX-XX`
- Custom: `X` * length

---

## 🔄 **Context Hash Scoping**

```
CONTEXT HASH = SHA256(org_id + ":" + direction + ":" + path + ":" + user_id)[:32]

Purpose: Same PII value → Different tokens in different contexts

Example:
  Org: "hospital-a"
  Direction: "external"
  Path: "/api/v1/llm/query"
  User: "dr-smith"

  Context Hash: "a1b2c3d4e5f6..."

  "John Doe" in this context → "Jane Smith" (token_1)
  "John Doe" in different context (different path/user) → "Bob Wilson" (token_2)

Benefits:
  - Prevents token correlation attacks
  - Supports different policies per endpoint
  - Enables per-request audit granularity
```

---

## 📈 **Scalability Considerations**

| Component | Current (Dev) | Production Ready |
|-----------|---------------|------------------|
| **Token Store** | In-memory dict | PostgreSQL + Redis cache |
| **Policy Store** | In-memory dict | PostgreSQL + in-memory cache |
| **Audit Log** | In-memory list + JSONL | PostgreSQL (partitioned) + WORM |
| **Policy Cache** | Dict with TTL | Redis (distributed) |
| **Middleware** | Single process | Multiple workers + shared cache |

**Migration Path**: Replace `MemoryTokenStore`/`MemoryPolicyStore`/`MemoryAuditLog` with PostgreSQL implementations — **same Protocol interfaces, zero changes to middleware or services**.

---

## 🧪 **Testing Architecture**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              TEST LAYERS                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  UNIT TESTS (Fast, Isolated)                                                │
│  ├─ test_policy_engine.py      → Policy lookup, caching, context hash      │
│  ├─ test_anonymizer.py         → All 3 strategies, edge cases              │
│  ├─ test_restorer.py           → Auth, decryption, audit, expiry           │
│  ├─ test_token_store.py        → CRUD, encryption, context scoping         │
│  └─ test_storage_memory.py     → In-memory store implementations           │
│                                                                             │
│  INTEGRATION TESTS (Real Components)                                        │
│  ├─ test_middleware.py         → Full request/response cycle               │
│  ├─ test_admin_api.py          → Policy CRUD, token restore, audit         │
│  └─ test_end_to_end.py         → EHR → Middleware → LLM → Restore          │
│                                                                             │
│  FIXTURES                                                                   │
│  ├─ conftest.py                → Fresh MemoryTokenStore per test           │
│  ├─ sample_texts.py            → Realistic PII samples                     │
│  └─ policy_presets.py          → HIPAA, GDPR, PCI configs                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 **Deployment Architecture**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PRODUCTION DEPLOYMENT                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                    │
│  │   Load      │    │   FastAPI   │    │  PostgreSQL │                    │
│  │  Balancer   │───>│  (3+ pods)  │───>│  (Primary)  │                    │
│  │  (TLS Term) │    │             │    │             │                    │
│  └─────────────┘    └─────────────┘    └─────────────┘                    │
│                            │                      │                        │
│                            │                      ▼                        │
│                            │               ┌─────────────┐                │
│                            └──────────────>│    Redis    │                │
│                                           │  (Cache)    │                │
│                                           └─────────────┘                │
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐                                        │
│  │   Admin     │    │  Admin      │                                        │
│  │  Dashboard  │───>│  Backend    │                                        │
│  │  (Vercel)   │    │  (Railway)  │                                        │
│  └─────────────┘    └─────────────┘                                        │
│                                                                             │
│  MONITORING: Prometheus + Grafana + Structured Logging (JSON)              │
│  ALERTING: P99 latency, error rate, token store size, audit log growth     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📋 **Configuration Reference**

### **Environment Variables (.env)**
```bash
# Storage
STORAGE_BACKEND=memory          # memory | json
DATA_DIR=./data                 # For JSON persistence
ENCRYPTION_KEY=dev-key-change-in-production-32-bytes!!

# Middleware
ANONYMIZATION_ENABLED=true
POLICY_CACHE_TTL=60
EXCLUDED_PATHS=/health,/info,/docs,/openapi.json,/entities,/predict,/validate,/mask,/predict/batch

# App
ENVIRONMENT=development
LOG_LEVEL=INFO

# Production (when ready)
# DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/pii_db
# REDIS_URL=redis://host:6379/0
```

---

## 🔮 **Future Extensibility Points**

| Extension Point | Current State | Future Enhancement |
|-----------------|---------------|-------------------|
| **Custom Entity Types** | Fixed from model | Dynamic registration via admin UI |
| **Policy DSL** | Simple enum | Expression-based (CEL/RegO) |
| **Token Format** | Faker-based | Format-preserving encryption (FPE) |
| **Restoration Auth** | Purpose allowlist | OPA policies, ABAC |
| **Audit Storage** | JSONL | Immutable ledger (CloudTrail, QLDB) |
| **Multi-tenancy** | Org-scoped | Hierarchical orgs, data residency |
| **Streaming** | Buffer + process | True streaming (async generators) |

---

## ✅ **Implementation Checklist**

### Phase 1: Foundation (Week 1)
- [ ] `api/storage/base.py` - Protocols
- [ ] `api/storage/memory.py` - In-memory implementations
- [ ] `api/storage/json_persist.py` - JSON persistence mixin
- [ ] `api/storage/__init__.py` - Factory
- [ ] `api/config/settings.py` - Configuration
- [ ] `api/models/*.py` - Pydantic models
- [ ] Update `requirements.txt` - Add `aiofiles`

### Phase 2: Core Engine (Week 2)
- [ ] `api/middleware/policy_engine.py` - PolicyEngine, PolicyContext
- [ ] `api/middleware/entity_detector.py` - EntityDetector wrapper
- [ ] `api/services/anonymizer.py` - Three strategies
- [ ] `api/services/token_store.py` - TokenStore service
- [ ] `api/services/policy_store.py` - PolicyStore service
- [ ] `api/services/audit_log.py` - AuditLog service
- [ ] `api/services/restorer.py` - Restorer service

### Phase 3: Middleware (Week 3)
- [ ] `api/middleware/anonymization_middleware.py` - ASGI middleware
- [ ] `api/middleware/exceptions.py` - Custom exceptions
- [ ] Integrate into `api/main.py` - Startup, middleware mount
- [ ] Add `/internal/restore` endpoints

### Phase 4: Admin Dashboard (Week 4-5)
- [ ] Backend: FastAPI + policy/token/audit APIs
- [ ] Frontend: React + PolicyConfig, TokenExplorer, AuditLog pages
- [ ] Deploy separately (Vercel + Railway/Render)

### Phase 5: Testing & Hardening (Week 6)
- [ ] Unit tests for all components
- [ ] Integration tests for middleware
- [ ] Load testing with synthetic data
- [ ] Security review

---

This architecture provides **zero-database dev experience** with **production-ready PostgreSQL migration path**, **comprehensive audit trails**, **flexible policy configuration**, and **clean separation of concerns** via Protocol-based storage abstraction.