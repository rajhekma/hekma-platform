import pytest
from api.middleware.policy_engine import PolicyEngine, PolicyContext
from api.models.policy import PIIPolicy, PolicyType, AnonymizeStrategy


@pytest.fixture
def policy_engine():
    return PolicyEngine()


@pytest.fixture(autouse=True)
def mock_policy_store_get_by_org(mocker):
    from api.services import policy_store
    async def mock_get_by_org(org_id: str):
        return policy_store._policies.get(org_id, policy_store._defaults.copy())
    mocker.patch.object(policy_store, "get_by_org", side_effect=mock_get_by_org)


@pytest.fixture
def sample_policies():
    return [
        PIIPolicy(entity_type="PERSON", policy_type=PolicyType.ANONYMIZE, anonymize_strategy=AnonymizeStrategy.RANDOMIZED),
        PIIPolicy(entity_type="EMAIL", policy_type=PolicyType.ANONYMIZE, anonymize_strategy=AnonymizeStrategy.RANDOMIZED),
        PIIPolicy(entity_type="SSN", policy_type=PolicyType.REDACT),
        PIIPolicy(entity_type="PHONE", policy_type=PolicyType.REDACT),
        PIIPolicy(entity_type="CREDIT_CARD", policy_type=PolicyType.REDACT),
    ]


@pytest.fixture
def internal_policies():
    return [
        PIIPolicy(entity_type="PERSON", policy_type=PolicyType.ANONYMIZE, anonymize_strategy=AnonymizeStrategy.RANDOMIZED, applies_to_internal=True, applies_to_external=False),
        PIIPolicy(entity_type="SSN", policy_type=PolicyType.REDACT, applies_to_internal=True, applies_to_external=True),
    ]


@pytest.mark.asyncio
async def test_get_policies_for_org_external(policy_engine, sample_policies):
    # Mock the policy_store
    from api.services import policy_store
    policy_store._policies["test-org"] = sample_policies
    
    context = PolicyContext(org_id="test-org", direction="external", path="/llm/generate")
    policies = await policy_engine.get_policies_for_org("test-org", context)
    
    assert len(policies) == 5


@pytest.mark.asyncio
async def test_get_policies_for_org_internal(policy_engine, sample_policies):
    from api.services import policy_store
    policy_store._policies["test-org"] = sample_policies
    
    context = PolicyContext(org_id="test-org", direction="internal", path="/internal/process")
    policies = await policy_engine.get_policies_for_org("test-org", context)
    
    assert len(policies) == 5


@pytest.mark.asyncio
async def test_filter_by_direction_external_only(policy_engine):
    policies = [
        PIIPolicy(entity_type="PERSON", policy_type=PolicyType.ANONYMIZE, applies_to_internal=False, applies_to_external=True),
        PIIPolicy(entity_type="SSN", policy_type=PolicyType.REDACT, applies_to_internal=True, applies_to_external=True),
    ]
    from api.services import policy_store
    policy_store._policies["test-org"] = policies
    
    context = PolicyContext(org_id="test-org", direction="external", path="/llm/generate")
    result = await policy_engine.get_policies_for_org("test-org", context)
    
    assert len(result) == 2  # Both apply to external


@pytest.mark.asyncio
async def test_filter_by_direction_internal_only(policy_engine):
    policies = [
        PIIPolicy(entity_type="PERSON", policy_type=PolicyType.ANONYMIZE, applies_to_internal=True, applies_to_external=False),
        PIIPolicy(entity_type="SSN", policy_type=PolicyType.REDACT, applies_to_internal=True, applies_to_external=True),
    ]
    from api.services import policy_store
    policy_store._policies["test-org"] = policies
    
    context = PolicyContext(org_id="test-org", direction="internal", path="/internal/process")
    result = await policy_engine.get_policies_for_org("test-org", context)
    
    assert len(result) == 2  # Both apply to internal


@pytest.mark.asyncio
async def test_filter_excludes_internal_only_for_external(policy_engine):
    policies = [
        PIIPolicy(entity_type="PERSON", policy_type=PolicyType.ANONYMIZE, applies_to_internal=True, applies_to_external=False),
        PIIPolicy(entity_type="SSN", policy_type=PolicyType.REDACT, applies_to_internal=True, applies_to_external=True),
    ]
    from api.services import policy_store
    policy_store._policies["test-org"] = policies
    
    context = PolicyContext(org_id="test-org", direction="external", path="/llm/generate")
    result = await policy_engine.get_policies_for_org("test-org", context)
    
    # PERSON should be filtered out (only applies to internal)
    assert len(result) == 1
    assert result[0].entity_type == "SSN"


@pytest.mark.asyncio
async def test_policy_cache_invalidation(policy_engine):
    # First call populates cache
    from api.services import policy_store
    policy_store._policies["test-org"] = [
        PIIPolicy(entity_type="PERSON", policy_type=PolicyType.ANONYMIZE),
    ]
    
    context = PolicyContext(org_id="test-org", direction="external", path="/llm/generate")
    await policy_engine.get_policies_for_org("test-org", context)
    
    # Add new policy
    policy_store._policies["test-org"].append(
        PIIPolicy(entity_type="EMAIL", policy_type=PolicyType.REDACT)
    )
    
    # Invalidate cache
    policy_engine.invalidate_cache("test-org")
    
    # Next call should get updated policies
    policies = await policy_engine.get_policies_for_org("test-org", context)
    assert len(policies) == 2


@pytest.mark.asyncio
async def test_context_hash_consistency(policy_engine):
    context1 = PolicyContext(
        org_id="test-org",
        direction="external",
        path="/llm/generate",
        user_id="user-123",
        request_id="req-456"
    )
    context2 = PolicyContext(
        org_id="test-org",
        direction="external",
        path="/llm/generate",
        user_id="user-123",
        request_id="req-456"
    )
    
    hash1 = policy_engine.build_context_hash(context1)
    hash2 = policy_engine.build_context_hash(context2)
    
    assert hash1 == hash2


@pytest.mark.asyncio
async def test_context_hash_differs_by_org(policy_engine):
    context1 = PolicyContext(org_id="org-1", direction="external", path="/llm/generate")
    context2 = PolicyContext(org_id="org-2", direction="external", path="/llm/generate")
    
    hash1 = policy_engine.build_context_hash(context1)
    hash2 = policy_engine.build_context_hash(context2)
    
    assert hash1 != hash2


@pytest.mark.asyncio
async def test_context_hash_differs_by_direction(policy_engine):
    context1 = PolicyContext(org_id="test-org", direction="external", path="/llm/generate")
    context2 = PolicyContext(org_id="test-org", direction="internal", path="/internal/process")
    
    hash1 = policy_engine.build_context_hash(context1)
    hash2 = policy_engine.build_context_hash(context2)
    
    assert hash1 != hash2