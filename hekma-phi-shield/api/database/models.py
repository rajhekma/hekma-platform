import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    DateTime,
    Text,
    Index,
    PrimaryKeyConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class TokenMappingModel(Base):
    __tablename__ = "token_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(String(128), nullable=False, index=True)
    original_value = Column(Text, nullable=False)  # Encrypted ciphertext
    original_hash = Column(String(64), nullable=False, index=True)  # HMAC hash for O(1) deduplication lookup
    tokenized_value = Column(String(256), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False, index=True)
    policy_applied = Column(String(64), nullable=False)
    context_hash = Column(String(64), nullable=True)
    confidence = Column(Float, nullable=False, default=1.0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    restored_at = Column(DateTime(timezone=True), nullable=True)
    restored_by = Column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_org_token", "org_id", "tokenized_value"),
        Index("ix_org_original_hash", "org_id", "original_hash"),
    )


class PolicyModel(Base):
    __tablename__ = "policies"

    org_id = Column(String(128), nullable=False)
    entity_type = Column(String(64), nullable=False)
    policy_type = Column(String(32), nullable=False)
    anonymize_strategy = Column(String(32), nullable=True)
    custom_replacement = Column(String(256), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        PrimaryKeyConstraint("org_id", "entity_type", name="pk_org_entity_policy"),
    )


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(String(128), nullable=False, index=True)
    mapping_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    tokenized_value = Column(String(256), nullable=True)
    entity_type = Column(String(64), nullable=True)
    action = Column(String(32), nullable=False)  # RESTORE, DENIED, CREATE, UPDATE
    requester_id = Column(String(128), nullable=False, index=True)
    ip_address = Column(String(64), nullable=False)
    purpose = Column(String(64), nullable=False)
    reason = Column(String(256), nullable=True)
    status = Column(String(32), nullable=False)  # SUCCESS, DENIED, ERROR
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class OrgModel(Base):
    __tablename__ = "organizations"

    org_id = Column(String(128), primary_key=True)
    name = Column(String(256), nullable=False)
    contact_email = Column(String(256), nullable=True)
    api_key_hash = Column(String(64), nullable=True)
    raw_api_key_preview = Column(String(128), nullable=True)
    audit_retention_days = Column(Integer, nullable=True, default=0)
    token_ttl_days = Column(Integer, nullable=True, default=0)
    settings_json = Column(Text, nullable=True, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
