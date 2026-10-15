import pytest
from datetime import datetime
from api.services.anonymizer import Anonymizer, RedactStrategy, RandomizedStrategy, AlternateStrategy
from api.models.policy import PIIPolicy, PolicyType, AnonymizeStrategy
from api.models.token_mapping import TokenMapping


class MockTokenStore:
    def __init__(self):
        self.data = {}
    
    async def save(self, mapping):
        self.data[mapping.tokenized_value] = mapping
        return mapping


@pytest.fixture
def token_store():
    return MockTokenStore()


@pytest.fixture
def anonymizer():
    return Anonymizer()


@pytest.fixture
def sample_policies():
    return [
        PIIPolicy(entity_type="PERSON", policy_type=PolicyType.ANONYMIZE, anonymize_strategy=AnonymizeStrategy.RANDOMIZED),
        PIIPolicy(entity_type="EMAIL", policy_type=PolicyType.REDACT),
        PIIPolicy(entity_type="SSN", policy_type=PolicyType.REDACT),
        PIIPolicy(entity_type="PHONE", policy_type=PolicyType.REDACT),
        PIIPolicy(entity_type="CREDIT_CARD", policy_type=PolicyType.REDACT),
    ]


@pytest.fixture
def anonymize_email_policies():
    return [
        PIIPolicy(entity_type="EMAIL", policy_type=PolicyType.ANONYMIZE, anonymize_strategy=AnonymizeStrategy.RANDOMIZED),
    ]


class MockEntity:
    def __init__(self, entity, text, start, end, confidence=0.95):
        self.entity = entity
        self.text = text
        self.start = start
        self.end = end
        self.confidence = confidence


@pytest.mark.asyncio
async def test_redact_ssn(anonymizer, token_store, sample_policies):
    text = "My SSN is 123-45-6789"
    entities = [MockEntity("SSN", "123-45-6789", 11, 22)]
    context_hash = "ctx_123"
    
    result, mappings = await anonymizer.apply(text, entities, sample_policies, context_hash, token_store, "test-org")
    
    # SSN redaction keeps first digit: 1XX-XX-XXXX
    assert "1XX-XX-XXXX" in result
    assert "123-45-6789" not in result
    assert len(mappings) == 1
    assert mappings[0].entity_type == "SSN"
    assert mappings[0].policy_applied == "redact"


@pytest.mark.asyncio
async def test_redact_phone(anonymizer, token_store, sample_policies):
    text = "Call me at 555-123-4567"
    entities = [MockEntity("PHONE", "555-123-4567", 11, 23)]
    context_hash = "ctx_123"
    
    result, mappings = await anonymizer.apply(text, entities, sample_policies, context_hash, token_store, "test-org")
    
    assert "XXX-XXX-XXXX" in result
    assert "555-123-4567" not in result


@pytest.mark.asyncio
async def test_redact_email(anonymizer, token_store, sample_policies):
    text = "Email me at john@example.com"
    entities = [MockEntity("EMAIL", "john@example.com", 12, 28)]
    context_hash = "ctx_123"
    
    result, mappings = await anonymizer.apply(text, entities, sample_policies, context_hash, token_store, "test-org")
    
    assert "XXX@XXX.XXX" in result
    assert "john@example.com" not in result


@pytest.mark.asyncio
async def test_anonymize_person(anonymizer, token_store, sample_policies):
    text = "Patient John Doe visited"
    entities = [MockEntity("PERSON", "John Doe", 8, 16)]
    context_hash = "ctx_123"
    
    result, mappings = await anonymizer.apply(text, entities, sample_policies, context_hash, token_store, "test-org")
    
    assert "John Doe" not in result
    assert len(mappings) == 1
    assert mappings[0].entity_type == "PERSON"
    assert mappings[0].policy_applied == "anonymize"
    assert mappings[0].original_value == "John Doe"
    assert mappings[0].tokenized_value != "John Doe"


@pytest.mark.asyncio
async def test_anonymize_email_randomized(anonymizer, token_store, anonymize_email_policies):
    text = "Contact: alice@test.com"
    entities = [MockEntity("EMAIL", "alice@test.com", 9, 23)]
    context_hash = "ctx_123"
    
    result, mappings = await anonymizer.apply(text, entities, anonymize_email_policies, context_hash, token_store, "test-org")
    
    assert "alice@test.com" not in result
    assert "@" in result
    assert mappings[0].policy_applied == "anonymize"


