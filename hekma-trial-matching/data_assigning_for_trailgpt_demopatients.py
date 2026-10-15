import os
import sys
import logging
import mysql.connector
from dotenv import load_dotenv

load_dotenv()


DEMO_DB_CONFIG = {
    "host": os.getenv("DEMO_MYSQL_HOST"),
    "user": os.getenv("DEMO_MYSQL_USER"),
    "password": os.getenv("DEMO_MYSQL_PASSWORD"),
    "database": os.getenv("DEMO_MYSQL_DATABASE"),
}

TABLE_NAME = "Patient"

EMAIL_SUBJECT_MAP = {
    "fernandez@gmail.com": "c5b7ac7c-3399-910c-c774-32c4a1e5feeb",
    "ronaldo@gmail.com": "721ed73f-cb08-29a0-b6fb-60f7bdf73ee9",
    "tinapaul@gmail.com": "afc87c03-bae9-e2f3-fa78-d193fca97020",
    "rebecca@gmail.com": "a3d353a0-481c-734a-dcd5-9062cfdb2589",
    "damonsalvatore@gmail.com": "57fa027e-d54d-b6d6-6c7f-1243140b879b"
}

EMAIL_COLUMN = "email"
SUBJECT_COLUMN = "subjectId"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)


def validate_config():
    required = [
        "DEMO_MYSQL_HOST",
        "DEMO_MYSQL_USER",
        "DEMO_MYSQL_PASSWORD",
        "DEMO_MYSQL_DATABASE"
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        log.error(f"Missing env variables: {missing}")
        sys.exit(1)


def update_subject_ids():
    log.info("Connecting to DEMO DB...")
    conn = mysql.connector.connect(**DEMO_DB_CONFIG)
    cursor = conn.cursor()

    update_query = f"""
        UPDATE {TABLE_NAME}
        SET {SUBJECT_COLUMN} = %s,
            modifiedTs = NOW()
        WHERE {EMAIL_COLUMN} = %s
    """

    total_updated = 0

    try:
        log.info("Starting updates...")

        for email, subject_id in EMAIL_SUBJECT_MAP.items():
            cursor.execute(update_query, (str(subject_id), email))
            affected = cursor.rowcount

            if affected == 0:
                log.warning(f"No rows found for email: {email}")
            else:
                log.info(f"Updated {affected} row(s) for email: {email}")

            total_updated += affected

        conn.commit()

        log.info(f"Total rows updated: {total_updated}")

    except Exception as e:
        conn.rollback()
        log.error(f"Update failed: {e}")
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()

# MAIN

def main():
    validate_config()

    if not EMAIL_SUBJECT_MAP:
        log.warning("No mappings provided. Exiting.")
        return

    update_subject_ids()

    log.info("Patient table update completed successfully!")

if __name__ == "__main__":
    main()