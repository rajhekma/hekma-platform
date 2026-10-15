import os
import subprocess
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger(__name__)

DEV = {
    "host": os.getenv("PG_HOST"),
    "user": os.getenv("PG_USER"),
    "db": os.getenv("PG_DATABASE"),
    "port": os.getenv("PG_PORT", "5432"),
    "password": os.getenv("PG_PASSWORD"),
}

DEMO = {
    "host": os.getenv("DEMO_PG_HOST"),
    "user": os.getenv("DEMO_PG_USER"),
    "db": os.getenv("DEMO_PG_DATABASE"),
    "port": os.getenv("DEMO_PG_PORT", "5432"),
    "password": os.getenv("DEMO_PG_PASSWORD"),
}

TABLES = ["public.compose", "public.trialgpt_corpus"]

def validate_env():
    required = [
        "PG_HOST", "PG_USER", "PG_PASSWORD", "PG_DATABASE",
        "DEMO_PG_HOST", "DEMO_PG_USER", "DEMO_PG_PASSWORD", "DEMO_PG_DATABASE"
    ]
    missing = [k for k in required if not os.getenv(k)]

    if missing:
        raise Exception(f"Missing env variables: {missing}")

DDL_SQL = """
BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP TABLE IF EXISTS public.trialgpt_corpus CASCADE;
DROP TABLE IF EXISTS public.compose CASCADE;

-- trialgpt_corpus
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
USING gin (to_tsvector('english', "text"));

CREATE UNIQUE INDEX uq_trialgpt_corpus_nctid 
ON public.trialgpt_corpus (nct_id) 
WHERE nct_id IS NOT NULL;

-- compose
CREATE TABLE public.compose (
    patient_id text NOT NULL,
    summary_text text NOT NULL,
    structured_json jsonb NOT NULL,
    last_data_timestamp timestamp without time zone NOT NULL,
    last_generated_at timestamp without time zone DEFAULT now(),
    version integer DEFAULT 1,
    site_id character varying(50),
    disease_list text[],
    CONSTRAINT compose_pkey PRIMARY KEY (patient_id)
);

COMMIT;
"""

def run_command(cmd, env):
    log.info("Running: " + " ".join(cmd))

    result = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        log.error(result.stderr)
        raise Exception("Command failed")

    if result.stdout:
        log.info(result.stdout)

def apply_schema():
    log.info("Applying schema to DEMO...")

    cmd = [
        "psql",
        "-h", DEMO["host"],
        "-U", DEMO["user"],
        "-d", DEMO["db"],
        "-p", DEMO["port"],
        "-c", DDL_SQL
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = DEMO["password"]

    run_command(cmd, env)

def dump_and_load():
    log.info("Streaming data from DEV → DEMO...")

    dump_cmd = [
        "pg_dump",
        "-h", DEV["host"],
        "-U", DEV["user"],
        "-d", DEV["db"],
        "-p", DEV["port"],
        "--data-only",
        "--no-owner",
        "--no-privileges",
    ]

    for table in TABLES:
        dump_cmd.extend(["--table", table])

    load_cmd = [
        "psql",
        "-h", DEMO["host"],
        "-U", DEMO["user"],
        "-d", DEMO["db"],
        "-p", DEMO["port"],
    ]

    env_dump = os.environ.copy()
    env_dump["PGPASSWORD"] = DEV["password"]

    env_load = os.environ.copy()
    env_load["PGPASSWORD"] = DEMO["password"]

    dump_proc = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE, env=env_dump)
    load_proc = subprocess.Popen(load_cmd, stdin=dump_proc.stdout, env=env_load)

    dump_proc.stdout.close()
    load_proc.communicate()

    if load_proc.returncode != 0:
        raise Exception("Streaming migration failed")

# MAIN
def main():
    log.info("===== STARTING MIGRATION =====")

    validate_env()

    apply_schema()     # Step 1: Drop + Create
    dump_and_load()    # Step 2: Data migration

    log.info("===== MIGRATION COMPLETED SUCCESSFULLY =====")

if __name__ == "__main__":
    main()