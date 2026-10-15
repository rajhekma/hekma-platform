import pytest
import uuid
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from api.storage.memory import MemoryTokenStore
from api.storage.base import TokenMapping


@pytest.fixture
def encryption_key():
    return Fernet.generate_key()


@pytest.fixture
def token_store(encryption_key):
    return MemoryTokenStore(encryption_key)


@pytest.mark.asyncio
async def test_save_and_get_by_token(token_store):
    mapping = TokenMapping(
        org_id="test-org",
        original_value="John Doe",
        tokenized_value="PERSON_abc123",
        entity_type="PERSON",
        policy_applied="anonymize",
        context_hash="ctx_hash_123",
        confidence=0.95,
    )
    
    saved = await token_store.save(mapping)
    assert saved.id is not None
    assert saved.created_at is not None
    
    retrieved = await token_store.get_by_token("test-org", "PERSON_abc123")
    assert retrieved is not None
    assert retrieved.original_value == "John Doe"
    assert retrieved.tokenized_value == "PERSON_abc123"
    assert retrieved.entity_type == "PERSON"
    assert retrieved.policy_applied == "anonymize"
    assert retrieved.confidence == 0.95


@pytest.mark.asyncio
async def test_get_by_token_with_entity_type_filter(token_store):
    mapping1 = TokenMapping(
        org_id="test-org",
        original_value="John Doe",
        tokenized_value="PERSON_abc123",
        entity_type="PERSON",
        policy_applied="anonymize",
        context_hash="ctx_hash_123",
        confidence=0.95,
    )
    mapping2 = TokenMapping(
        org_id="test-org",
        original_value="jane@example.com",
        tokenized_value="EMAIL_xyz789",
        entity_type="EMAIL",
        policy_applied="anonymize",
        context_hash="ctx_hash_123",
        confidence=0.95,
    )
    
    await token_store.save(mapping1)
    await token_store.save(mapping2)
    
    # Filter by PERSON
    result = await token_store.get_by_token("test-org", "PERSON_abc123", entity_types=["PERSON"])
    assert result is not None
    assert result.entity_type == "PERSON"
    
    # Filter by EMAIL (should not find PERSON)
    result = await token_store.get_by_token("test-org", "PERSON_abc123", entity_types=["EMAIL"])
    assert result is None


@pytest.mark.asyncio
async def test_get_all_for_org(token_store):
    mappings = [
        TokenMapping(
            org_id="test-org",
            original_value="John Doe",
            tokenized_value="PERSON_abc123",
            entity_type="PERSON",
            policy_applied="anonymize",
            context_hash="ctx_hash_123",
            confidence=0.95,
        ),
        TokenMapping(
            org_id="test-org",
            original_value="jane@example.com",
            tokenized_value="EMAIL_xyz789",
            entity_type="EMAIL",
            policy_applied="anonymize",
            context_hash="ctx_hash_123",
            confidence=0.95,
        ),
    ]
    
    for m in mappings:
        await token_store.save(m)
    
    all_mappings = await token_store.get_all_for_org("test-org")
    assert len(all_mappings) == 2
    assert all_mappings[0].original_value == "John Doe"
    assert all_mappings[1].original_value == "jane@example.com"


@pytest.mark.asyncio
async def test_update_token_mapping(token_store):
    mapping = TokenMapping(
        org_id="test-org",
        original_value="John Doe",
        tokenized_value="PERSON_abc123",
        entity_type="PERSON",
        policy_applied="anonymize",
        context_hash="ctx_hash_123",
        confidence=0.95,
    )
    
    await token_store.save(mapping)
    
    # Update with new original value
    mapping.original_value = "Jane Smith"
    mapping.restored_at = datetime.utcnow()
    mapping.restored_by = "admin-user"
    
    updated = await token_store.update(mapping)
    
    retrieved = await token_store.get_by_token("test-org", "PERSON_abc123")
    assert retrieved.original_value == "Jane Smith"
    assert retrieved.restored_at is not None
    assert retrieved.restored_by == "admin-user"


@pytest.mark.asyncio
async def test_encrypt_decrypt(token_store):
    original = "test-value-123"
    encrypted = token_store.encrypt(original)
    decrypted = token_store.decrypt(encrypted)
    
    assert encrypted != original
    assert decrypted == original


@pytest.mark.asyncio
async def test_get_by_original(token_store):
    mapping = TokenMapping(
        org_id="test-org",
        original_value="John Doe",
        tokenized_value="PERSON_abc123",
        entity_type="PERSON",
        policy_applied="anonymize",
        context_hash="ctx_hash_123",
        confidence=0.95,
    )
    
    await token_store.save(mapping)
    
    retrieved = await token_store.get_by_original("test-org", "John Doe")
    assert retrieved is not None
    assert retrieved.tokenized_value == "PERSON_abc123"
    assert retrieved.original_value == "John Doe"


@pytest.mark.asyncio
async def test_isolation_between_orgs(token_store):
    mapping1 = TokenMapping(
        org_id="org-1",
        original_value="John Doe",
        tokenized_value="PERSON_abc123",
        entity_type="PERSON",
        policy_applied="anonymize",
        context_hash="ctx_hash_123",
        confidence=0.95,
    )
    mapping2 = TokenMapping(
        org_id="org-2",
        original_value="Jane Smith",
        tokenized_value="PERSON_xyz789",
        entity_type="PERSON",
        policy_applied="anonymize",
        context_hash="ctx_hash_123",
        confidence=0.95,
    )
    
    await token_store.save(mapping1)
    await token_store.save(mapping2)
    
    org1_mappings = await token_store.get_all_for_org("org-1")
    org2_mappings = await token_store.get_all_for_org("org-2")
    
    assert len(org1_mappings) == 1
    assert len(org2_mappings) == 1
    assert org1_mappings[0].original_value == "John Doe"
    assert org2_mappings[0].original_value == "Jane Smith"


@pytest.mark.asyncio
async def test_expiration_support(token_store):
    from datetime import timedelta
    mapping = TokenMapping(
        org_id="test-org",
        original_value="John Doe",
        tokenized_value="PERSON_abc123",
        entity_type="PERSON",
        policy_applied="anonymize",
        context_hash="ctx_hash_123",
        confidence=0.95,
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    
    await token_store.save(mapping)
    retrieved = await token_store.get_by_token("test-org", "PERSON_abc123")
    assert retrieved.expires_at is not None