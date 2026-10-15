import os
import logging
import psycopg2
from dotenv import load_dotenv
from io import StringIO

# LOAD ENV
load_dotenv()

DB_CONFIG = {
    "host": os.getenv("PG_HOST"),
    "user": os.getenv("PG_USER"),
    "password": os.getenv("PG_PASSWORD"),
    "dbname": os.getenv("PG_DB"),
    "port": os.getenv("PG_PORT", 5432),
}

TABLES = ["compose", "trialgpt_corpus"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)


# -------------------------------
# CREATE TABLE STRUCTURE (LIKE)
# -------------------------------
def create_test_table(conn, table):
    new_table = f"{table}_test"

    log.info(f"{table}: creating {new_table}...")

    cur = conn.cursor()

    cur.execute(f"DROP TABLE IF EXISTS public.{new_table} CASCADE;")

    # This copies structure INCLUDING constraints, defaults
    cur.execute(f"""
        CREATE TABLE public.{new_table}
        (LIKE public.{table} INCLUDING ALL);
    """)

    conn.commit()
    cur.close()

    log.info(f"{new_table}: structure created")


# -------------------------------
# COPY DATA
# -------------------------------
def copy_data(conn, table):
    new_table = f"{table}_test"

    log.info(f"{table}: copying data → {new_table}...")

    source_cur = conn.cursor()
    target_cur = conn.cursor()

    buffer = StringIO()

    # Extract data
    source_cur.copy_expert(
        f"COPY public.{table} TO STDOUT WITH CSV",
        buffer
    )

    buffer.seek(0)

    # Load data
    target_cur.copy_expert(
        f"COPY public.{new_table} FROM STDIN WITH CSV",
        buffer
    )

    conn.commit()

    source_cur.close()
    target_cur.close()

    log.info(f"{new_table}: data copied")


# -------------------------------
# MAIN
# -------------------------------
def main():
    log.info("Starting TEST migration (schema + data + indexes)...")

    conn = psycopg2.connect(**DB_CONFIG)

    for table in TABLES:
        log.info(f"--- Processing {table} ---")

        create_test_table(conn, table)
        copy_data(conn, table)

    conn.close()

    log.info("Test migration completed successfully ✅")


if __name__ == "__main__":
    main()