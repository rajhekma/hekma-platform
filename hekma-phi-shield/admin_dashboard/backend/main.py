# admin_dashboard/backend/main.py
import logging
import sys
import os
from pathlib import Path

# Add parent api to path for shared services
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "api"))

from fastapi import FastAPI, Depends, HTTPException, status, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
import uuid
import hashlib

from api.config.settings import settings
from api.services.token_store import token_store
from api.services.policy_store import policy_store
from api.services.audit_log import audit_log
from api.services.org_store import org_store
from api.services.restorer import restorer, RestoreRequest
from api.models.policy import PIIPolicy, PolicyType, AnonymizeStrategy, PolicyPreset, PRESETS
from api.models.token_mapping import TokenMapping
from api.storage.base import AuditEntry, OrgRecord

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("admin-dashboard")

# This process is the pds-agent deployment: admin API (`admin_router`) and the
# React portal at /admin. Detection stays on api.main. The portal calls /api/v1/*
# on this same host, so VITE_API_URL stays unset.
app = FastAPI(
    title="PII Admin Dashboard API",
    description="Policy configuration, token exploration, and audit log for PII anonymization",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

admin_router = APIRouter()

# Auth
API_KEY_HEADER = APIKeyHeader(name="X-Admin-Key", auto_error=False)
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "hekma_admin_live_1e2f3a4b")

# Accept configured key, live dev secret, or fallback dev key
ALLOWED_ADMIN_KEYS = {
    ADMIN_API_KEY,
    "hekma_admin_live_1e2f3a4b",
    "admin-dev-key-change-in-production",
}


async def verify_admin_key(api_key: str = Depends(API_KEY_HEADER)):
    if not api_key or (api_key != ADMIN_API_KEY and api_key not in ALLOWED_ADMIN_KEYS):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key")
    return api_key


@admin_router.get("/auth/verify", tags=["Auth"])
async def verify_auth(key: str = Depends(verify_admin_key)):
    return {"status": "authenticated"}


# Models
class PolicyCreate(BaseModel):
    entity_type: str
    policy_type: PolicyType
    anonymize_strategy: AnonymizeStrategy = AnonymizeStrategy.RANDOMIZED
    custom_replacement: Optional[str] = None
    applies_to_internal: bool = True
    applies_to_external: bool = True


class PolicyResponse(PolicyCreate):
    id: str
    org_id: str
    created_at: str
    updated_at: str


class BulkPolicyUpdate(BaseModel):
    policies: List[PolicyCreate]


class PresetApply(BaseModel):
    preset: PolicyPreset
    org_id: str = "default-org"


class TokenSearchParams(BaseModel):
    org_id: Optional[str] = "all"
    tokenized_value: Optional[str] = None
    entity_type: Optional[str] = None
    policy_applied: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    limit: int = 100
    offset: int = 0


class RestoreTokenRequest(BaseModel):
    tokenized_values: List[str]
    org_id: str = "default-org"
    purpose: Literal["trial_matching", "db_storage", "audit", "patient_care", "research"]
    requester_id: str = "admin-user"
    ip_address: str = "127.0.0.1"


class AuditSearchParams(BaseModel):
    org_id: Optional[str] = "all"
    action: Optional[str] = None
    entity_type: Optional[str] = None
    performed_by: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    limit: int = 100
    offset: int = 0


class EntityTypesResponse(BaseModel):
    entity_types: List[str]
    count: int


class OrgUpdate(BaseModel):
    name: str
    contact_email: Optional[str] = "admin@hekma.ai"
    audit_retention_days: int = 0
    token_ttl_days: int = 0
    settings: Optional[dict] = None


class OrgResponse(BaseModel):
    id: str
    name: str
    contact_email: Optional[str] = "admin@hekma.ai"
    api_key: Optional[str] = "org_sk_live_••••••••••••••••"
    audit_retention_days: int = 0
    token_ttl_days: int = 0
    settings: Optional[dict] = None
    created_at: str
    updated_at: str


