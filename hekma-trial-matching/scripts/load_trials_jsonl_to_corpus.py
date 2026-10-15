"""
Load parsed trials from dataset/trials.jsonl into trialgpt_corpus (Postgres).

Uses structured inclusion/exclusion dicts from dataset/trials.jsonl.
Optionally merges title/text/metadata from corpus_annot_10.jsonl.

Usage (from repo root):
  python scripts/load_trials_jsonl_to_corpus.py
  python scripts/load_trials_jsonl_to_corpus.py -i dataset/trials.jsonl -a dataset/corpus_annot_10.jsonl
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

from repositories.trialgpt_corpus_repo import upsert_trial_corpus
from utils.eval_corpus_util import load_corpus_jsonl_by_nct
from dataset.block_summary.paths import CORPUS_ANNOT_10_JSONL, TRIALS_JSONL


def _parse_enrollment(value) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return {"count": float(value)}
    except (TypeError, ValueError):
        return {"count": value}


def _metadata_lists(meta: dict, key: str) -> list:
    raw = meta.get(key)
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw.replace("'", '"'))
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def trial_row_to_corpus(row: dict, annot_row: dict | None = None) -> dict:
    meta = (annot_row or {}).get("metadata") or {}
    nct_id = row.get("nct_id") or row.get("_id")
    title = row.get("brief_title") or (annot_row or {}).get("title") or meta.get(
        "brief_title", ""
    )
    text = row.get("brief_summary") or (annot_row or {}).get("text") or meta.get(
        "brief_summary", ""
    )

    diseases = row.get("diseases") or _metadata_lists(meta, "diseases_list")
    drugs = row.get("drugs") or _metadata_lists(meta, "drugs_list")
    phase = row.get("phase") or meta.get("phase")

    return {
        "nct_id": nct_id,
        "title": title,
        "text": text,
        "inclusion_criteria": row.get("inclusion_criteria") or {},
        "exclusion_criteria": row.get("exclusion_criteria") or {},
        "diseases": diseases or [],
        "drugs": drugs or [],
        "phase": phase,
        "enrollment": _parse_enrollment(row.get("enrollment") or meta.get("enrollment")),
        "countries": ["United States"],
        "locations": ["United States"],
        "locations_detailed": [],
        "source_type": "jsonl_eval",
        "raw_json": {"source": "trials.jsonl", "annot": bool(annot_row)},
    }


def main():
    parser = argparse.ArgumentParser(
        description="Upsert parsed trials.jsonl into trialgpt_corpus"
    )
    parser.add_argument(
        "-i",
        "--input",
        default=str(TRIALS_JSONL),
        help="Parsed trials JSONL (dict criteria)",
    )
    parser.add_argument(
        "-a",
        "--annot-corpus",
        default=str(CORPUS_ANNOT_10_JSONL),
        help="Optional annot corpus JSONL for titles/metadata",
    )
    args = parser.parse_args()

    annot_by_nct = {}
    if args.annot_corpus and Path(args.annot_corpus).is_file():
        annot_by_nct = load_corpus_jsonl_by_nct(args.annot_corpus)

    loaded = 0
    errors = []

    with open(args.input, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            nct_id = row.get("nct_id")
            if not nct_id:
                continue
            try:
                corpus_obj = trial_row_to_corpus(row, annot_by_nct.get(nct_id))
                upsert_trial_corpus(corpus_obj)
                loaded += 1
                print(f"OK {nct_id}")
            except Exception as exc:
                errors.append((nct_id, str(exc)))
                print(f"FAIL {nct_id}: {exc}")

    print(f"\nLoaded {loaded} trials into trialgpt_corpus.")
    if errors:
        print(f"Errors ({len(errors)}):")
        for nct_id, msg in errors:
            print(f"  {nct_id}: {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
