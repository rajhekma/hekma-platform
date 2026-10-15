import argparse
import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values, Json
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from services.disease_list_util import (
    attach_icd_diseases_metadata,
    build_icd_official_disease_list,
    derive_disease_list_from_blocks,
)
from services.summary_llm_service import generate_disease_list
from services.patient_block_service import (
    attach_generation_metadata,
    generate_block_summary_from_text,
)
from utils.llm_config import (
    DEFAULT_COMPOSE_LLM_SERVICE,
    DEFAULT_COMPOSE_MODEL,
    resolve_compose_llm_service,
    resolve_compose_model,
)
from dataset.block_summary.paths import SINGLE_PATIENT_LOAD_JSON

DEFAULT_JSON_PATH = str(SINGLE_PATIENT_LOAD_JSON)
BATCH_SIZE = 500


def ensure_table_exists(conn):
    ddl_sql = """
        CREATE TABLE IF NOT EXISTS compose_summary_block (
            patient_id TEXT PRIMARY KEY,
            summary_text TEXT NOT NULL,
            structured_json JSONB NOT NULL,
            last_data_timestamp TIMESTAMP NOT NULL,
            last_generated_at TIMESTAMP DEFAULT NOW(),
            version INT DEFAULT 1,
            site_id TEXT NULL,
            disease_list TEXT[] NULL
        );

        CREATE INDEX IF NOT EXISTS idx_compose_summary_block_last_data_ts
        ON compose_summary_block (last_data_timestamp DESC);

        CREATE INDEX IF NOT EXISTS idx_compose_summary_block_last_generated_at
        ON compose_summary_block (last_generated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_compose_summary_block_structured_json
        ON compose_summary_block USING GIN (structured_json);
    """
    with conn.cursor() as cur:
        cur.execute(ddl_sql)
    conn.commit()


def get_connection():
    load_dotenv()

    pg_host = os.getenv("PG_HOST")
    pg_port = int(os.getenv("PG_PORT", "5432"))
    pg_db = os.getenv("PG_DB")
    pg_user = os.getenv("PG_USER")
    pg_password = os.getenv("PG_PASSWORD")

    missing = [
        name
        for name, value in {
            "PG_HOST": pg_host,
            "PG_DB": pg_db,
            "PG_USER": pg_user,
            "PG_PASSWORD": pg_password,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing PostgreSQL environment variables: {', '.join(missing)}"
        )

    return psycopg2.connect(
        host=pg_host,
        port=pg_port,
        dbname=pg_db,
        user=pg_user,
        password=pg_password,
    )


def load_records(
    json_path: Path,
    *,
    model: str,
    llm_service: str,
    skip_disease_llm: bool,
    use_file_blocks: bool,
    llm_disease_list: bool,
    skip_icd: bool,
):
    with json_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, list):
        raise ValueError("Input JSON must be an array of patient objects.")

    rows = []
    for index, item in enumerate(payload, start=1):
        patient_id = item.get("Patient_ID")
        summary_text = item.get("Patient_Summary")
        file_blocks = item.get("Patient_Block_Summary")
        structured_json = file_blocks

        if not patient_id or summary_text is None:
            raise ValueError(
                "Invalid JSON row at index "
                f"{index}: requires Patient_ID and Patient_Summary."
            )

        steps = []

        if not use_file_blocks or not structured_json:
            print(f"[{patient_id}] Generating block summary via {llm_service}/{model}...")
            structured_json = generate_block_summary_from_text(
                patient_id,
                summary_text,
                model=model,
                llm_service=llm_service,
            )
            steps.append("block_summary")
        else:
            steps.append("block_summary_from_file")

        structured_json = attach_generation_metadata(
            structured_json,
            model=model,
            llm_service=llm_service,
            steps=steps,
        )

        disease_list = []
        if skip_disease_llm:
            structured_json["_generation"]["steps"].append("disease_list_skipped")
        elif llm_disease_list:
            print(f"[{patient_id}] Extracting disease_list via {llm_service}/{model}...")
            disease_list = generate_disease_list(
                summary_text,
                structured_json,
                model=model,
                llm_service=llm_service,
            )
            structured_json["_generation"]["steps"].append("disease_list_llm")
        elif skip_icd:
            source_blocks = file_blocks if file_blocks else structured_json
            disease_list = derive_disease_list_from_blocks(source_blocks)
            structured_json["_generation"]["steps"].append("disease_list_raw")
        else:
            source_blocks = file_blocks if file_blocks else structured_json
            print(
                f"[{patient_id}] Mapping conditions to ICD-10-CM via "
                f"{llm_service}/{model}..."
            )
            disease_list, icd_entries = build_icd_official_disease_list(
                source_blocks,
                model=model,
                llm_service=llm_service,
                patient_context=summary_text,
            )
            structured_json = attach_icd_diseases_metadata(
                structured_json, icd_entries
            )
            structured_json["_generation"]["steps"].append("disease_list_icd10")
            for entry in icd_entries:
                print(
                    f"  {entry.get('input')} -> {entry.get('icd10_code')} "
                    f"{entry.get('official_name')}"
                )

        print(
            f"[{patient_id}] disease_list ({len(disease_list)}): {disease_list}"
        )

        rows.append((patient_id, summary_text, Json(structured_json), disease_list))
    return rows


