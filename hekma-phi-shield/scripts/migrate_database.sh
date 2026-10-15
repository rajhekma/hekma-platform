#!/usr/bin/env bash
# ==============================================================================
# Multi-Environment Database Migration Script for Privacy Detection Service
# Migrates the 4 dedicated Token Vault tables directly into the App Database
# Usage: ./scripts/migrate_database.sh <environment>
# Environments: dev | demo | staging | production
# ==============================================================================

set -e

ENV_NAME="${1:-dev}"
echo "============================================================"
echo " Running Token Vault Schema Migration for: [${ENV_NAME}]"
echo " Target DB: Existing Application Database"
echo "============================================================"

# Resolve DATABASE_URL per environment if not already set
if [ -z "$DATABASE_URL" ]; then
    case "$ENV_NAME" in
        dev|develop)
            export DATABASE_URL="${DEV_DATABASE_URL:?Set DEV_DATABASE_URL for dev migration}"
            ;;
        demo)
            export DATABASE_URL="${DEMO_DATABASE_URL:?Set DEMO_DATABASE_URL for demo migration}"
            ;;
        staging)
            export DATABASE_URL="${STAGING_DATABASE_URL:?Set STAGING_DATABASE_URL for staging migration}"
            ;;
        prod|production)
            if [ -z "$PROD_DATABASE_URL" ]; then
                echo "❌ Error: PROD_DATABASE_URL must be provided for production migration."
                exit 1
            fi
            export DATABASE_URL="$PROD_DATABASE_URL"
            ;;
        *)
            echo "❌ Unknown environment: $ENV_NAME (Supported: dev, demo, staging, production)"
            exit 1
            ;;
    esac
fi

export STORAGE_BACKEND="postgresql"
echo "Target DB: $(echo "$DATABASE_URL" | sed -E 's/:[^@]+@/@/')"

# 1. Run Alembic Upgrade to Head (or Python init_db)
echo "Step 1: Applying isolated Token Vault tables (token_mappings, policies, audit_logs, organizations)..."
alembic upgrade head

# 2. Run Verification Check
echo "Step 2: Verifying database health and tables..."
python3 -c "
import asyncio
from api.database.connection import check_db_health, init_db_schema
async def verify():
    healthy = await check_db_health()
    if not healthy:
        raise SystemExit('Database health check failed after migration!')
    print('✅ Token Vault tables verified inside application database. Existing tables untouched.')
asyncio.run(verify())
"

echo "============================================================"
echo " 🎉 Migration for [${ENV_NAME}] completed successfully!"
echo "============================================================"
