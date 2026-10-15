import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from api.models.policy import PIIPolicy
from api.storage.base import TokenMapping, AuditEntry
from api.storage.postgres import PostgresTokenStore, PostgresPolicyStore, PostgresAuditLog


@pytest.mark.asyncio
async def test_postgres_token_store_save_and_get():
    mock_session = AsyncMock()
    mock_row = MagicMock()
    mock_row.id = uuid.uuid4()
    mock_row.org_id = "test-org"
    mock_row.tokenized_value = "PAT_12345"
    mock_row.entity_type = "PERSON"
    mock_row.policy_applied = "anonymize"
    mock_row.context_hash = ""
    mock_row.confidence = 1.0
    mock_row.created_at = datetime.now(timezone.utc)
    mock_row.expires_at = None
    mock_row.restored_at = None
    mock_row.restored_by = None

    crypto_mock = MagicMock()
    crypto_mock.encrypt.return_value = "encrypted_val"
    crypto_mock.decrypt.return_value = "John Doe"
    crypto_mock.hash_plaintext.return_value = "hmac_hash_123"
    mock_row.original_value = "encrypted_val"

    store = PostgresTokenStore(crypto=crypto_mock)

    mapping = TokenMapping(
        org_id="test-org",
        original_value="John Doe",
        tokenized_value="PAT_12345",
        entity_type="PERSON",
        policy_applied="anonymize",
    )

    with patch("api.storage.postgres.get_db_session") as mock_db:
        mock_db.return_value.__aenter__.return_value = mock_session
        saved = await store.save(mapping)
        assert saved.tokenized_value == "PAT_12345"
        assert mock_session.add.called


@pytest.mark.asyncio
async def test_postgres_policy_store():
    store = PostgresPolicyStore()
    defaults = await store.get_defaults()
    assert len(defaults) > 0
    assert any(p.entity_type == "PERSON" for p in defaults)


@pytest.mark.asyncio
async def test_postgres_audit_log():
    mock_session = AsyncMock()
    store = PostgresAuditLog()

    entry = AuditEntry(
        org_id="test-org",
        action="RESTORE",
        performed_by="user-123",
        tokenized_value="PAT_12345",
        metadata={"purpose": "patient_care", "status": "SUCCESS"},
    )

    with patch("api.storage.postgres.get_db_session") as mock_db:
        mock_db.return_value.__aenter__.return_value = mock_session
        await store.log(entry)
        assert mock_session.add.called