def upsert_rows(conn, rows):
    upsert_sql = """
        INSERT INTO compose_summary_block (
            patient_id,
            summary_text,
            structured_json,
            disease_list,
            site_id,
            version,
            last_data_timestamp,
            last_generated_at
        )
        VALUES %s
        ON CONFLICT (patient_id)
        DO UPDATE SET
            summary_text = EXCLUDED.summary_text,
            structured_json = EXCLUDED.structured_json,
            disease_list = EXCLUDED.disease_list,
            site_id = EXCLUDED.site_id,
            version = compose_summary_block.version + 1,
            last_data_timestamp = NOW(),
            last_generated_at = NOW();
    """

    total = len(rows)
    with conn.cursor() as cur:
        for start in range(0, total, BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]
            values = [
                (pid, summary, block_json, disease_list, None, 1)
                for pid, summary, block_json, disease_list in batch
            ]
            execute_values(
                cur,
                upsert_sql,
                values,
                template="(%s, %s, %s, %s, %s, %s, NOW(), NOW())",
            )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Load patient rows into compose_summary_block using Claude "
            "(default claude-sonnet-4-6) for block summary and disease extraction."
        )
    )
    parser.add_argument(
        "--json-path",
        default=DEFAULT_JSON_PATH,
        help="Path to input JSON file (array of Patient_ID / Patient_Summary / Patient_Block_Summary).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_COMPOSE_MODEL,
        help=f"LLM model (default: {DEFAULT_COMPOSE_MODEL})",
    )
    parser.add_argument(
        "--llm-service",
        default=DEFAULT_COMPOSE_LLM_SERVICE,
        choices=["claude", "openai"],
        help=f"LLM provider (default: {DEFAULT_COMPOSE_LLM_SERVICE})",
    )
    parser.add_argument(
        "--skip-disease-llm",
        action="store_true",
        help="Leave disease_list empty.",
    )
    parser.add_argument(
        "--llm-disease-list",
        action="store_true",
        help="Extract disease_list with Claude from full summary (not ICD-10).",
    )
    parser.add_argument(
        "--skip-icd",
        action="store_true",
        help="Use raw condition phrases without ICD-10-CM normalization.",
    )
    parser.add_argument(
        "--use-file-blocks",
        action="store_true",
        help=(
            "Keep Patient_Block_Summary from JSON (no Claude block step). "
            "Default: regenerate blocks with Claude before load."
        ),
    )
    args = parser.parse_args()

    model = resolve_compose_model(args.model)
    llm_service = resolve_compose_llm_service(args.llm_service)

    json_path = Path(args.json_path)
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    rows = load_records(
        json_path,
        model=model,
        llm_service=llm_service,
        skip_disease_llm=args.skip_disease_llm,
        use_file_blocks=args.use_file_blocks,
        llm_disease_list=args.llm_disease_list,
        skip_icd=args.skip_icd,
    )
    conn = get_connection()
    try:
        ensure_table_exists(conn)
        upsert_rows(conn, rows)
    finally:
        conn.close()

    print(
        f"Loaded {len(rows)} record(s) into compose_summary_block "
        f"(model={model}, llm_service={llm_service})."
    )


if __name__ == "__main__":
    main()
