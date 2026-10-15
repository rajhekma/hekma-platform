from datetime import datetime
from api.storage import get_audit_log
from api.models.token_mapping import TokenMapping


class AuditLogService:
    def __init__(self):
        self._log = get_audit_log()

    @property
    def log(self):
        return self._log

    async def log_tokenize(
        self,
        org_id: str,
        mapping: TokenMapping,
        performed_by: str,
        ip_address: str = "",
    ):
        from api.storage.base import AuditEntry
        entry = AuditEntry(
            org_id=org_id,
            action="tokenize",
            entity_type=mapping.entity_type,
            tokenized_value=mapping.tokenized_value,
            performed_by=performed_by,
            ip_address=ip_address,
            metadata={
                "policy_applied": mapping.policy_applied,
                "confidence": mapping.confidence,
                "context_hash": mapping.context_hash,
            },
        )
        await self._log.log(entry)

    async def log_restore(
        self,
        org_id: str,
        mapping: TokenMapping,
        performed_by: str,
        ip_address: str,
        purpose: str,
    ):
        from api.storage.base import AuditEntry
        entry = AuditEntry(
            org_id=org_id,
            action="restore",
            entity_type=mapping.entity_type,
            tokenized_value=mapping.tokenized_value,
            performed_by=performed_by,
            ip_address=ip_address,
            metadata={
                "purpose": purpose,
                "restored_at": datetime.utcnow().isoformat(),
            },
        )
        await self._log.log(entry)

    async def log_denied(
        self,
        org_id: str,
        mapping: TokenMapping,
        performed_by: str,
        ip_address: str,
        purpose: str,
        reason: str,
    ):
        from api.storage.base import AuditEntry
        entry = AuditEntry(
            org_id=org_id,
            action="restore_denied",
            entity_type=mapping.entity_type,
            tokenized_value=mapping.tokenized_value,
            performed_by=performed_by,
            ip_address=ip_address,
            metadata={
                "purpose": purpose,
                "reason": reason,
            },
        )
        await self._log.log(entry)

    async def log_policy_change(
        self,
        org_id: str,
        performed_by: str,
        ip_address: str,
        changes: dict,
    ):
        from api.storage.base import AuditEntry
        entry = AuditEntry(
            org_id=org_id,
            action="policy_change",
            performed_by=performed_by,
            ip_address=ip_address,
            metadata=changes,
        )
        await self._log.log(entry)

    async def get_for_org(self, org_id: str, limit: int = 100):
        return await self._log.get_for_org(org_id, limit)


audit_log = AuditLogService()