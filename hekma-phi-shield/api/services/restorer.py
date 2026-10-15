from dataclasses import dataclass
from typing import Optional, Any
from datetime import datetime
import logging
import json

from api.services.token_store import token_store
from api.services.audit_log import audit_log

logger = logging.getLogger(__name__)


@dataclass
class RestoreRequest:
    tokenized_values: list[str]
    entity_types: Optional[list[str]] = None
    org_id: str = ""
    requester_id: str = ""
    ip_address: str = ""
    purpose: str = ""


@dataclass
class RestoreResult:
    original_value: str = ""
    tokenized_value: str = ""
    entity_type: str = ""
    restored: bool = False
    error: Optional[str] = None


ALLOWED_PURPOSES = {"trial_matching", "db_storage", "audit", "patient_care", "research"}


class Restorer:
    def __init__(self, token_store_svc=None, audit_log_svc=None):
        self.token_store = token_store_svc or token_store
        self.audit_log = audit_log_svc or audit_log

    async def restore(self, request: RestoreRequest) -> list[RestoreResult]:
        results = []

        for token in request.tokenized_values:
            mapping = await self.token_store.get_by_token(
                request.org_id, token, request.entity_types
            )

            if not mapping:
                results.append(RestoreResult(
                    tokenized_value=token,
                    restored=False,
                    error="Token not found"
                ))
                continue

            if not await self._authorize_restore(request, mapping):
                await self.audit_log.log_denied(
                    request.org_id, mapping, request.requester_id,
                    request.ip_address, request.purpose, "Unauthorized"
                )
                results.append(RestoreResult(
                    tokenized_value=token,
                    entity_type=mapping.entity_type,
                    restored=False,
                    error="Unauthorized"
                ))
                continue

            original = mapping.original_value

            mapping.restored_at = datetime.utcnow()
            mapping.restored_by = request.requester_id
            await self.token_store.update(mapping)

            await self.audit_log.log_restore(
                request.org_id, mapping, request.requester_id,
                request.ip_address, request.purpose
            )

            results.append(RestoreResult(
                original_value=original,
                tokenized_value=token,
                entity_type=mapping.entity_type,
                restored=True,
            ))

        return results

    async def _authorize_restore(self, request: RestoreRequest, mapping) -> bool:
        if request.purpose not in ALLOWED_PURPOSES:
            return False
        if mapping.expires_at and mapping.expires_at < datetime.utcnow():
            return False
        return True

    async def restore_in_text(
        self,
        text: str,
        org_id: str,
        requester_id: str,
        purpose: str,
        ip: str,
    ) -> str:
        mappings = await self.token_store.get_all_for_org(org_id)
        token_to_mapping = {m.tokenized_value: m for m in mappings}

        result = text
        for token, mapping in token_to_mapping.items():
            if token in result:
                restore_result = await self.restore(RestoreRequest(
                    tokenized_values=[token],
                    org_id=org_id,
                    requester_id=requester_id,
                    ip_address=ip,
                    purpose=purpose,
                ))
                if restore_result[0].restored:
                    result = result.replace(token, restore_result[0].original_value)

        return result

    async def restore_in_json(
        self,
        data: Any,
        org_id: str,
        requester_id: str,
        purpose: str,
        ip: str,
    ) -> Any:
        mappings = await self.token_store.get_all_for_org(org_id)
        token_to_mapping = {m.tokenized_value: m for m in mappings}

        async def restore_value(obj: Any) -> Any:
            if isinstance(obj, str):
                for token, mapping in token_to_mapping.items():
                    if token in obj:
                        restore_result = await self.restore(RestoreRequest(
                            tokenized_values=[token],
                            org_id=org_id,
                            requester_id=requester_id,
                            ip_address=ip,
                            purpose=purpose,
                        ))
                        if restore_result[0].restored:
                            obj = obj.replace(token, restore_result[0].original_value)
                return obj
            elif isinstance(obj, dict):
                return {k: await restore_value(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [await restore_value(v) for v in obj]
            return obj

        return await restore_value(data)


restorer = Restorer()