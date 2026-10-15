"""Export trial_gpt_ehr structured_json for TrialGPT_RAG patient ingest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.trial_gpt_ehr_config import get_trial_gpt_ehr_config
from repositories.trial_gpt_ehr_repo import fetch_ready_subject_ids, fetch_profiles_by_subject_ids


def export_profiles(output_path: Path, limit: int | None = None) -> int:
    """Write {subject_id: structured_profile} JSON from ready trial_gpt_ehr rows."""
    llm = bool(get_trial_gpt_ehr_config().p2t_preferred_llm)
    subject_ids = fetch_ready_subject_ids(llm=llm, limit=limit)
    profiles = fetch_profiles_by_subject_ids(subject_ids, llm=llm)

    out = {}
    for pid, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        out[pid] = {
            k: v
            for k, v in profile.items()
            if k not in ("_generation", "_icd_diseases")
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    return len(out)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Export trial_gpt_ehr structured_json "
            "to TrialGPT_RAG ingestion format."
        )
    )
    parser.add_argument(
        "--output",
        default=str(
            Path(__file__).resolve().parents[1]
            / "TrialGPT_RAG"
            / "patient_block_summaries.from_trial_gpt_ehr.json"
        ),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional row limit for testing (0 = no limit).",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    written = export_profiles(output_path, limit=args.limit if args.limit > 0 else None)
    print(f"[done] Exported {written} trial_gpt_ehr profiles to '{output_path}'.")


if __name__ == "__main__":
    main()
