"""
Generate summary_text + 7-block structured_json for trialgpt_eligible_patients.

Flow:
  FHIR rows -> summary_builder.build_structured_json (rule-based)
            -> generate_summary (LLM) -> summary_text
            -> generate_block_summary_from_text (LLM) -> 7-block JSON
            -> UPDATE trialgpt_eligible_patients

Usage:
  python scripts/generate_eligible_patient_summaries.py --limit 10
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from repositories.postgres_repo import (
    get_latest_timestamp,
    get_patient_row,
    get_table_rows,
)
from services.patient_block_service import (
    attach_generation_metadata,
    generate_block_summary_from_text,
)
from services.summary_builder import build_structured_json
from services.summary_llm_service import generate_summary
from utils.llm_config import resolve_compose_llm_service, resolve_compose_model
from utils.pg_util import pg_transaction

DDL_PATH = PROJECT_ROOT / "migration" / "011_trialgpt_eligible_patients_summary.sql"

# Cap labs sent to the summary LLM to avoid huge token bills / timeouts.
MAX_OBSERVATIONS_FOR_LLM = 50


def ensure_summary_columns() -> None:
    ddl = DDL_PATH.read_text(encoding="utf-8")
    with pg_transaction() as (conn, cur):
        cur.execute(ddl)
        conn.commit()


def fetch_first_eligible(limit: int) -> list[str]:
    with pg_transaction() as (_, cur):
        cur.execute(
            """
            SELECT subject_id
            FROM trialgpt_eligible_patients
            ORDER BY subject_id
            LIMIT %s
            """,
            (limit,),
        )
        return [str(r["subject_id"]) for r in (cur.fetchall() or [])]


def _cap_observations(fhir_structured: dict, max_obs: int) -> dict:
    out = dict(fhir_structured)
    obs = out.get("observations") or []
    if isinstance(obs, list) and len(obs) > max_obs:
        # Prefer most recent-looking entries when date is present; else keep head.
        def _sort_key(item):
            if isinstance(item, dict):
                return str(item.get("date") or "")
            return ""

        sorted_obs = sorted(obs, key=_sort_key, reverse=True)
        out["observations"] = sorted_obs[:max_obs]
    return out


def process_one(subject_id: str, *, model: str, llm_service: str, max_obs: int) -> dict:
    latest_ts = get_latest_timestamp(subject_id)
    patient_row = get_patient_row(subject_id)
    if not patient_row:
        return {"subject_id": subject_id, "status": "no_pg_data"}

    fhir_structured = build_structured_json(
        patient_row,
        get_table_rows("condition", subject_id),
        get_table_rows("allergy", subject_id),
        get_table_rows("medication_order", subject_id),
        get_table_rows("immunization", subject_id),
        get_table_rows("procedure", subject_id),
        get_table_rows("observation", subject_id),
    )
    llm_input = _cap_observations(fhir_structured, max_obs)

    print(f"[{subject_id}] Generating summary_text...", flush=True)
    summary_text = generate_summary(
        llm_input,
        model=model,
        llm_service=llm_service,
    )

    print(f"[{subject_id}] Generating 7-block structured_json...", flush=True)
    block_json = generate_block_summary_from_text(
        subject_id,
        summary_text,
        model=model,
        llm_service=llm_service,
    )
    block_json = attach_generation_metadata(
        block_json,
        model=model,
        llm_service=llm_service,
        steps=["summary_builder", "summary_llm", "block_summary_from_summary"],
    )

    with pg_transaction() as (conn, cur):
        cur.execute(
            """
            UPDATE trialgpt_eligible_patients
            SET summary_text = %s,
                structured_json = %s::jsonb,
                last_data_timestamp = %s,
                last_generated_at = NOW(),
                summary_status = 'ready',
                updated_at = NOW()
            WHERE subject_id = %s
            """,
            (
                summary_text,
                json.dumps(block_json),
                latest_ts,
                subject_id,
            ),
        )
        conn.commit()

    return {
        "subject_id": subject_id,
        "status": "ready",
        "summary_chars": len(summary_text or ""),
        "block_keys": sorted(
            k for k in block_json.keys() if not str(k).startswith("_")
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate summary_text + 7-block JSON for eligible patients."
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--llm-service",
        default=None,
        choices=["claude", "openai"],
    )
    parser.add_argument(
        "--max-observations",
        type=int,
        default=MAX_OBSERVATIONS_FOR_LLM,
        help="Cap observations sent to summary LLM (default 50).",
    )
    parser.add_argument(
        "--output",
        default="results/eligible_summary_first10.json",
    )
    args = parser.parse_args()

    model = resolve_compose_model(args.model)
    llm_service = resolve_compose_llm_service(args.llm_service)

    ensure_summary_columns()
    ids = fetch_first_eligible(args.limit)
    print(f"Processing {len(ids)} patients model={model} llm={llm_service}", flush=True)

    results = []
    for subject_id in ids:
        try:
            result = process_one(
                subject_id,
                model=model,
                llm_service=llm_service,
                max_obs=args.max_observations,
            )
            print(json.dumps(result), flush=True)
            results.append(result)
        except Exception as exc:
            err = {
                "subject_id": subject_id,
                "status": "failed",
                "error": str(exc),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            print(json.dumps(err), flush=True)
            results.append(err)
            with pg_transaction() as (conn, cur):
                cur.execute(
                    """
                    UPDATE trialgpt_eligible_patients
                    SET summary_status = 'failed', updated_at = NOW()
                    WHERE subject_id = %s
                    """,
                    (subject_id,),
                )
                conn.commit()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model,
        "llm_service": llm_service,
        "limit": args.limit,
        "max_observations": args.max_observations,
        "results": results,
        "ready": sum(1 for r in results if r.get("status") == "ready"),
        "failed": sum(1 for r in results if r.get("status") == "failed"),
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("ready", "failed", "limit")}, indent=2))
    print(f"[done] wrote {out}", flush=True)
    return 0 if payload["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
