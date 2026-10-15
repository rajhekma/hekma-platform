"""
Phase 0: Coverage report for MySQL subjectIds vs Postgres FHIR vs compose_summary_block.

Usage:
  python scripts/patient_summary_coverage_report.py
  python scripts/patient_summary_coverage_report.py --limit 5000 --output results/coverage.json
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

from services.patient_summary_coverage_service import PAGE_SIZE, build_coverage_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count MySQL subjects with PG clinical data vs compose_summary_block coverage."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max MySQL subjects to scan (0 = all).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=PAGE_SIZE,
        help="MySQL page size (default 500).",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional path to write JSON report.",
    )
    args = parser.parse_args()

    report = build_coverage_report(
        limit=args.limit if args.limit > 0 else None,
        page_size=args.page_size,
    )
    text = json.dumps(report, indent=2)
    print(text)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"[done] Wrote coverage report to {out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
