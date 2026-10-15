"""
Export trialgpt_corpus (Postgres) to JSONL for TrialGPT_RAG/ingest_trials.py.

Usage (from repo root):
  python scripts/export_trialgpt_corpus_for_qdrant.py
  python scripts/export_trialgpt_corpus_for_qdrant.py --output TrialGPT_RAG/trials.from_corpus.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()
# Full-table export can exceed default 5s PG statement timeout
os.environ.setdefault("PG_STATEMENT_TIMEOUT_MS", "120000")

from repositories.trialgpt_corpus_repo import fetch_all_trials
from utils.trial_criteria_util import criteria_to_matching_text


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        return [text]
    return [str(value)]


def row_to_corpus_line(row: dict) -> dict:
    nct_id = row.get("nct_id") or row.get("_id")
    diseases = _as_list(row.get("diseases"))
    drugs = _as_list(row.get("drugs"))
    inclusion = criteria_to_matching_text(row.get("inclusion_criteria"))
    exclusion = criteria_to_matching_text(row.get("exclusion_criteria"))
    summary = (row.get("text") or "").strip()

    return {
        "_id": nct_id,
        "title": row.get("title") or "",
        "text": summary,
        "metadata": {
            "brief_summary": summary,
            "inclusion_criteria": inclusion,
            "exclusion_criteria": exclusion,
            "diseases_list": diseases,
            "drugs_list": drugs,
        },
    }


def export_trials(output_path: Path) -> int:
    rows = fetch_all_trials()
    if not rows:
        raise RuntimeError("trialgpt_corpus is empty — load trials before Qdrant ingest")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        for row in rows:
            line = row_to_corpus_line(dict(row))
            if not line.get("_id"):
                continue
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
            count += 1

    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Export trialgpt_corpus to Qdrant ingest JSONL")
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "TrialGPT_RAG" / "trials.from_corpus.jsonl"),
        help="Output JSONL path",
    )
    args = parser.parse_args()
    output_path = Path(args.output)
    count = export_trials(output_path)
    print(f"[done] Exported {count} trials to '{output_path}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