@pytest.mark.asyncio
async def test_alternate_strategy_deterministic(anonymizer, token_store):
    policies = [
        PIIPolicy(entity_type="PERSON", policy_type=PolicyType.ANONYMIZE, anonymize_strategy=AnonymizeStrategy.ALTERNATE),
    ]
    text = "Patient John Doe and John Doe again"
    entities = [
        MockEntity("PERSON", "John Doe", 8, 16),
        MockEntity("PERSON", "John Doe", 21, 29),
    ]
    context_hash = "ctx_123"
    
    result, mappings = await anonymizer.apply(text, entities, policies, context_hash, token_store, "test-org")
    
    # Same original should map to same token
    tokens = [m.tokenized_value for m in mappings]
    assert tokens[0] == tokens[1]


@pytest.mark.asyncio
async def test_ignore_policy(anonymizer, token_store):
    policies = [
        PIIPolicy(entity_type="PERSON", policy_type=PolicyType.IGNORE),
    ]
    text = "Patient John Doe visited"
    entities = [MockEntity("PERSON", "John Doe", 8, 16)]
    context_hash = "ctx_123"
    
    result, mappings = await anonymizer.apply(text, entities, policies, context_hash, token_store, "test-org")
    
    assert "John Doe" in result  # Should not be modified
    assert len(mappings) == 0


@pytest.mark.asyncio
async def test_multiple_entities_sorted_by_position(anonymizer, token_store):
    policies = [
        PIIPolicy(entity_type="PERSON", policy_type=PolicyType.ANONYMIZE, anonymize_strategy=AnonymizeStrategy.RANDOMIZED),
        PIIPolicy(entity_type="EMAIL", policy_type=PolicyType.REDACT),
        PIIPolicy(entity_type="SSN", policy_type=PolicyType.REDACT),
    ]
    text = "John Doe has SSN 123-45-6789 and email john@example.com"
    entities = [
        MockEntity("PERSON", "John Doe", 0, 8),
        MockEntity("SSN", "123-45-6789", 17, 28),
        MockEntity("EMAIL", "john@example.com", 33, 49),
    ]
    context_hash = "ctx_123"
    
    result, mappings = await anonymizer.apply(text, entities, policies, context_hash, token_store, "test-org")
    
    assert "John Doe" not in result
    assert "XXX-XX-XXXX" in result
    assert "XXX@XXX.XXX" in result
    assert len(mappings) == 3


@pytest.mark.asyncio
async def test_redact_credit_card(anonymizer, token_store, sample_policies):
    text = "Card: 4111-1111-1111-1111"
    entities = [MockEntity("CREDIT_CARD", "4111-1111-1111-1111", 6, 25)]
    context_hash = "ctx_123"
    
    result, mappings = await anonymizer.apply(text, entities, sample_policies, context_hash, token_store, "test-org")
    
    assert "XXXX-XXXX-XXXX-XXXX" in result
    assert "4111-1111-1111-1111" not in result


@pytest.mark.asyncio
async def test_redact_custom_replacement(anonymizer, token_store):
    policies = [
        PIIPolicy(entity_type="PERSON", policy_type=PolicyType.REDACT, custom_replacement="[REDACTED]"),
    ]
    text = "Patient John Doe"
    entities = [MockEntity("PERSON", "John Doe", 8, 16)]
    context_hash = "ctx_123"
    
    result, mappings = await anonymizer.apply(text, entities, policies, context_hash, token_store, "test-org")
    
    assert "[REDACTED]" in result
    assert "John Doe" not in result


@pytest.mark.asyncio
async def test_mapping_stores_context_hash(anonymizer, token_store, sample_policies):
    text = "John Doe"
    entities = [MockEntity("PERSON", "John Doe", 0, 8)]
    context_hash = "ctx_hash_abc123"
    
    result, mappings = await anonymizer.apply(text, entities, sample_policies, context_hash, token_store, "test-org")
    
    assert mappings[0].context_hash == context_hash


@pytest.mark.asyncio
async def test_mapping_stores_confidence(anonymizer, token_store, sample_policies):
    text = "John Doe"
    entities = [MockEntity("PERSON", "John Doe", 0, 8, confidence=0.99)]
    context_hash = "ctx_123"
    
    result, mappings = await anonymizer.apply(text, entities, sample_policies, context_hash, token_store, "test-org")
    
    assert mappings[0].confidence == 0.99


@pytest.mark.asyncio
async def test_no_entities_returns_original(anonymizer, token_store, sample_policies):
    text = "No PII here"
    entities = []
    context_hash = "ctx_123"
    
    result, mappings = await anonymizer.apply(text, entities, sample_policies, context_hash, token_store, "test-org")
    
    assert result == text
    assert len(mappings) == 0