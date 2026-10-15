import pytest
import uuid
from datetime import datetime, timedelta
from api.services.restorer import Restorer, RestoreRequest, RestoreResult, ALLOWED_PURPOSES
from api.models.token_mapping import TokenMapping


class MockTokenStore:
    def __init__(self):
        self.data = {}
    
    async def get_by_token(self, org_id, token, entity_types=None):
        mapping = self.data.get(org_id, {}).get(token)
        if mapping and (not entity_types or mapping.entity_type in entity_types):
            return mapping
        return None
    
    async def get_all_for_org(self, org_id):
        return list(self.data.get(org_id, {}).values())
    
    async def update(self, mapping):
        if mapping.org_id not in self.data:
            self.data[mapping.org_id] = {}
        self.data[mapping.org_id][mapping.tokenized_value] = mapping
        return mapping


class MockAuditLog:
    def __init__(self):
        self.logs = []
    
    async def log_denied(self, org_id, mapping, requester_id, ip, purpose, reason):
        self.logs.append(("denied", org_id, mapping.tokenized_value, requester_id, purpose, reason))
    
    async def log_restore(self, org_id, mapping, requester_id, ip, purpose):
        self.logs.append(("restore", org_id, mapping.tokenized_value, requester_id, purpose))


@pytest.fixture
def token_store():
    return MockTokenStore()


@pytest.fixture
def audit_log():
    return MockAuditLog()


@pytest.fixture
def restorer(token_store, audit_log):
    return Restorer(token_store_svc=token_store, audit_log_svc=audit_log)


