"""Initial Token Vault Schema Migration

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-08-21 16:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create organizations table
    op.create_table(
        "organizations",
        sa.Column("org_id", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("api_key_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 2. Create policies table
    op.create_table(
        "policies",
        sa.Column("org_id", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("policy_type", sa.String(length=32), nullable=False),
        sa.Column("anonymize_strategy", sa.String(length=32), nullable=True),
        sa.Column("custom_replacement", sa.String(length=256), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("org_id", "entity_type", name="pk_org_entity_policy"),
    )

    # 3. Create token_mappings table
    op.create_table(
        "token_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(length=128), nullable=False),
        sa.Column("original_value", sa.Text(), nullable=False),
        sa.Column("original_hash", sa.String(length=64), nullable=False),
        sa.Column("tokenized_value", sa.String(length=256), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("policy_applied", sa.String(length=64), nullable=False),
        sa.Column("context_hash", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_by", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_token_mappings_org_id", "token_mappings", ["org_id"])
    op.create_index("ix_token_mappings_tokenized_value", "token_mappings", ["tokenized_value"])
    op.create_index("ix_token_mappings_entity_type", "token_mappings", ["entity_type"])
    op.create_index("ix_token_mappings_original_hash", "token_mappings", ["original_hash"])
    op.create_index("ix_token_mappings_created_at", "token_mappings", ["created_at"])
    op.create_index("ix_token_mappings_expires_at", "token_mappings", ["expires_at"])
    op.create_index("ix_org_token", "token_mappings", ["org_id", "tokenized_value"])
    op.create_index("ix_org_original_hash", "token_mappings", ["org_id", "original_hash"])

    # 4. Create audit_logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(length=128), nullable=False),
        sa.Column("mapping_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tokenized_value", sa.String(length=256), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("requester_id", sa.String(length=128), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_org_id", "audit_logs", ["org_id"])
    op.create_index("ix_audit_logs_mapping_id", "audit_logs", ["mapping_id"])
    op.create_index("ix_audit_logs_requester_id", "audit_logs", ["requester_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("token_mappings")
    op.drop_table("policies")
    op.drop_table("organizations")
