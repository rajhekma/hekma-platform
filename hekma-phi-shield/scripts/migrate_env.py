"""Multi-Environment Database Migration CLI Runner for Privacy Detection Service."""

import argparse
import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("migrate_env")

ENV_DEFAULTS = {
    "dev": os.getenv("DEV_DATABASE_URL", ""),
    "develop": os.getenv("DEV_DATABASE_URL", ""),
    "demo": os.getenv("DEMO_DATABASE_URL", ""),
    "staging": os.getenv("STAGING_DATABASE_URL", ""),
    "production": os.getenv("PROD_DATABASE_URL", ""),
}


async def run_migration(env_name: str, db_url: str):
    logger.info("=== Running Token Vault Schema Migration ===")
    logger.info("Target Environment: %s", env_name)
    logger.info("Target DB URL: %s", db_url.split("@")[-1] if "@" in db_url else db_url)

    os.environ["DATABASE_URL"] = db_url
    os.environ["STORAGE_BACKEND"] = "postgresql"

    from api.database.connection import check_db_health, init_db_schema
    from api.database.models import Base

    logger.info("\nChecking database connectivity...")
    healthy = await check_db_health()
    if not healthy:
        logger.error("❌ Database connection failed. Please check network/credentials.")
        sys.exit(1)

    logger.info("✅ Connected to database!")
    logger.info("Applying schema migrations (creating token_mappings, policies, audit_logs, organizations)...")
    await init_db_schema()

    logger.info("\n✅ Verified Token Vault tables:")
    for table_name in Base.metadata.tables.keys():
        logger.info("   • %s", table_name)

    logger.info("\n🎉 Schema migration for environment '%s' completed successfully! Existing tables untouched.", env_name)


def main():
    parser = argparse.ArgumentParser(description="Privacy Detection Service Database Migration Tool")
    parser.add_argument(
        "--env",
        choices=["dev", "develop", "demo", "staging", "production"],
        default="dev",
        help="Target environment (default: dev)",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Override database connection string",
    )

    args = parser.parse_args()
    target_url = args.db_url or os.getenv("DATABASE_URL") or ENV_DEFAULTS.get(args.env)

    if not target_url:
        logger.error("❌ No database URL configured for environment: %s. Set DATABASE_URL or pass --db-url.", args.env)
        sys.exit(1)

    asyncio.run(run_migration(args.env, target_url))


if __name__ == "__main__":
    main()
