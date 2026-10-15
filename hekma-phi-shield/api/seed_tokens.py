import asyncio
from datetime import datetime, timedelta
import uuid
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.storage.base import TokenMapping
from api.services.token_store import token_store

async def seed():
    # Define mappings
    items = [
        TokenMapping(
            org_id="default-org",
            original_value="John Doe",
            tokenized_value="Albert Gibson",
            entity_type="PERSON",
            policy_applied="anonymize",
            context_hash="a1b2c3d4",
            confidence=0.98,
            created_at=datetime.utcnow() - timedelta(hours=2),
            expires_at=datetime.utcnow() + timedelta(days=30),
        ),
        TokenMapping(
            org_id="default-org",
            original_value="jane.smith@example.com",
            tokenized_value="kathryn.jones@hotmail.com",
            entity_type="EMAIL",
            policy_applied="anonymize",
            context_hash="b2c3d4e5",
            confidence=0.95,
            created_at=datetime.utcnow() - timedelta(hours=3),
            expires_at=datetime.utcnow() + timedelta(days=30),
        ),
        TokenMapping(
            org_id="default-org",
            original_value="123-456-7890",
            tokenized_value="XXX-XXX-XXXX",
            entity_type="PHONE",
            policy_applied="redact",
            context_hash="c3d4e5f6",
            confidence=0.88,
            created_at=datetime.utcnow() - timedelta(days=1),
            expires_at=datetime.utcnow() + timedelta(days=30),
        ),
        TokenMapping(
            org_id="default-org",
            original_value="666-29-9182",
            tokenized_value="XXX-XX-XXXX",
            entity_type="SSN",
            policy_applied="redact",
            context_hash="d4e5f6a1",
            confidence=0.99,
            created_at=datetime.utcnow() - timedelta(days=2),
            expires_at=datetime.utcnow() + timedelta(days=15),
        ),
        TokenMapping(
            org_id="default-org",
            original_value="1980-05-12",
            tokenized_value="1984-08-25",
            entity_type="DATE",
            policy_applied="anonymize",
            context_hash="e5f6a1b2",
            confidence=0.91,
            created_at=datetime.utcnow() - timedelta(days=5),
            expires_at=None,
        ),
        TokenMapping(
            org_id="default-org",
            original_value="4111-2222-3333-4444",
            tokenized_value="XXXX-XXXX-XXXX-XXXX",
            entity_type="CREDIT_CARD",
            policy_applied="redact",
            context_hash="f6a1b2c3",
            confidence=0.97,
            created_at=datetime.utcnow() - timedelta(days=7),
            expires_at=datetime.utcnow() + timedelta(days=90),
        ),
        TokenMapping(
            org_id="default-org",
            original_value="192.168.1.1",
            tokenized_value="74.125.19.14",
            entity_type="IP_ADDRESS",
            policy_applied="anonymize",
            context_hash="a1c2e3g4",
            confidence=0.85,
            created_at=datetime.utcnow() - timedelta(days=10),
            expires_at=None,
        )
    ]
    
    for item in items:
        # Note: save will automatically handle encryption of the original value
        await token_store.save(item)
    print("Successfully seeded database with mock token mappings!")

if __name__ == "__main__":
    asyncio.run(seed())
