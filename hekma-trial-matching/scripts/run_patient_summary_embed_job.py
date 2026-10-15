"""
Orchestrator: coverage → summarize (sharded) → optional Qdrant patient embed.

Usage examples:
  python scripts/run_patient_summary_embed_job.py --dry-run-coverage
  python scripts/run_patient_summary_embed_job.py --limit 10 --skip-disease-llm --no-embed
  python scripts/run_patient_summary_embed_job.py --shards 4 --shard-id 0 --skip-disease-llm --embed
  python scripts/run_patient_summary_embed_job.py --retry-errors --embed
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

from services.patient_summary_coverage_service import build_coverage_report
from services.patient_qdrant_embed_service import (
    DEFAULT_EMBED_ERROR_PATH,
    embed_from_compose,
)
from services.patient_summary_batch_service import (
    DEFAULT_ERROR_PATH,
    DEFAULT_PROGRESS_DIR,
    load_dlq_subject_ids,
    run_summary_shard,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Coverage-first patient summarize into compose_summary_block "
            "with optional incremental Qdrant embed."
        )
    )
    parser.add_argument(
        "--dry-run-coverage",
        action="store_true",
        help="Only run Phase 0 coverage report and exit.",
    )
    parser.add_argument(
        "--coverage-limit",
        type=int,
        default=0,
        help="Optional max subjects to scan for coverage (0 = all).",
    )
    parser.add_argument(
        "--coverage-output",
        default="results/patient_summary_coverage.json",
        help="Where to write coverage JSON.",
    )
    parser.add_argument("--shards", type=int, default=1, help="Number of shards (default 1).")
    parser.add_argument("--shard-id", type=int, default=0, help="This worker shard id (0-based).")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help=(
            "Safety cap: max eligible patients this shard will summarize "
            "(skipped/generated/failed count; no_pg_data does not consume the cap)."
        ),
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=500,
        help="MySQL page size when scanning subjectIds.",
    )
    parser.add_argument(
        "--with-icd-disease-llm",
        action="store_true",
        help="Run ICD-10 LLM disease normalization (more expensive). Default: skip ICD LLM.",
    )
    parser.add_argument("--model", default=None, help="Override compose LLM model.")
    parser.add_argument(
        "--llm-service",
        default=None,
        choices=["claude", "openai"],
        help="Override compose LLM provider.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if compose_summary_block is up-to-date.",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Reprocess subject_ids from patient_summary_errors.jsonl instead of full scan.",
    )
    parser.add_argument(
        "--error-path",
        default=str(DEFAULT_ERROR_PATH),
        help="Summary DLQ JSONL path.",
    )
    parser.add_argument(
        "--progress-dir",
        default=str(DEFAULT_PROGRESS_DIR),
        help="Directory for per-shard progress JSON.",
    )
    embed_group = parser.add_mutually_exclusive_group()
    embed_group.add_argument(
        "--embed",
        action="store_true",
        help="After summarize, embed updated (or all compose) patients into Qdrant.",
    )
    embed_group.add_argument(
        "--no-embed",
        action="store_true",
        help="Skip Qdrant embed (default if neither flag set: no embed).",
    )
    parser.add_argument(
        "--embed-all-compose",
        action="store_true",
        help="When embedding, upsert all compose_summary_block profiles (not only this run).",
    )
    parser.add_argument(
        "--embed-batch-size",
        type=int,
        default=50,
        help="Qdrant upsert batch size.",
    )
    parser.add_argument(
        "--embed-error-path",
        default=str(DEFAULT_EMBED_ERROR_PATH),
        help="Embed DLQ JSONL path.",
    )
    parser.add_argument(
        "--skip-summarize",
        action="store_true",
        help="Skip summarize phase (useful with --embed / --embed-all-compose only).",
    )
    args = parser.parse_args()

    # Coverage
    coverage = build_coverage_report(
        limit=args.coverage_limit if args.coverage_limit > 0 else None,
    )
    cov_path = Path(args.coverage_output)
    cov_path.parent.mkdir(parents=True, exist_ok=True)
    cov_path.write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"coverage": coverage}, indent=2))

    if args.dry_run_coverage:
        print(f"[done] Coverage only. Wrote {cov_path}")
        return 0

    skip_disease_llm = not args.with_icd_disease_llm
    do_embed = bool(args.embed) and not args.no_embed

    summary_stats = None
    updated_ids: list[str] = []

    if not args.skip_summarize:
        subject_ids = None
        if args.retry_errors:
            subject_ids = load_dlq_subject_ids(Path(args.error_path))
            print(f"[retry-errors] Loaded {len(subject_ids)} subject_ids from DLQ")
            if not subject_ids:
                print("[retry-errors] Nothing to retry.")
                return 0

        summary_stats = run_summary_shard(
            shards=args.shards,
            shard_id=args.shard_id,
            limit=args.limit if args.limit > 0 else None,
            page_size=args.page_size,
            skip_disease_llm=skip_disease_llm,
            model=args.model,
            llm_service=args.llm_service,
            force=args.force or args.retry_errors,
            subject_ids=subject_ids,
            error_path=Path(args.error_path),
            progress_dir=Path(args.progress_dir),
        )
        updated_ids = list(summary_stats.get("updated_patient_ids") or [])
        print(json.dumps({"summary": summary_stats}, indent=2, default=str))

    embed_stats = None
    if do_embed:
        if args.embed_all_compose or args.skip_summarize:
            embed_stats = embed_from_compose(
                patient_ids=None,
                limit=args.limit if args.limit > 0 else None,
                batch_size=args.embed_batch_size,
                error_path=Path(args.embed_error_path),
            )
        elif updated_ids:
            embed_stats = embed_from_compose(
                patient_ids=updated_ids,
                batch_size=args.embed_batch_size,
                error_path=Path(args.embed_error_path),
            )
        else:
            embed_stats = {
                "requested": 0,
                "found_in_compose": 0,
                "upserted": 0,
                "failed": 0,
                "message": "No updated patients in this run; nothing to embed.",
            }
        print(json.dumps({"embed": embed_stats}, indent=2, default=str))

    print(
        json.dumps(
            {
                "done": True,
                "coverage_path": str(cov_path),
                "eligible_to_generate": coverage.get("eligible_to_generate"),
                "summary": summary_stats,
                "embed": embed_stats,
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
