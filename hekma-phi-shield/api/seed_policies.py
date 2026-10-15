import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.storage.base import PIIPolicy
from api.services.policy_store import policy_store

async def seed():
    # Define standard HIPAA protection policies for default-org
    policies = [
        PIIPolicy(
            entity_type="PERSON",
            policy_type="anonymize",
            anonymize_strategy="alternate", # Deterministic alternate name mapping
            applies_to_internal=True,
            applies_to_external=True
        ),
        PIIPolicy(
            entity_type="EMAIL_ADDRESS",
            policy_type="anonymize",
            anonymize_strategy="alternate",
            applies_to_internal=True,
            applies_to_external=True
        ),
        PIIPolicy(
            entity_type="PHONE_NUMBER",
            policy_type="redact",
            applies_to_internal=True,
            applies_to_external=True
        ),
        PIIPolicy(
            entity_type="US_SSN",
            policy_type="redact",
            applies_to_internal=True,
            applies_to_external=True
        ),
        PIIPolicy(
            entity_type="DATE",
            policy_type="anonymize",
            anonymize_strategy="randomized",
            applies_to_internal=True,
            applies_to_external=True
        )
    ]
    
    await policy_store.upsert_many("default-org", policies)
    print("Successfully seeded policies in data/policies.json!")

if __name__ == "__main__":
    asyncio.run(seed())
