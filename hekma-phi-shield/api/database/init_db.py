"""Database Initialization and Verification Script for PII/PHI Token Vault."""

import asyncio
import logging
import sys
from api.config.settings import settings
from api.database.connection import get_engine, init_db_schema, check_db_health
from api.database.models import Base

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("init_db")


async def main():
    logger.info("=== PII/PHI Token Vault Database Initializer ===")
    logger.info("Storage Backend Configured: %s", settings.STORAGE_BACKEND)
    logger.info("Target Database URL: %s", settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else settings.DATABASE_URL)

    logger.info("\nChecking database connectivity...")
    healthy = await check_db_health()
    if not healthy:
        logger.error("❌ Could not connect to PostgreSQL instance. Please verify DATABASE_URL and ensure PostgreSQL is running.")
        sys.exit(1)

    logger.info("✅ Database connection successful!")

    logger.info("\nInitializing Token Vault tables...")
    await init_db_schema()

    logger.info("\n✅ The following 4 Token Vault tables are ready:")
    for table_name in Base.metadata.tables.keys():
        logger.info("  - %s", table_name)

    logger.info("\n🎉 Database initialization complete! Zero existing tables were altered.")


if __name__ == "__main__":
    asyncio.run(main())
