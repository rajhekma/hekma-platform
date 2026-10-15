import os
import sys
import logging
import psycopg2
from psycopg2.extras import Json, execute_values
from dotenv import load_dotenv

# LOAD ENV
load_dotenv()

DEV_DB_CONFIG = {
    "host": os.getenv("PG_HOST"),
    "user": os.getenv("PG_USER"),
    "password": os.getenv("PG_PASSWORD"),
    "dbname": os.getenv("PG_DATABASE"),
    "port": os.getenv("PG_PORT", 5432),
}

DEMO_DB_CONFIG = {
    "host": os.getenv("DEMO_PG_HOST"),
    "user": os.getenv("DEMO_PG_USER"),
    "password": os.getenv("DEMO_PG_PASSWORD"),
    "dbname": os.getenv("DEMO_PG_DATABASE"),
    "port": os.getenv("DEMO_PG_PORT", 5432),
}

TABLES = ["compose", "trialgpt_corpus"]

# LOGGING
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

# VALIDATION
def validate_config():
    required = [
        "PG_HOST", "PG_USER", "PG_PASSWORD", "PG_DATABASE",
        "DEMO_PG_HOST", "DEMO_PG_USER", "DEMO_PG_PASSWORD", "DEMO_PG_DATABASE"
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        log.error(f"Missing env variables: {missing}")
        sys.exit(1)

# RESET SCHEMA FOR trialgpt_corpus (DROP + CREATE)
def reset_trialgpt_schema():
    conn = psycopg2.connect(**DEMO_DB_CONFIG)
    cursor = conn.cursor()

    log.info("Dropping and recreating trialgpt_corpus...")

    cursor.execute("""
    DROP TABLE IF EXISTS trialgpt_corpus;

    CREATE TABLE public.trialgpt_corpus (
        id uuid DEFAULT gen_random_uuid() NOT NULL,
        nct_id text NULL,
        title text NULL,
        "text" text NULL,
        inclusion_criteria jsonb NULL,
        exclusion_criteria jsonb NULL,
        source_type text NOT NULL,
        created_at timestamp DEFAULT now() NULL,
        updated_at timestamp DEFAULT now() NULL,
        min_age int4 NULL,
        max_age int4 NULL,
        sex varchar(20) NULL,
        locations jsonb NULL,
        countries jsonb NULL,
        diseases jsonb NULL,
        drugs jsonb NULL,
        phase text NULL,
        enrollment jsonb NULL,
        locations_detailed jsonb NULL,
        overall_status text NULL,
        raw_json jsonb NULL,
        start_date text NULL,
        completion_date text NULL,
        CONSTRAINT trialgpt_corpus_pkey PRIMARY KEY (id)
    );

    CREATE INDEX idx_trialgpt_corpus_source_type 
    ON public.trialgpt_corpus (source_type);

    CREATE INDEX idx_trialgpt_corpus_status 
    ON public.trialgpt_corpus (overall_status);

    CREATE INDEX idx_trialgpt_corpus_text_fts 
    ON public.trialgpt_corpus 
    USING gin (to_tsvector('english', text));

    CREATE UNIQUE INDEX uq_trialgpt_corpus_nctid 
    ON public.trialgpt_corpus (nct_id) 
    WHERE nct_id IS NOT NULL;
    """)

    conn.commit()
    cursor.close()
    conn.close()

# FETCH DATA FROM DEV
def fetch_data(table):
    conn = psycopg2.connect(**DEV_DB_CONFIG)
    cursor = conn.cursor()

    query = f"SELECT * FROM public.{table}"
    cursor.execute(query)

    columns = [desc[0] for desc in cursor.description]

    log.info(f"{table}: fetching data...")

    while True:
        rows = cursor.fetchmany(1000)
        if not rows:
            break
        yield rows, columns

    cursor.close()
    conn.close()

# INSERT INTO DEMO
def insert_data(table, data_generator):
    conn = psycopg2.connect(**DEMO_DB_CONFIG)
    cursor = conn.cursor()

    inserted = 0

    for rows, columns in data_generator:

        col_names = ", ".join(columns)

        
        if table == "compose":
            clean_rows = rows
        else:
            clean_rows = []
            for row in rows:
                new_row = []
                for val in row:
                    if isinstance(val, dict):
                        new_row.append(Json(val))  # only dict → jsonb
                    else:
                        new_row.append(val)
                clean_rows.append(tuple(new_row))

        execute_values(
            cursor,
            f"""
            INSERT INTO public.{table} ({col_names})
            VALUES %s
            """,
            clean_rows,
            page_size=1000
        )

        inserted += len(clean_rows)
        conn.commit()

        log.info(f"{table}: inserted={inserted}")

    cursor.close()
    conn.close()

    log.info(f"{table}: completed")

# MAIN
def main():
    validate_config()

    log.info("Starting migration...")

    # Step 1: Reset schema for corpus
    reset_trialgpt_schema()

    # Step 2: Copy data
    for table in TABLES:
        log.info(f"--- Processing {table} ---")
        data_gen = fetch_data(table)
        insert_data(table, data_gen)

    log.info("Migration completed successfully!")

if __name__ == "__main__":
    main()
