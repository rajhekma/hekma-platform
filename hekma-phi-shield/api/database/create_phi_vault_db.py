import asyncio
import logging
import os

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("create_phi_vault")

HOST = os.getenv("PG_HOST", "localhost")
PORT = int(os.getenv("PG_PORT", "5433"))
USER = os.getenv("PG_USER", "hekma")
PASSWORD = os.getenv("PG_PASSWORD", "")
TARGET_DB = "phi_vault"
DEFAULT_DB = "hekmaai"  # Or "postgres" to establish initial connection


async def create_database_if_not_exists():
    logger.info("Connecting to PostgreSQL server at %s:%d...", HOST, PORT)
    try:
        # Connect to default db first to check/create TARGET_DB
        conn = await asyncpg.connect(
            host=HOST,
            port=PORT,
            user=USER,
            password=PASSWORD,
            database=DEFAULT_DB,
            timeout=10,
        )
        logger.info("✅ Successfully connected to PostgreSQL server!")

        # Check if phi_vault database exists
        row = await conn.fetchrow(
            "SELECT 1 FROM pg_database WHERE datname = $1", TARGET_DB
        )
        if not row:
            logger.info("Database '%s' does not exist yet. Creating isolated database '%s'...", TARGET_DB, TARGET_DB)
            # Cannot execute CREATE DATABASE in transaction block
            await conn.execute(f'CREATE DATABASE "{TARGET_DB}"')
            logger.info("🎉 Isolated database '%s' created successfully!", TARGET_DB)
        else:
            logger.info("ℹ️ Database '%s' already exists.", TARGET_DB)

        await conn.close()

        # Now connect directly to the newly created phi_vault database to initialize its schema
        logger.info("Connecting directly to '%s' database to initialize tables...", TARGET_DB)
        vault_conn = await asyncpg.connect(
            host=HOST,
            port=PORT,
            user=USER,
            password=PASSWORD,
            database=TARGET_DB,
            timeout=10,
        )
        
        # Enable UUID extension in phi_vault
        await vault_conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

        # Create organizations table
        await vault_conn.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                org_id VARCHAR(128) PRIMARY KEY,
                name VARCHAR(256) NOT NULL,
                api_key_hash VARCHAR(64),
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create policies table
        await vault_conn.execute("""
            CREATE TABLE IF NOT EXISTS policies (
                org_id VARCHAR(128) NOT NULL,
                entity_type VARCHAR(64) NOT NULL,
                policy_type VARCHAR(32) NOT NULL,
                anonymize_strategy VARCHAR(32),
                custom_replacement VARCHAR(256),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT pk_org_entity_policy PRIMARY KEY (org_id, entity_type)
            )
        """)

        # Create token_mappings table
        await vault_conn.execute("""
            CREATE TABLE IF NOT EXISTS token_mappings (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                org_id VARCHAR(128) NOT NULL,
                original_value TEXT NOT NULL,
                original_hash VARCHAR(64) NOT NULL,
                tokenized_value VARCHAR(256) NOT NULL,
                entity_type VARCHAR(64) NOT NULL,
                policy_applied VARCHAR(64) NOT NULL,
                context_hash VARCHAR(64),
                confidence FLOAT NOT NULL DEFAULT 1.0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMPTZ,
                restored_at TIMESTAMPTZ,
                restored_by VARCHAR(128)
            )
        """)
        await vault_conn.execute('CREATE INDEX IF NOT EXISTS ix_token_mappings_org_id ON token_mappings (org_id)')
        await vault_conn.execute('CREATE INDEX IF NOT EXISTS ix_token_mappings_tokenized_value ON token_mappings (tokenized_value)')
        await vault_conn.execute('CREATE INDEX IF NOT EXISTS ix_token_mappings_original_hash ON token_mappings (original_hash)')
        await vault_conn.execute('CREATE INDEX IF NOT EXISTS ix_org_token ON token_mappings (org_id, tokenized_value)')
        await vault_conn.execute('CREATE INDEX IF NOT EXISTS ix_org_original_hash ON token_mappings (org_id, original_hash)')

        # Create audit_logs table
        await vault_conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                org_id VARCHAR(128) NOT NULL,
                mapping_id UUID,
                tokenized_value VARCHAR(256),
                entity_type VARCHAR(64),
                action VARCHAR(32) NOT NULL,
                requester_id VARCHAR(128) NOT NULL,
                ip_address VARCHAR(64) NOT NULL,
                purpose VARCHAR(64) NOT NULL,
                reason VARCHAR(256),
                status VARCHAR(32) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await vault_conn.execute('CREATE INDEX IF NOT EXISTS ix_audit_logs_org_id ON audit_logs (org_id)')
        await vault_conn.execute('CREATE INDEX IF NOT EXISTS ix_audit_logs_requester_id ON audit_logs (requester_id)')

        # List tables in phi_vault to verify
        tables = await vault_conn.fetch("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        logger.info("✅ Verified tables in database '%s':", TARGET_DB)
        for t in tables:
            logger.info("   • %s", t["table_name"])

        await vault_conn.close()
        logger.info("🎉 Isolated database '%s' initialized with 100% zero disturbance to 'hekmaai'!", TARGET_DB)
        return True

    except Exception as e:
        logger.error("❌ Failed to create/initialize database: %s", e)
        return False


if __name__ == "__main__":
    asyncio.run(create_database_if_not_exists())
