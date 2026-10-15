"""Inspect the exact /results payload (build_job_results_response) for given jobs."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from core.response_builders import build_job_results_response
from repositories.matching_jobs_repo import get_job

JOBS = sys.argv[1:] or [
    "a122ed39-683d-493d-a014-04afcf840dff",  # P2T
    "7f594b91-55ae-4a77-b1a8-b1bd8201f62c",  # T2P
]

for job_id in JOBS:
    job = get_job(job_id)
    flow = (job or {}).get("flow_type", "P2T")
    resp = build_job_results_response(job_id, flow_type=flow)
    evals = resp.get("evaluations", [])
    print("=" * 70)
    print(f"job={job_id} flow={flow} evaluations={len(evals)}")
    for e in evals[:5]:
        cid = e.get("trial_id") or e.get("patient_id")
        print(
            f"  rank={e.get('rank')} match%={e.get('criteria_match_pct')} "
            f"strong={e.get('meets_strong_match')} thr={e.get('strong_match_threshold_pct')} "
            f"eligible={e.get('eligible')} rankscore={round(e.get('ranking_score', 0), 3)} "
            f"inc={e.get('inclusion_met')} exc={e.get('exclusion_violated')} id={str(cid)[:24]}"
        )
    # Show full first entry keys to confirm schema
    if evals:
        print("  first-entry keys:", sorted(evals[0].keys()))
