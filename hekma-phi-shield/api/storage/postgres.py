import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, delete, distinct
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.database.connection import get_db_session
from api.database.models import TokenMappingModel, PolicyModel, AuditLogModel, OrgModel
from api.models.policy import PRESETS, PolicyPreset
from api.services.crypto import crypto_engine
from api.storage.base import (
    AuditEntry,
    AuditLog,
    OrgRecord,
    OrgStore,
    PIIPolicy,
    PolicyStore,
    TokenMapping,
    TokenStore,
)

logger = logging.getLogger("pii-phi.storage.postgres")


class PostgresTokenStore(TokenStore):
    """Production PostgreSQL Token Vault with AES-256 / KMS encryption and HMAC indexing."""

    def __init__(self, crypto=None):
        self._crypto = crypto or crypto_engine

    def encrypt(self, value: str) -> str:
        return self._crypto.encrypt(value)

    def decrypt(self, value: str) -> str:
        return self._crypto.decrypt(value)

    async def save(self, mapping: TokenMapping) -> TokenMapping:
        orig_plain = mapping.original_value
        # If it's not already encrypted, encrypt it
        if not (orig_plain.startswith("gAAAAA") or orig_plain.startswith("kms:")):
            orig_hash = self._crypto.hash_plaintext(orig_plain)
            enc_val = self._crypto.encrypt(orig_plain)
        else:
            # Already ciphertext
            try:
                decrypted = self._crypto.decrypt(orig_plain)
                orig_hash = self._crypto.hash_plaintext(decrypted)
            except Exception:
                orig_hash = self._crypto.hash_plaintext(orig_plain)
            enc_val = orig_plain

        db_model = TokenMappingModel(
            id=mapping.id if isinstance(mapping.id, uuid.UUID) else uuid.UUID(str(mapping.id)),
            org_id=mapping.org_id,
            original_value=enc_val,
            original_hash=orig_hash,
            tokenized_value=mapping.tokenized_value,
            entity_type=mapping.entity_type,
            policy_applied=mapping.policy_applied,
            context_hash=mapping.context_hash or "",
            confidence=mapping.confidence,
            created_at=mapping.created_at or datetime.now(timezone.utc),
            expires_at=mapping.expires_at,
            restored_at=mapping.restored_at,
            restored_by=mapping.restored_by,
        )

        async with get_db_session() as session:
            session.add(db_model)
            await session.flush()

        return mapping

    async def get_by_token(
        self, org_id: str, token: str, entity_types: Optional[List[str]] = None
    ) -> Optional[TokenMapping]:
        async with get_db_session() as session:
            stmt = select(TokenMappingModel).where(
                TokenMappingModel.org_id == org_id,
                TokenMappingModel.tokenized_value == token,
            )
            if entity_types:
                stmt = stmt.where(TokenMappingModel.entity_type.in_(entity_types))
            
            result = await session.execute(stmt)
            row = result.scalars().first()
            if not row:
                return None

            try:
                decrypted_orig = self._crypto.decrypt(row.original_value)
            except Exception as e:
                logger.error("Failed to decrypt token %s: %s", token, e)
                decrypted_orig = row.original_value

            return TokenMapping(
                id=row.id,
                org_id=row.org_id,
                original_value=decrypted_orig,
                tokenized_value=row.tokenized_value,
                entity_type=row.entity_type,
                policy_applied=row.policy_applied,
                context_hash=row.context_hash or "",
                confidence=row.confidence,
                created_at=row.created_at,
                expires_at=row.expires_at,
                restored_at=row.restored_at,
                restored_by=row.restored_by,
            )

    async def get_by_original(self, org_id: str, original_value: str) -> Optional[TokenMapping]:
        orig_hash = self._crypto.hash_plaintext(original_value)
        async with get_db_session() as session:
            stmt = select(TokenMappingModel).where(
                TokenMappingModel.org_id == org_id,
                TokenMappingModel.original_hash == orig_hash,
            )
            result = await session.execute(stmt)
            row = result.scalars().first()
            if not row:
                return None

            try:
                decrypted_orig = self._crypto.decrypt(row.original_value)
            except Exception:
                decrypted_orig = original_value

            return TokenMapping(
                id=row.id,
                org_id=row.org_id,
                original_value=decrypted_orig,
                tokenized_value=row.tokenized_value,
                entity_type=row.entity_type,
                policy_applied=row.policy_applied,
                context_hash=row.context_hash or "",
                confidence=row.confidence,
                created_at=row.created_at,
                expires_at=row.expires_at,
                restored_at=row.restored_at,
                restored_by=row.restored_by,
            )

    async def get_all_for_org(self, org_id: str) -> List[TokenMapping]:
        async with get_db_session() as session:
            stmt = select(TokenMappingModel)
            if org_id and org_id != "all":
                stmt = stmt.where(TokenMappingModel.org_id == org_id)
            stmt = stmt.order_by(TokenMappingModel.created_at.desc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
            
            mappings = []
            for row in rows:
                try:
                    decrypted_orig = self._crypto.decrypt(row.original_value)
                except Exception:
                    decrypted_orig = row.original_value

                mappings.append(
                    TokenMapping(
                        id=row.id,
                        org_id=row.org_id,
                        original_value=decrypted_orig,
                        tokenized_value=row.tokenized_value,
                        entity_type=row.entity_type,
                        policy_applied=row.policy_applied,
                        context_hash=row.context_hash or "",
                        confidence=row.confidence,
                        created_at=row.created_at,
                        expires_at=row.expires_at,
                        restored_at=row.restored_at,
                        restored_by=row.restored_by,
                    )
                )
            return mappings

    async def update(self, mapping: TokenMapping) -> TokenMapping:
        async with get_db_session() as session:
            stmt = select(TokenMappingModel).where(TokenMappingModel.id == mapping.id)
            result = await session.execute(stmt)
            row = result.scalars().first()
            if row:
                row.restored_at = mapping.restored_at
                row.restored_by = mapping.restored_by
                row.expires_at = mapping.expires_at
                await session.flush()
        return mapping

    async def purge_expired(self, org_id: Optional[str] = None) -> int:
        now = datetime.now(timezone.utc)
        async with get_db_session() as session:
            stmt = delete(TokenMappingModel).where(
                TokenMappingModel.expires_at.isnot(None),
                TokenMappingModel.expires_at < now,
            )
            if org_id:
                stmt = stmt.where(TokenMappingModel.org_id == org_id)
            result = await session.execute(stmt)
            return result.rowcount or 0



class PostgresPolicyStore(PolicyStore):
    """PostgreSQL Policy Store managing per-tenant PII/PHI policies."""

    DEFAULT_POLICIES = [
        PIIPolicy(entity_type="PERSON", policy_type="anonymize", anonymize_strategy="randomized"),
        PIIPolicy(entity_type="EMAIL", policy_type="anonymize", anonymize_strategy="randomized"),
        PIIPolicy(entity_type="PHONE", policy_type="anonymize", anonymize_strategy="randomized"),
        PIIPolicy(entity_type="PHONE_NUMBER", policy_type="anonymize", anonymize_strategy="randomized"),
        PIIPolicy(entity_type="SSN", policy_type="redact"),
        PIIPolicy(entity_type="US_SSN", policy_type="redact"),
        PIIPolicy(entity_type="CREDIT_CARD", policy_type="redact"),
        PIIPolicy(entity_type="CREDIT_CARD_NUMBER", policy_type="redact"),
        PIIPolicy(entity_type="DATE", policy_type="anonymize", anonymize_strategy="alternate"),
        PIIPolicy(entity_type="ADDRESS", policy_type="anonymize", anonymize_strategy="randomized"),
        PIIPolicy(entity_type="LOCATION", policy_type="anonymize", anonymize_strategy="randomized"),
        PIIPolicy(entity_type="DRIVER_LICENSE", policy_type="redact"),
        PIIPolicy(entity_type="US_DRIVER_LICENSE", policy_type="redact"),
        PIIPolicy(entity_type="PASSPORT", policy_type="redact"),
        PIIPolicy(entity_type="US_PASSPORT", policy_type="redact"),
        PIIPolicy(entity_type="IP_ADDRESS", policy_type="redact"),
    ]

    def __init__(self):
        self._defaults = list(self.DEFAULT_POLICIES)

    def set_defaults(self, defaults: List[PIIPolicy]) -> None:
        self._defaults = defaults

    async def get_by_org(self, org_id: str) -> List[PIIPolicy]:
        async with get_db_session() as session:
            stmt = select(PolicyModel).where(PolicyModel.org_id == org_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            if not rows:
                return await self.get_defaults()
            return [
                PIIPolicy(
                    entity_type=row.entity_type,
                    policy_type=row.policy_type,
                    anonymize_strategy=row.anonymize_strategy,
                    custom_replacement=row.custom_replacement,
                )
                for row in rows
            ]

    async def upsert_many(self, org_id: str, policies: List[PIIPolicy]) -> List[PIIPolicy]:
        async with get_db_session() as session:
            for p in policies:
                stmt = select(PolicyModel).where(
                    PolicyModel.org_id == org_id,
                    PolicyModel.entity_type == p.entity_type,
                )
                result = await session.execute(stmt)
                existing = result.scalars().first()
                if existing:
                    existing.policy_type = p.policy_type
                    existing.anonymize_strategy = p.anonymize_strategy
                    existing.custom_replacement = p.custom_replacement
                else:
                    new_policy = PolicyModel(
                        org_id=org_id,
                        entity_type=p.entity_type,
                        policy_type=p.policy_type,
                        anonymize_strategy=p.anonymize_strategy,
                        custom_replacement=p.custom_replacement,
                    )
                    session.add(new_policy)
            await session.flush()
        return policies

    async def get_defaults(self) -> List[PIIPolicy]:
        return list(self._defaults)

    async def apply_preset(self, org_id: str, preset: str) -> List[PIIPolicy]:
        preset_enum = PolicyPreset(preset)
        policies = PRESETS.get(preset_enum, self._defaults)
        return await self.upsert_many(org_id, policies)


class PostgresAuditLog(AuditLog):
    """PostgreSQL Audit Log recording all token restoration & denial events."""

    async def log(self, entry: AuditEntry) -> None:
        meta = entry.metadata or {}
        mapping_id = meta.get("mapping_id")
        if isinstance(mapping_id, str):
            try:
                mapping_id = uuid.UUID(mapping_id)
            except Exception:
                mapping_id = None

        db_entry = AuditLogModel(
            id=entry.id if isinstance(entry.id, uuid.UUID) else uuid.UUID(str(entry.id)),
            org_id=entry.org_id or "default",
            mapping_id=mapping_id,
            tokenized_value=entry.tokenized_value or meta.get("tokenized_value"),
            entity_type=entry.entity_type or meta.get("entity_type"),
            action=entry.action,
            requester_id=entry.performed_by or meta.get("requester_id") or "system",
            ip_address=entry.ip_address or meta.get("ip_address") or "127.0.0.1",
            purpose=meta.get("purpose") or "api_call",
            reason=meta.get("reason"),
            status=meta.get("status") or "SUCCESS",
            created_at=entry.created_at or datetime.now(timezone.utc),
        )

        async with get_db_session() as session:
            session.add(db_entry)
            await session.flush()

    async def get_for_org(self, org_id: str, limit: int = 100) -> List[AuditEntry]:
        async with get_db_session() as session:
            stmt = select(AuditLogModel)
            if org_id and org_id != "all":
                stmt = stmt.where(AuditLogModel.org_id == org_id)
            stmt = stmt.order_by(AuditLogModel.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                AuditEntry(
                    id=r.id,
                    org_id=r.org_id,
                    action=r.action,
                    entity_type=r.entity_type,
                    tokenized_value=r.tokenized_value,
                    performed_by=r.requester_id,
                    ip_address=r.ip_address,
                    metadata={
                        "purpose": r.purpose,
                        "status": r.status,
                        "reason": r.reason,
                    },
                    created_at=r.created_at,
                )
                for r in rows
            ]


class PostgresOrgStore(OrgStore):
    """PostgreSQL Organization & Multi-Tenant Store."""

    async def list_orgs(self) -> List[OrgRecord]:
        async with get_db_session() as session:
            # 1. Fetch registered organizations
            stmt = select(OrgModel).order_by(OrgModel.created_at.asc())
            res = await session.execute(stmt)
            org_rows = res.scalars().all()
            org_map = {r.org_id: r for r in org_rows}

            # 2. Also fetch distinct org_ids from token_mappings to detect active tenants/patients (e.g. 203611)
            token_org_stmt = select(distinct(TokenMappingModel.org_id))
            token_res = await session.execute(token_org_stmt)
            token_org_ids = [row[0] for row in token_res.all() if row[0]]

            # Ensure default-org is present
            if "default-org" not in org_map and "default-org" not in token_org_ids:
                token_org_ids.insert(0, "default-org")

            results = []
            for org_id, r in org_map.items():
                results.append(
                    OrgRecord(
                        org_id=r.org_id,
                        name=r.name,
                        contact_email=r.contact_email or "admin@hekma.ai",
                        api_key_hash=r.api_key_hash,
                        raw_api_key_preview=r.raw_api_key_preview or "org_sk_live_••••••••••••••••",
                        audit_retention_days=r.audit_retention_days or 0,
                        token_ttl_days=r.token_ttl_days or 0,
                        settings_json=r.settings_json or "{}",
                        created_at=r.created_at,
                        updated_at=r.updated_at or r.created_at,
                    )
                )

            # Add discovered token orgs that aren't yet in organizations table
            for t_org_id in token_org_ids:
                if t_org_id not in org_map:
                    friendly_name = f"Patient / Tenant {t_org_id}" if t_org_id.isdigit() else t_org_id.replace("-", " ").title()
                    results.append(
                        OrgRecord(
                            org_id=t_org_id,
                            name=friendly_name,
                            contact_email="tenant@hekma.ai",
                            raw_api_key_preview="org_sk_live_••••••••••••••••",
                            audit_retention_days=0,
                            token_ttl_days=0,
                            settings_json="{}",
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc),
                        )
                    )

            return results

    async def get_org(self, org_id: str) -> OrgRecord:
        async with get_db_session() as session:
            stmt = select(OrgModel).where(OrgModel.org_id == org_id)
            res = await session.execute(stmt)
            r = res.scalars().first()
            if r:
                return OrgRecord(
                    org_id=r.org_id,
                    name=r.name,
                    contact_email=r.contact_email or "admin@hekma.ai",
                    api_key_hash=r.api_key_hash,
                    raw_api_key_preview=r.raw_api_key_preview or "org_sk_live_••••••••••••••••",
                    audit_retention_days=r.audit_retention_days or 0,
                    token_ttl_days=r.token_ttl_days or 0,
                    settings_json=r.settings_json or "{}",
                    created_at=r.created_at,
                    updated_at=r.updated_at or r.created_at,
                )

            # Create default organization profile on demand if not exists
            friendly_name = f"Patient / Tenant {org_id}" if org_id.isdigit() else (
                "Default Organization" if org_id == "default-org" else org_id.replace("-", " ").title()
            )
            new_org = OrgModel(
                org_id=org_id,
                name=friendly_name,
                contact_email="admin@hekma.ai",
                raw_api_key_preview="org_sk_live_••••••••••••••••",
                audit_retention_days=0,
                token_ttl_days=0,
                settings_json="{}",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(new_org)
            await session.flush()
            return OrgRecord(
                org_id=new_org.org_id,
                name=new_org.name,
                contact_email=new_org.contact_email,
                raw_api_key_preview=new_org.raw_api_key_preview,
                audit_retention_days=new_org.audit_retention_days,
                token_ttl_days=new_org.token_ttl_days,
                settings_json=new_org.settings_json,
                created_at=new_org.created_at,
                updated_at=new_org.updated_at,
            )

    async def save_org(self, org: OrgRecord) -> OrgRecord:
        async with get_db_session() as session:
            stmt = select(OrgModel).where(OrgModel.org_id == org.org_id)
            res = await session.execute(stmt)
            r = res.scalars().first()
            now = datetime.now(timezone.utc)
            if r:
                r.name = org.name
                r.contact_email = org.contact_email
                if org.raw_api_key_preview:
                    r.raw_api_key_preview = org.raw_api_key_preview
                if org.api_key_hash:
                    r.api_key_hash = org.api_key_hash
                r.audit_retention_days = org.audit_retention_days
                r.token_ttl_days = org.token_ttl_days
                r.settings_json = org.settings_json
                r.updated_at = now
                await session.flush()
            else:
                new_org = OrgModel(
                    org_id=org.org_id,
                    name=org.name,
                    contact_email=org.contact_email,
                    raw_api_key_preview=org.raw_api_key_preview or "org_sk_live_••••••••••••••••",
                    api_key_hash=org.api_key_hash,
                    audit_retention_days=org.audit_retention_days,
                    token_ttl_days=org.token_ttl_days,
                    settings_json=org.settings_json,
                    created_at=org.created_at or now,
                    updated_at=now,
                )
                session.add(new_org)
                await session.flush()
            return org

    async def rotate_key(self, org_id: str) -> tuple[OrgRecord, str]:
        import secrets
        import hashlib
        raw_key = f"org_sk_live_{secrets.token_urlsafe(24)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        preview = f"{raw_key[:16]}••••••••••••••••"

        org = await self.get_org(org_id)
        org.api_key_hash = key_hash
        org.raw_api_key_preview = preview
        await self.save_org(org)
        return org, raw_key

