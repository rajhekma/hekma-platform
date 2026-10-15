"""
Smoke checks for the coverage-first summarize/embed pipeline (no full LLM backfill).

Usage:
  python scripts/verify_patient_summary_pipeline.py
  python scripts/verify_patient_summary_pipeline.py --coverage-limit 200
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify patient summary/embed pipeline wiring.")
    parser.add_argument("--coverage-limit", type=int, default=200)
    parser.add_argument("--skip-coverage", action="store_true")
    parser.add_argument("--skip-qdrant", action="store_true")
    args = parser.parse_args()

    results = []

    # Import / wiring checks
    try:
        from repositories.compose_repo import (
            count_compose_summary_block,
            upsert_compose_summary_block,
            get_compose_summary_block_timestamp,
        )
        from services.patient_summary_batch_service import process_patient_summary, run_summary_shard
        from services.patient_qdrant_embed_service import embed_from_compose
        from services.patient_summary_coverage_service import build_coverage_report
        from services.summary_resfresh_service import refresh_summaries

        assert callable(upsert_compose_summary_block)
        assert callable(get_compose_summary_block_timestamp)
        assert callable(process_patient_summary)
        assert callable(run_summary_shard)
        assert callable(embed_from_compose)
        assert callable(refresh_summaries)
        results.append({"check": "imports", "ok": True})
    except Exception as exc:
        results.append({"check": "imports", "ok": False, "detail": str(exc)})
        print(json.dumps({"results": results}, indent=2))
        return 1

    if not args.skip_coverage:
        try:
            report = build_coverage_report(limit=args.coverage_limit if args.coverage_limit > 0 else None)
            compose_n = count_compose_summary_block()
            results.append(
                {
                    "check": "coverage",
                    "ok": True,
                    "detail": {
                        "mysql_with_subject": report.get("mysql_with_subject"),
                        "scanned": report.get("scanned"),
                        "with_pg_clinical": report.get("with_pg_clinical"),
                        "eligible_to_generate": report.get("eligible_to_generate"),
                        "no_pg_data": report.get("no_pg_data"),
                        "compose_summary_block_total_rows": compose_n,
                    },
                }
            )
            out = Path("results/patient_summary_coverage_smoke.json")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            results.append({"check": "coverage", "ok": False, "detail": str(exc)})

    if not args.skip_qdrant:
        try:
            from utils.qdrant_util import get_qdrant_client
            import os

            client = get_qdrant_client()
            pc = os.getenv("QDRANT_PATIENT_COLLECTION", "patient_profiles_hybrid_v1")
            tc = os.getenv("QDRANT_TRIAL_COLLECTION", "clinical_trials_hybrid_v1")
            names = {c.name for c in client.get_collections().collections}
            pp = client.get_collection(pc).points_count if pc in names else 0
            tp = client.get_collection(tc).points_count if tc in names else 0
            results.append(
                {
                    "check": "qdrant",
                    "ok": pp > 0 and tp > 0,
                    "detail": {"patient_points": pp, "trial_points": tp},
                }
            )
        except Exception as exc:
            results.append({"check": "qdrant", "ok": False, "detail": str(exc)})

    print(json.dumps({"results": results}, indent=2, default=str))
    ok = all(r.get("ok") for r in results)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