@pytest.fixture
def sample_mapping():
    return TokenMapping(
        id=uuid.uuid4(),
        org_id="test-org",
        original_value="John Doe",
        tokenized_value="PERSON_abc123",
        entity_type="PERSON",
        policy_applied="anonymize",
        context_hash="ctx_123",
        confidence=0.95,
        created_at=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_restore_valid_token(restorer, token_store, sample_mapping):
    token_store.data["test-org"] = {"PERSON_abc123": sample_mapping}
    
    request = RestoreRequest(
        tokenized_values=["PERSON_abc123"],
        org_id="test-org",
        requester_id="doctor-123",
        ip_address="192.168.1.1",
        purpose="patient_care",
    )
    
    results = await restorer.restore(request)
    
    assert len(results) == 1
    assert results[0].restored is True
    assert results[0].original_value == "John Doe"
    assert results[0].tokenized_value == "PERSON_abc123"
    assert results[0].entity_type == "PERSON"


@pytest.mark.asyncio
async def test_restore_token_not_found(restorer, token_store):
    request = RestoreRequest(
        tokenized_values=["PERSON_nonexistent"],
        org_id="test-org",
        requester_id="doctor-123",
        ip_address="192.168.1.1",
        purpose="patient_care",
    )
    
    results = await restorer.restore(request)
    
    assert len(results) == 1
    assert results[0].restored is False
    assert results[0].error == "Token not found"


@pytest.mark.asyncio
async def test_restore_unauthorized_purpose(restorer, token_store, sample_mapping):
    token_store.data["test-org"] = {"PERSON_abc123": sample_mapping}
    
    request = RestoreRequest(
        tokenized_values=["PERSON_abc123"],
        org_id="test-org",
        requester_id="doctor-123",
        ip_address="192.168.1.1",
        purpose="invalid_purpose",
    )
    
    results = await restorer.restore(request)
    
    assert len(results) == 1
    assert results[0].restored is False
    assert results[0].error == "Unauthorized"
    
    # Check audit log
    denied_logs = [log for log in restorer.audit_log.logs if log[0] == "denied"]
    assert len(denied_logs) == 1


@pytest.mark.asyncio
async def test_restore_expired_token(restorer, token_store):
    expired_mapping = TokenMapping(
        org_id="test-org",
        original_value="John Doe",
        tokenized_value="PERSON_expired",
        entity_type="PERSON",
        policy_applied="anonymize",
        context_hash="ctx_123",
        confidence=0.95,
        created_at=datetime.utcnow() - timedelta(days=10),
        expires_at=datetime.utcnow() - timedelta(days=1),  # Expired
    )
    token_store.data["test-org"] = {"PERSON_expired": expired_mapping}
    
    request = RestoreRequest(
        tokenized_values=["PERSON_expired"],
        org_id="test-org",
        requester_id="doctor-123",
        ip_address="192.168.1.1",
        purpose="patient_care",
    )
    
    results = await restorer.restore(request)
    
    assert len(results) == 1
    assert results[0].restored is False
    assert results[0].error == "Unauthorized"


@pytest.mark.asyncio
async def test_restore_updates_mapping(restorer, token_store, sample_mapping):
    token_store.data["test-org"] = {"PERSON_abc123": sample_mapping}
    
    request = RestoreRequest(
        tokenized_values=["PERSON_abc123"],
        org_id="test-org",
        requester_id="doctor-123",
        ip_address="192.168.1.1",
        purpose="patient_care",
    )
    
    await restorer.restore(request)
    
    updated = await token_store.get_by_token("test-org", "PERSON_abc123")
    assert updated.restored_at is not None
    assert updated.restored_by == "doctor-123"


@pytest.mark.asyncio
async def test_restore_logs_audit(restorer, token_store, sample_mapping):
    token_store.data["test-org"] = {"PERSON_abc123": sample_mapping}
    
    request = RestoreRequest(
        tokenized_values=["PERSON_abc123"],
        org_id="test-org",
        requester_id="doctor-123",
        ip_address="192.168.1.1",
        purpose="patient_care",
    )
    
    await restorer.restore(request)
    
    restore_logs = [log for log in restorer.audit_log.logs if log[0] == "restore"]
    assert len(restore_logs) == 1
    assert restore_logs[0][1] == "test-org"
    assert restore_logs[0][2] == "PERSON_abc123"
    assert restore_logs[0][3] == "doctor-123"
    assert restore_logs[0][4] == "patient_care"


@pytest.mark.asyncio
async def test_restore_multiple_tokens(restorer, token_store):
    mapping1 = TokenMapping(
        org_id="test-org",
        original_value="John Doe",
        tokenized_value="PERSON_abc123",
        entity_type="PERSON",
        policy_applied="anonymize",
        context_hash="ctx_123",
        confidence=0.95,
    )
    mapping2 = TokenMapping(
        org_id="test-org",
        original_value="jane@example.com",
        tokenized_value="EMAIL_xyz789",
        entity_type="EMAIL",
        policy_applied="anonymize",
        context_hash="ctx_123",
        confidence=0.95,
    )
    token_store.data["test-org"] = {
        "PERSON_abc123": mapping1,
        "EMAIL_xyz789": mapping2,
    }
    
    request = RestoreRequest(
        tokenized_values=["PERSON_abc123", "EMAIL_xyz789"],
        org_id="test-org",
        requester_id="doctor-123",
        ip_address="192.168.1.1",
        purpose="patient_care",
    )
    
    results = await restorer.restore(request)
    
    assert len(results) == 2
    assert all(r.restored for r in results)
    assert {r.original_value for r in results} == {"John Doe", "jane@example.com"}


@pytest.mark.asyncio
async def test_restore_with_entity_type_filter(restorer, token_store):
    mapping = TokenMapping(
        org_id="test-org",
        original_value="John Doe",
        tokenized_value="PERSON_abc123",
        entity_type="PERSON",
        policy_applied="anonymize",
        context_hash="ctx_123",
        confidence=0.95,
    )
    token_store.data["test-org"] = {"PERSON_abc123": mapping}
    
    # Filter by EMAIL should not find PERSON
    request = RestoreRequest(
        tokenized_values=["PERSON_abc123"],
        entity_types=["EMAIL"],
        org_id="test-org",
        requester_id="doctor-123",
        ip_address="192.168.1.1",
        purpose="patient_care",
    )
    
    results = await restorer.restore(request)
    
    assert len(results) == 1
    assert results[0].restored is False
    assert results[0].error == "Token not found"


@pytest.mark.asyncio
async def test_restore_in_text(restorer, token_store):
    mapping = TokenMapping(
        org_id="test-org",
        original_value="John Doe",
        tokenized_value="PERSON_abc123",
        entity_type="PERSON",
        policy_applied="anonymize",
        context_hash="ctx_123",
        confidence=0.95,
    )
    token_store.data["test-org"] = {"PERSON_abc123": mapping}
    
    text = "Patient PERSON_abc123 was admitted"
    result = await restorer.restore_in_text(
        text, "test-org", "doctor-123", "patient_care", "192.168.1.1"
    )
    
    assert "John Doe" in result
    assert "PERSON_abc123" not in result


@pytest.mark.asyncio
async def test_restore_in_json(restorer, token_store):
    mapping = TokenMapping(
        org_id="test-org",
        original_value="John Doe",
        tokenized_value="PERSON_abc123",
        entity_type="PERSON",
        policy_applied="anonymize",
        context_hash="ctx_123",
        confidence=0.95,
    )
    token_store.data["test-org"] = {"PERSON_abc123": mapping}
    
    data = {
        "patient": "PERSON_abc123",
        "details": {
            "name": "PERSON_abc123",
            "notes": "Patient PERSON_abc123 visited"
        }
    }
    
    result = await restorer.restore_in_json(
        data, "test-org", "doctor-123", "patient_care", "192.168.1.1"
    )
    
    assert result["patient"] == "John Doe"
    assert result["details"]["name"] == "John Doe"
    assert result["details"]["notes"] == "Patient John Doe visited"


@pytest.mark.asyncio
async def test_allowed_purposes(restorer):
    assert "trial_matching" in ALLOWED_PURPOSES
    assert "db_storage" in ALLOWED_PURPOSES
    assert "audit" in ALLOWED_PURPOSES
    assert "patient_care" in ALLOWED_PURPOSES
    assert "research" in ALLOWED_PURPOSES
    assert "unauthorized" not in ALLOWED_PURPOSES