def policy_to_dict(p) -> dict:
    if hasattr(p, "dict"):
        return p.dict()
    elif hasattr(p, "model_dump"):
        return p.model_dump()
    elif hasattr(p, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(p)
    return getattr(p, "__dict__", {})


# API Routes
@app.get("/health", tags=["7. System Health & Observability"])
async def health():
    return {"status": "ok", "service": "admin-dashboard"}


@admin_router.get("/api/v1/entity-types", response_model=EntityTypesResponse, tags=["5. Policy & Governance"])
async def get_entity_types(_: str = Depends(verify_admin_key)):
    """Return PII model types plus PHI catalog types for policy configuration."""
    from api.services.phi.types import PHI_ENTITY_TYPE_NAMES

    try:
        from api.main import entity_types as pii_types
        merged = sorted(set(pii_types) | set(PHI_ENTITY_TYPE_NAMES))
        return EntityTypesResponse(entity_types=merged, count=len(merged))
    except Exception:
        default_types = [
            "PERSON", "EMAIL_ADDRESS", "US_SSN", "PHONE_NUMBER", "DATE",
            "ADDRESS", "CREDIT_CARD_NUMBER", "US_DRIVER_LICENSE", "US_PASSPORT",
            "IP_ADDRESS", "USERNAME", "COMPANY", "ORGANIZATION",
        ]
        merged = sorted(set(default_types) | set(PHI_ENTITY_TYPE_NAMES))
        return EntityTypesResponse(entity_types=merged, count=len(merged))


@admin_router.get("/api/v1/policy-presets", tags=["5. Policy & Governance"])
async def get_presets(_: str = Depends(verify_admin_key)):
    """Get available policy presets"""
    return {
        preset.value: {
            entity: policy.value for entity, policy in policies.items()
        }
        for preset, policies in PRESETS.items()
    }


@admin_router.get("/api/v1/orgs/{org_id}/policies", response_model=List[PolicyResponse], tags=["5. Policy & Governance"])
async def list_policies(org_id: str, _: str = Depends(verify_admin_key)):
    """List all policies for an org (including defaults)"""
    policies = await policy_store.get_by_org(org_id)
    return [
        PolicyResponse(
            **policy_to_dict(p),
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{org_id}:{p.entity_type}")),
            org_id=org_id,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        for p in policies
    ]


@admin_router.put("/api/v1/orgs/{org_id}/policies", response_model=List[PolicyResponse], tags=["5. Policy & Governance"])
async def bulk_update_policies(org_id: str, payload: BulkPolicyUpdate, _: str = Depends(verify_admin_key)):
    """Bulk upsert policies for an org"""
    policies = [PIIPolicy(**p.dict()) for p in payload.policies]
    await policy_store.upsert_many(org_id, policies)
    policy_engine.invalidate_cache(org_id)
    
    # Log policy change
    await audit_log.log_policy_change(
        org_id=org_id,
        performed_by="admin-user",
        ip_address="127.0.0.1",
        changes={p.entity_type: p.policy_type for p in policies}
    )
    
    return [
        PolicyResponse(
            **policy_to_dict(p),
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{org_id}:{p.entity_type}")),
            org_id=org_id,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        for p in policies
    ]


@admin_router.post("/api/v1/orgs/{org_id}/policies/preset", tags=["5. Policy & Governance"])
async def apply_preset(org_id: str, payload: PresetApply, _: str = Depends(verify_admin_key)):
    """Apply a policy preset to an org"""
    policies = await policy_store.apply_preset(org_id, payload.preset)
    policy_engine.invalidate_cache(org_id)
    
    await audit_log.log_policy_change(
        org_id=org_id,
        performed_by="admin-user",
        ip_address="127.0.0.1",
        changes={f"preset_{payload.preset}": "applied"}
    )
    
    return {"message": f"Preset {payload.preset} applied", "policy_count": len(policies)}


# Token Explorer
@admin_router.post("/api/v1/tokens/search", tags=["4. Reverse Tokenization & Token Vault"])
async def search_tokens(params: TokenSearchParams, _: str = Depends(verify_admin_key)):
    """Search token mappings with filters across all or specific orgs"""
    target_org = params.org_id if (params.org_id and params.org_id != "all") else "all"
    mappings = await token_store.get_all_for_org(target_org)
    
    # Apply filters
    if params.tokenized_value:
        mappings = [m for m in mappings if params.tokenized_value.lower() in m.tokenized_value.lower() or params.tokenized_value.lower() in (m.original_value or '').lower()]
    if params.entity_type:
        mappings = [m for m in mappings if m.entity_type == params.entity_type]
    if params.policy_applied:
        mappings = [m for m in mappings if m.policy_applied == params.policy_applied]
    if params.date_from:
        mappings = [m for m in mappings if m.created_at >= params.date_from]
    if params.date_to:
        mappings = [m for m in mappings if m.created_at <= params.date_to]
    
    # Always show latest tokens first
    mappings.sort(key=lambda m: m.created_at if m.created_at else datetime.min, reverse=True)
    
    total = len(mappings)
    mappings = mappings[params.offset:params.offset + params.limit]
    
    return {
        "total": total,
        "offset": params.offset,
        "limit": params.limit,
        "items": [
            {
                "id": str(m.id),
                "org_id": m.org_id,
                "tokenized_value": m.tokenized_value,
                "original_value": m.original_value,
                "entity_type": m.entity_type,
                "policy_applied": m.policy_applied,
                "context_hash": m.context_hash,
                "confidence": m.confidence,
                "created_at": m.created_at.isoformat(),
                "expires_at": m.expires_at.isoformat() if m.expires_at else None,
                "restored_at": m.restored_at.isoformat() if m.restored_at else None,
                "restored_by": m.restored_by,
            }
            for m in mappings
        ]
    }


@admin_router.post("/api/v1/tokens/restore", tags=["4. Reverse Tokenization & Token Vault"])
async def restore_tokens(payload: RestoreTokenRequest, _: str = Depends(verify_admin_key)):
    """Restore original values for given tokens (authorized only)"""
    request = RestoreRequest(
        tokenized_values=payload.tokenized_values,
        org_id=payload.org_id,
        requester_id=payload.requester_id,
        ip_address=payload.ip_address,
        purpose=payload.purpose,
    )
    results = await restorer.restore(request)
    
    return {
        "results": [
            {
                "tokenized_value": r.tokenized_value,
                "original_value": r.original_value,
                "entity_type": r.entity_type,
                "restored": r.restored,
                "error": r.error,
            }
            for r in results
        ]
    }


@admin_router.get("/api/v1/tokens/stats/{org_id}", tags=["4. Reverse Tokenization & Token Vault"])
async def token_stats(org_id: str, _: str = Depends(verify_admin_key)):
    """Get token mapping statistics for an org or global"""
    target_org = org_id if (org_id and org_id != "all") else "all"
    mappings = await token_store.get_all_for_org(target_org)
    
    by_entity = {}
    by_policy = {}
    for m in mappings:
        by_entity[m.entity_type] = by_entity.get(m.entity_type, 0) + 1
        by_policy[m.policy_applied] = by_policy.get(m.policy_applied, 0) + 1
    
    return {
        "total_mappings": len(mappings),
        "by_entity_type": by_entity,
        "by_policy": by_policy,
        "restored_count": sum(1 for m in mappings if m.restored_at),
        "expired_count": sum(1 for m in mappings if m.expires_at and m.expires_at < datetime.utcnow()),
    }


# Audit Log
@admin_router.post("/api/v1/audit/search", tags=["6. HIPAA Audit Logs"])
async def search_audit_log(params: AuditSearchParams, _: str = Depends(verify_admin_key)):
    """Search audit log with filters across all records"""
    target_org = params.org_id if (params.org_id and params.org_id != "all") else "all"
    logs = await audit_log.get_for_org(target_org, limit=1000)
    
    if params.action:
        logs = [l for l in logs if l.action == params.action]
    if params.entity_type:
        logs = [l for l in logs if l.entity_type == params.entity_type]
    if params.performed_by:
        logs = [l for l in logs if l.performed_by == params.performed_by]
    if params.date_from:
        logs = [l for l in logs if l.created_at >= params.date_from]
    if params.date_to:
        logs = [l for l in logs if l.created_at <= params.date_to]
    
    total = len(logs)
    logs = logs[params.offset:params.offset + params.limit]
    
    return {
        "total": total,
        "offset": params.offset,
        "limit": params.limit,
        "items": [
            {
                "id": str(l.id),
                "org_id": l.org_id,
                "action": l.action,
                "entity_type": l.entity_type,
                "tokenized_value": l.tokenized_value,
                "performed_by": l.performed_by,
                "ip_address": l.ip_address,
                "metadata": l.metadata,
                "created_at": l.created_at.isoformat(),
            }
            for l in logs
        ]
    }


@admin_router.get("/api/v1/audit/stats/{org_id}", tags=["6. HIPAA Audit Logs"])
async def audit_stats(org_id: str, _: str = Depends(verify_admin_key)):
    """Get audit log statistics"""
    logs = await audit_log.get_for_org(org_id, limit=10000)
    
    by_action = {}
    by_entity = {}
    by_user = {}
    for l in logs:
        by_action[l.action] = by_action.get(l.action, 0) + 1
        if l.entity_type:
            by_entity[l.entity_type] = by_entity.get(l.entity_type, 0) + 1
        by_user[l.performed_by] = by_user.get(l.performed_by, 0) + 1
    
    return {
        "total_events": len(logs),
        "by_action": by_action,
        "by_entity_type": by_entity,
        "by_user": by_user,
    }


# Organization Management (Multi-Tenant)
@admin_router.get("/api/v1/orgs", response_model=List[OrgResponse], tags=["8. Admin Portal"])
async def list_organizations(_: str = Depends(verify_admin_key)):
    """List all registered organizations and active tenant IDs in real-time."""
    orgs = await org_store.list_orgs()
    return [
        OrgResponse(
            id=o.org_id,
            name=o.name,
            contact_email=o.contact_email,
            api_key=o.raw_api_key_preview,
            audit_retention_days=o.audit_retention_days,
            token_ttl_days=o.token_ttl_days,
            settings={"locale": "en_US", "timezone": "UTC"},
            created_at=o.created_at.isoformat() if hasattr(o.created_at, "isoformat") else str(o.created_at),
            updated_at=o.updated_at.isoformat() if hasattr(o.updated_at, "isoformat") else str(o.updated_at),
        )
        for o in orgs
    ]


@admin_router.get("/api/v1/orgs/{org_id}", response_model=OrgResponse, tags=["8. Admin Portal"])
async def get_organization(org_id: str, _: str = Depends(verify_admin_key)):
    """Get organization profile and governance settings from PostgreSQL."""
    o = await org_store.get_org(org_id)
    return OrgResponse(
        id=o.org_id,
        name=o.name,
        contact_email=o.contact_email,
        api_key=o.raw_api_key_preview,
        audit_retention_days=o.audit_retention_days,
        token_ttl_days=o.token_ttl_days,
        settings={"locale": "en_US", "timezone": "UTC"},
        created_at=o.created_at.isoformat() if hasattr(o.created_at, "isoformat") else str(o.created_at),
        updated_at=o.updated_at.isoformat() if hasattr(o.updated_at, "isoformat") else str(o.updated_at),
    )


@admin_router.put("/api/v1/orgs/{org_id}", response_model=OrgResponse, tags=["8. Admin Portal"])
async def update_organization(org_id: str, payload: OrgUpdate, _: str = Depends(verify_admin_key)):
    """Update organization profile and data retention settings in PostgreSQL."""
    org = await org_store.get_org(org_id)
    org.name = payload.name
    org.contact_email = payload.contact_email
    org.audit_retention_days = payload.audit_retention_days
    org.token_ttl_days = payload.token_ttl_days
    saved = await org_store.save_org(org)

    await audit_log.log_policy_change(
        org_id=org_id,
        performed_by="admin-user",
        ip_address="127.0.0.1",
        changes={
            "name": payload.name,
            "contact_email": payload.contact_email,
            "audit_retention_days": payload.audit_retention_days,
            "token_ttl_days": payload.token_ttl_days,
        },
    )

    return OrgResponse(
        id=saved.org_id,
        name=saved.name,
        contact_email=saved.contact_email,
        api_key=saved.raw_api_key_preview,
        audit_retention_days=saved.audit_retention_days,
        token_ttl_days=saved.token_ttl_days,
        settings={"locale": "en_US", "timezone": "UTC"},
        created_at=saved.created_at.isoformat() if hasattr(saved.created_at, "isoformat") else str(saved.created_at),
        updated_at=saved.updated_at.isoformat() if hasattr(saved.updated_at, "isoformat") else str(saved.updated_at),
    )


@admin_router.post("/api/v1/orgs/{org_id}/api-key", tags=["8. Admin Portal"])
async def rotate_organization_key(org_id: str, _: str = Depends(verify_admin_key)):
    """Generate and rotate API key for an organization."""
    org, new_raw_key = await org_store.rotate_key(org_id)
    await audit_log.log_policy_change(
        org_id=org_id,
        performed_by="admin-user",
        ip_address="127.0.0.1",
        changes={"api_key": "rotated"},
    )
    return {
        "org_id": org_id,
        "api_key": new_raw_key,
        "preview": org.raw_api_key_preview,
        "message": "API key successfully rotated",
    }


@admin_router.post("/api/v1/tokens/purge-expired", tags=["4. Reverse Tokenization & Token Vault"])
async def purge_expired_tokens(org_id: Optional[str] = None, _: str = Depends(verify_admin_key)):
    """Purge lapsed tokens where expires_at < NOW()."""
    purged_count = 0
    if hasattr(token_store, "purge_expired"):
        purged_count = await token_store.purge_expired(org_id)

    return {
        "purged_count": purged_count,
        "org_id": org_id or "all_organizations",
        "timestamp": datetime.utcnow().isoformat(),
        "status": "success",
    }


# Import policy_engine for cache invalidation
from api.middleware.policy_engine import policy_engine

app.include_router(admin_router)

# Portal bundle. Built by the agent image (or `npm run build` locally). Never
# mount at "/" — that would swallow /health, /docs, and /api/v1.
ADMIN_DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def _dist_file(full_path: str) -> Optional[Path]:
    """Resolve a portal asset inside dist, or None when it is missing or unsafe."""
    if not full_path or ".." in Path(full_path).parts:
        return None
    root = ADMIN_DIST_DIR.resolve()
    candidate = (root / full_path).resolve()
    if root not in candidate.parents:
        return None
    if candidate.is_file():
        return candidate
    return None


if (ADMIN_DIST_DIR / "index.html").is_file():
    @app.get("/admin", include_in_schema=False)
    async def redirect_admin_root():
        return RedirectResponse(url="/admin/", status_code=307)

    @app.get("/admin/{full_path:path}", include_in_schema=False)
    async def serve_admin_spa(full_path: str):
        if ".." in Path(full_path).parts:
            raise HTTPException(status_code=404, detail="Not found")
        asset = _dist_file(full_path)
        if asset is not None:
            return FileResponse(asset)
        return FileResponse(ADMIN_DIST_DIR / "index.html")

    app.mount("/admin", StaticFiles(directory=str(ADMIN_DIST_DIR), html=True), name="admin_ui")
else:
    logger.warning(
        "Admin portal bundle not found at %s; /admin will return 503. "
        "Build admin_dashboard/frontend (npm run build) or use the agent Docker image.",
        ADMIN_DIST_DIR,
    )

    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/{full_path:path}", include_in_schema=False)
    async def admin_portal_not_built(full_path: str = ""):
        raise HTTPException(
            status_code=503,
            detail="Admin portal is not built. The admin API is still available under /api/v1.",
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8083)