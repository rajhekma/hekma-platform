"""
CLI tool for TrialGPT Lite.
Allows running clinical trial matching queries directly from the terminal.
"""

import argparse
import json
import sys

from trialgpt_lite.service import TrialGPTLiteService
from trialgpt_lite.schemas.request import MatchRequest, PatientProfile


def main():
    parser = argparse.ArgumentParser(
        description="TrialGPT Lite: Search and match clinical trials using ClinicalTrials.gov API v2."
    )
    parser.add_argument(
        "-c", "--condition",
        type=str,
        required=True,
        help="Medical condition or disease to match (e.g., 'triple negative breast cancer', 'melanoma').",
    )
    parser.add_argument(
        "-n", "--patient-note",
        type=str,
        default=None,
        help="Optional free-text patient clinical summary or note for criterion-level matching.",
    )
    parser.add_argument(
        "-a", "--age",
        type=float,
        default=None,
        help="Patient age in years.",
    )
    parser.add_argument(
        "-s", "--sex",
        type=str,
        choices=["FEMALE", "MALE", "ALL"],
        default=None,
        help="Patient biological sex.",
    )
    parser.add_argument(
        "-m", "--max-trials",
        type=int,
        default=10,
        help="Maximum candidate trials to fetch from ClinicalTrials.gov (default: 10).",
    )
    parser.add_argument(
        "-l", "--max-evals", "--max-llm",
        dest="max_evals",
        type=int,
        default=3,
        help="Number of top candidates to evaluate with rule-based criteria matcher (default: 3).",
    )
    parser.add_argument(
        "-p", "--provider",
        type=str,
        default="heuristic",
        help="Criteria matching engine (default: 'heuristic' offline rule-based).",
    )
    parser.add_argument(
        "--all-statuses",
        action="store_true",
        help="Include non-recruiting / closed studies as well.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON response.",
    )

    args = parser.parse_args()

    patient = None
    if args.patient_note or args.age is not None or args.sex:
        patient = PatientProfile(
            age=args.age,
            sex=args.sex,
            condition=args.condition,
            clinical_note=args.patient_note,
        )

    request = MatchRequest(
        condition=args.condition,
        patient=patient,
        page_size=args.max_trials,
        max_criteria_evals=args.max_evals,
        recruiting_only=not args.all_statuses,
        provider=args.provider,
    )

    service = TrialGPTLiteService()
    report = service.search_and_match(request)

    if args.json:
        print(report.model_dump_json(indent=2))
        return

    # Print Pretty Terminal Output
    print("\n" + "=" * 78)
    print(f"🔬 TrialGPT Lite: Clinical Trial Match Report (Offline Rule-Based)")
    print("=" * 78)
    print(f"Condition Searched : {report.searched_condition}")
    print(f"Total in CT.gov    : {report.total_trials_in_registry}")
    print(f"Retrieved Trials   : {report.retrieved_trials_count}")
    print(f"Criteria Evaluated : {report.evaluated_trials_count}")
    print(f"Execution Time     : {report.execution_time_seconds}s")
    print("-" * 78)

    if not report.trials:
        print("No clinical trials matched the query.")
        return

    for idx, trial in enumerate(report.trials, 1):
        verdict_icon = {
            "ELIGIBLE": "✅",
            "LIKELY_ELIGIBLE": "🟡",
            "INELIGIBLE": "❌",
            "UNCERTAIN": "❓",
            "FILTERED_OUT": "🚫",
            "RETRIEVED_ONLY": "📋",
        }.get(trial.verdict.value, "ℹ️")

        print(f"\n[{idx}] {trial.nct_id} | {verdict_icon} Verdict: {trial.verdict.value} (Score: {trial.eligibility_score:.2f})")
        print(f"    Title  : {trial.title}")
        print(f"    Status : {trial.overall_status}")
        if trial.phases:
            print(f"    Phases : {', '.join(trial.phases)}")
        if trial.interventions:
            print(f"    Drugs  : {', '.join(trial.interventions[:3])}")
        print(f"    URL    : {trial.web_url}")
        print(f"    Summary: {trial.summary_reasoning}")

        if trial.criteria_evaluations:
            print("    Criteria Breakdown:")
            for c_eval in trial.criteria_evaluations[:4]:
                c_icon = "✓" if c_eval.label in ["included", "not excluded"] else ("✗" if c_eval.label in ["excluded", "not included"] else "•")
                print(f"      [{c_icon}] {c_eval.criterion_type.upper()}: {c_eval.label} -> {c_eval.reasoning}")

    print("\n" + "=" * 78 + "\n")


if __name__ == "__main__":
    main()
