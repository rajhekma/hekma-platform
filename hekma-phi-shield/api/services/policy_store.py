from api.storage import get_policy_store
from api.models.policy import PRESETS, PolicyType, PIIPolicy

policy_store = get_policy_store()

DEFAULT_POLICIES = [
    PIIPolicy(entity_type=et, policy_type=pt) for et, pt in PRESETS.get("MINIMAL", {}).items()
]

policy_store.set_defaults(DEFAULT_POLICIES)