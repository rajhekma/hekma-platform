import time
from pydantic import BaseModel
from typing import Literal, Optional, List
import hashlib
import logging

from api.services.policy_store import policy_store
from api.models.policy import PIIPolicy

logger = logging.getLogger(__name__)


class PolicyContext(BaseModel):
    org_id: str
    direction: Literal["internal", "external"]
    path: str
    user_id: Optional[str] = None
    request_id: str = ""


class PolicyEngine:
    def __init__(self):
        self._cache: dict[str, tuple[float, List[PIIPolicy]]] = {}
        self._cache_ttl = 60

    async def get_policies_for_org(self, org_id: str, context: PolicyContext) -> List[PIIPolicy]:
        cache_key = f"{org_id}:{context.direction}"
        now = time.time()
        if cache_key in self._cache:
            ts, val = self._cache[cache_key]
            if now - ts < self._cache_ttl:
                return val

        policies = await policy_store.get_by_org(org_id)
        filtered = [
            p for p in policies
            if (context.direction == "external" and p.applies_to_external) or
               (context.direction == "internal" and p.applies_to_internal)
        ]
        self._cache[cache_key] = (now, filtered)
        return filtered

    def should_process(self, entity_type: str, policies: List[PIIPolicy]) -> Optional[PIIPolicy]:
        for policy in policies:
            if policy.entity_type.upper() == entity_type.upper():
                return policy if policy.policy_type != "ignore" else None
        return None

    def build_context_hash(self, context: PolicyContext) -> str:
        data = f"{context.org_id}:{context.direction}:{context.path}:{context.user_id or ''}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def invalidate_cache(self, org_id: str, direction: str = None):
        if direction:
            self._cache.pop(f"{org_id}:{direction}", None)
        else:
            keys = [k for k in self._cache if k.startswith(f"{org_id}:")]
            for k in keys:
                self._cache.pop(k, None)


policy_engine = PolicyEngine()