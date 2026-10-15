from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
import json
import uuid
import logging
from typing import Optional

from api.middleware.policy_engine import PolicyContext, policy_engine
from api.middleware.entity_detector import entity_detector
from api.services.token_store import token_store
from api.services.audit_log import audit_log
from api.services.anonymizer import anonymizer
from api.services.restorer import restorer
from api.config.settings import settings

logger = logging.getLogger(__name__)


class AnonymizationMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        excluded_paths: set[str] = None,
    ):
        super().__init__(app)
        self.excluded_paths = excluded_paths or settings.EXCLUDED_PATHS

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            path in self.excluded_paths
            or path.startswith("/admin")
            or path in {"/internal/restore", "/internal/restore-text"}
            or (path.startswith("/api/v1/") and path != "/api/v1/anonymize")
        ):
            return await call_next(request)

        if request.method == "GET" and not self._should_process_get(request):
            return await call_next(request)

        org_id = await self._extract_org_id(request)
        if not org_id:
            return await call_next(request)

        direction = self._determine_direction(request)

        body = await request.body()
        if not body:
            return await call_next(request)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return await call_next(request)

        processed_data, mappings = await self._process_request_data(
            data, org_id, direction, request
        )

        request.state.anonymization_mappings = mappings
        request.state.org_id = org_id

        # Replace the request body with processed data
        # We need to override the body method to return our processed data
        async def new_body():
            return json.dumps(processed_data).encode()
        
        request._body = json.dumps(processed_data).encode()
        # Also override the body method to ensure it returns our processed data
        request.body = new_body

        response = await call_next(request)

        if direction == "external" and self._should_process_response(response):
            response = await self._process_response(response, org_id, direction, request)

        return response

    async def _extract_org_id(self, request: Request) -> str | None:
        api_key = request.headers.get("x-api-key") or request.headers.get("authorization", "").replace("Bearer ", "")
        if api_key:
            return f"org-{hash(api_key) % 10000}"

        org_header = request.headers.get("x-org-id")
        if org_header:
            return org_header

        return "default-org"

    def _determine_direction(self, request: Request) -> str:
        path = request.url.path
        if "/llm/" in path or "/external/" in path or "external" in request.headers.get("x-direction", ""):
            return "external"
        return "internal"

    def _should_process_get(self, request: Request) -> bool:
        return False

    def _should_process_response(self, response: Response) -> bool:
        content_type = response.headers.get("content-type", "")
        return "application/json" in content_type

    async def _process_request_data(self, data: dict, org_id: str, direction: str, request: Request) -> tuple[dict, list]:
        mappings = []
        
        # Load existing policies once
        from api.services.policy_store import policy_store
        from api.models.policy import PIIPolicy, PolicyType, AnonymizeStrategy
        
        existing_policies = await policy_store.get_by_org(org_id)
        policy_map = {p.entity_type.upper(): p for p in existing_policies}
        updated_policies = list(existing_policies)

        # Check for preset override header
        preset_header = request.headers.get("x-policy-preset")
        use_preset_override = False
        preset_policies = {}
        
        if preset_header:
            from api.models.policy import PRESETS
            preset_name = preset_header.upper()
            if preset_name in ("REDACT_ALL", "ANONYMIZE_ALL") or preset_name in PRESETS:
                use_preset_override = True
                if preset_name in PRESETS:
                    preset_policies = {
                        et.upper(): PIIPolicy(
                            entity_type=et,
                            policy_type=pt,
                            anonymize_strategy=AnonymizeStrategy.RANDOMIZED,
                            applies_to_internal=True,
                            applies_to_external=True
                        )
                        for et, pt in PRESETS[preset_name].items()
                    }

        async def process_value(obj, path=""):
            if isinstance(obj, str):
                if len(obj) > 10000:
                    return obj
                entities = await entity_detector.detect(obj)
                
                if use_preset_override:
                    # Dynamically override policies in memory for all scanned entities
                    for ent in entities:
                        ent_type = ent.entity.upper()
                        if preset_header.upper() == "REDACT_ALL":
                            policy_map[ent_type] = PIIPolicy(
                                entity_type=ent.entity,
                                policy_type=PolicyType.REDACT,
                                anonymize_strategy=AnonymizeStrategy.RANDOMIZED,
                            )
                        elif preset_header.upper() == "ANONYMIZE_ALL":
                            policy_map[ent_type] = PIIPolicy(
                                entity_type=ent.entity,
                                policy_type=PolicyType.ANONYMIZE,
                                anonymize_strategy=AnonymizeStrategy.RANDOMIZED,
                            )
                        elif ent_type in preset_policies:
                            policy_map[ent_type] = preset_policies[ent_type]
                        else:
                            policy_map[ent_type] = PIIPolicy(
                                entity_type=ent.entity,
                                policy_type=PolicyType.IGNORE,
                                anonymize_strategy=AnonymizeStrategy.RANDOMIZED,
                            )
                else:
                    # Automatically check if any detected entity needs a non-ignore policy
                    need_save = False
                    for ent in entities:
                        ent_type = ent.entity.upper()
                        # If policy doesn't exist or is set to ignore, assign appropriate default
                        if ent_type not in policy_map or policy_map[ent_type].policy_type == PolicyType.IGNORE:
                            if ent_type in ("PERSON", "EMAIL", "EMAIL_ADDRESS", "ADDRESS", "COMPANY", "ORGANIZATION", "USERNAME"):
                                p_type = PolicyType.ANONYMIZE
                                strategy = AnonymizeStrategy.RANDOMIZED
                            else:
                                p_type = PolicyType.REDACT
                                strategy = AnonymizeStrategy.RANDOMIZED
                                
                            new_policy = PIIPolicy(
                                entity_type=ent.entity,
                                policy_type=p_type,
                                anonymize_strategy=strategy,
                                applies_to_internal=True,
                                applies_to_external=True
                            )
                            
                            # Remove existing ignore policy if present
                            if ent_type in policy_map:
                                updated_policies[:] = [p for p in updated_policies if p.entity_type.upper() != ent_type]
                                
                            updated_policies.append(new_policy)
                            policy_map[ent_type] = new_policy
                            need_save = True
                    
                    if need_save:
                        await policy_store.upsert_many(org_id, updated_policies)
                        policy_engine.invalidate_cache(org_id)

                context = PolicyContext(
                    org_id=org_id,
                    direction=direction,
                    path=request.url.path,
                    user_id=request.headers.get("x-user-id"),
                    request_id=str(uuid.uuid4())
                )
                context_hash = policy_engine.build_context_hash(context)
                
                if use_preset_override:
                    policies = list(policy_map.values())
                else:
                    policies = await policy_engine.get_policies_for_org(org_id, context)

                processed, entity_mappings = await anonymizer.apply(
                    obj, entities, policies, context_hash, token_store, org_id
                )
                mappings.extend(entity_mappings)

                for m in entity_mappings:
                    await audit_log.log_tokenize(
                        org_id=org_id,
                        mapping=m,
                        performed_by=context.user_id or "system",
                        ip_address=request.client.host if request.client else "unknown",
                    )

                return processed
            elif isinstance(obj, dict):
                return {k: await process_value(v, f"{path}.{k}") for k, v in obj.items()}
            elif isinstance(obj, list):
                return [await process_value(v, f"{path}[{i}]") for i, v in enumerate(obj)]
            return obj

        processed = await process_value(data)
        return processed, mappings

    async def _process_response(self, response: Response, org_id: str, direction: str, request: Request) -> Response:
        if not isinstance(response, JSONResponse):
            return response

        try:
            body = response.body
            if body:
                data = json.loads(body)
                requester_id = getattr(request.state, "user_id", "system")
                ip = request.client.host if request.client else "unknown"
                restored_data = await restorer.restore_in_json(
                    data, org_id, requester_id, "patient_care", ip
                )
                return JSONResponse(
                    content=restored_data,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
        except Exception as e:
            logger.warning(f"Failed to process response for restoration: {e}")

        return response


async def get_mappings(request: Request):
    return getattr(request.state, "anonymization_mappings", [])


async def get_org_id(request: Request):
    return getattr(request.state, "org_id", None)