import pytest
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from api.storage.memory import MemoryTokenStore, MemoryPolicyStore, MemoryAuditLog
from api.storage.base import TokenMapping, PIIPolicy, AuditEntry


@pytest.fixture
def encryption_key():
    return Fernet.generate_key()


@pytest.fixture
def token_store(encryption_key):
    return MemoryTokenStore(encryption_key)


@pytest.fixture
def policy_store():
    return MemoryPolicyStore()


@pytest.fixture
def audit_log():
    return MemoryAuditLog()


class TestMemoryTokenStore:
    @pytest.mark.asyncio
    async def test_save_and_retrieve(self, token_store):
        mapping = TokenMapping(
            org_id="test-org",
            original_value="John Doe",
            tokenized_value="PERSON_abc123",
            entity_type="PERSON",
            policy_applied="anonymize",
            context_hash="ctx_123",
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

    @pytest.mark.asyncio
    async def test_encryption_decryption(self, token_store):
        original = "sensitive-data-123"
        encrypted = token_store.encrypt(original)
        decrypted = token_store.decrypt(encrypted)
        
        assert encrypted != original
        assert decrypted == original

    @pytest.mark.asyncio
    async def test_get_all_for_org(self, token_store):
        mappings = [
            TokenMapping(
                org_id="test-org",
                original_value="John Doe",
                tokenized_value="PERSON_abc123",
                entity_type="PERSON",
                policy_applied="anonymize",
                context_hash="ctx_123",
                confidence=0.95,
            ),
            TokenMapping(
                org_id="test-org",
                original_value="jane@example.com",
                tokenized_value="EMAIL_xyz789",
                entity_type="EMAIL",
                policy_applied="anonymize",
                context_hash="ctx_123",
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
    async def test_update_mapping(self, token_store):
        mapping = TokenMapping(
            org_id="test-org",
            original_value="John Doe",
            tokenized_value="PERSON_abc123",
            entity_type="PERSON",
            policy_applied="anonymize",
            context_hash="ctx_123",
            confidence=0.95,
        )
        
        await token_store.save(mapping)
        
        # Update with restoration info
        mapping.original_value = "John Doe"  # Already decrypted
        mapping.restored_at = datetime.utcnow()
        mapping.restored_by = "admin-user"
        
        updated = await token_store.update(mapping)
        
        retrieved = await token_store.get_by_token("test-org", "PERSON_abc123")
        assert retrieved.restored_at is not None
        assert retrieved.restored_by == "admin-user"

    @pytest.mark.asyncio
    async def test_get_by_original(self, token_store):
        mapping = TokenMapping(
            org_id="test-org",
            original_value="John Doe",
            tokenized_value="PERSON_abc123",
            entity_type="PERSON",
            policy_applied="anonymize",
            context_hash="ctx_123",
            confidence=0.95,
        )
        
        await token_store.save(mapping)
        
        retrieved = await token_store.get_by_original("test-org", "John Doe")
        assert retrieved is not None
        assert retrieved.tokenized_value == "PERSON_abc123"
        assert retrieved.original_value == "John Doe"

    @pytest.mark.asyncio
    async def test_org_isolation(self, token_store):
        mapping1 = TokenMapping(
            org_id="org-1",
            original_value="John Doe",
            tokenized_value="PERSON_abc123",
            entity_type="PERSON",
            policy_applied="anonymize",
            context_hash="ctx_123",
            confidence=0.95,
        )
        mapping2 = TokenMapping(
            org_id="org-2",
            original_value="Jane Smith",
            tokenized_value="PERSON_xyz789",
            entity_type="PERSON",
            policy_applied="anonymize",
            context_hash="ctx_123",
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


class TestMemoryPolicyStore:
    @pytest.mark.asyncio
    async def test_upsert_and_get(self, policy_store):
        policies = [
            PIIPolicy(entity_type="PERSON", policy_type="anonymize"),
            PIIPolicy(entity_type="SSN", policy_type="redact"),
        ]
        
        result = await policy_store.upsert_many("test-org", policies)
        assert len(result) == 2
        
        retrieved = await policy_store.get_by_org("test-org")
        assert len(retrieved) == 2
        assert retrieved[0].entity_type == "PERSON"
        assert retrieved[0].policy_type == "anonymize"

    @pytest.mark.asyncio
    async def test_defaults(self, policy_store):
        defaults = [
            PIIPolicy(entity_type="PERSON", policy_type="anonymize"),
        ]
        policy_store.set_defaults(defaults)
        
        retrieved = await policy_store.get_defaults()
        assert len(retrieved) == 1
        assert retrieved[0].entity_type == "PERSON"

    @pytest.mark.asyncio
    async def test_apply_preset(self, policy_store):
        result = await policy_store.apply_preset("test-org", "HIPAA")
        assert len(result) > 0
        
        retrieved = await policy_store.get_by_org("test-org")
        assert len(retrieved) == len(result)


class TestMemoryAuditLog:
    @pytest.mark.asyncio
    async def test_log_and_retrieve(self, audit_log):
        entry = AuditEntry(
            org_id="test-org",
            action="tokenize",
            entity_type="PERSON",
            tokenized_value="PERSON_abc123",
            performed_by="system",
            ip_address="192.168.1.1",
            metadata={"path": "/llm/generate"},
        )
        
        await audit_log.log(entry)
        
        logs = await audit_log.get_for_org("test-org", limit=100)
        assert len(logs) == 1
        assert logs[0].action == "tokenize"
        assert logs[0].entity_type == "PERSON"

    @pytest.mark.asyncio
    async def test_limit(self, audit_log):
        for i in range(150):
            entry = AuditEntry(
                org_id="test-org",
                action="tokenize",
                performed_by="system",
                metadata={"index": i},
            )
            await audit_log.log(entry)
        
        logs = await audit_log.get_for_org("test-org", limit=100)
        assert len(logs) == 100
        # Should be most recent first
        assert logs[0].metadata["index"] == 149