"""
Accuracy harness for TrialGPT matching (T2P / P2T).

Reads already-persisted matching / aggregation / ranking results from Postgres
(no new LLM calls) and reports where match quality is won or lost:

  * criterion-level label breakdown (included / not included / not enough
    information / not applicable, and exclusion equivalents)
  * per-candidate criteria-match % distribution (+ how many clear >= 80%)
  * retrieval relevance distribution (aggregation relevance_score_R)

This isolates the bottleneck:
  - lots of "not enough information"  -> data / criteria mismatch
  - lots of "not included"            -> genuine ineligibility
  - low relevance_score_R spread      -> retrieval pulled off-topic candidates

Usage:
  python scripts/accuracy_harness.py --job <job_id>
  python scripts/accuracy_harness.py --recent-flow T2P --limit 3
  python scripts/accuracy_harness.py --recent-flow P2T --limit 3 --output results/accuracy_p2t.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from utils.pg_util import pg_transaction
from utils.matching_result_util import (
    normalize_criteria_dict,
    get_label,
    compute_eligible,
    criterion_pass_rate,
)

INCLUSION_LABELS = ["included", "not included", "not applicable", "not enough information"]
EXCLUSION_LABELS = ["excluded", "not excluded", "not applicable", "not enough information"]


def _fetch_recent_jobs(flow_type: str, limit: int) -> list[str]:
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT job_id
            FROM matching_jobs
            WHERE flow_type = %s AND status = 'COMPLETED'
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (flow_type, limit),
        )
        return [r["job_id"] for r in (cur.fetchall() or [])]


def _fetch_job(job_id: str) -> dict | None:
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            "SELECT job_id, flow_type, query_id, status FROM matching_jobs WHERE job_id = %s",
            (job_id,),
        )
        return cur.fetchone()


def _fetch_rows(job_id: str) -> list[dict]:
    """Join matching + aggregation + ranking for every (query, candidate) in a job."""
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT mr.query_id,
                   mr.candidate_id,
                   mr.inclusion_results,
                   mr.exclusion_results,
                   ar.relevance_score_R  AS relevance_score_r,
                   ar.eligibility_score_E AS eligibility_score_e,
                   fr.final_score,
                   fr.rank_position
            FROM matching_results mr
            LEFT JOIN aggregation_results ar
              ON mr.job_id = ar.job_id AND mr.flow_type = ar.flow_type
             AND mr.query_id = ar.query_id AND mr.candidate_id = ar.candidate_id
            LEFT JOIN final_ranking fr
              ON mr.job_id = fr.job_id AND mr.flow_type = fr.flow_type
             AND mr.query_id = fr.query_id AND mr.candidate_id = fr.candidate_id
            WHERE mr.job_id = %s
            ORDER BY fr.rank_position NULLS LAST
            """,
            (job_id,),
        )
        return cur.fetchall() or []


def _label_counts(norm: dict, allowed: list[str]) -> dict[str, int]:
    counts = {lbl: 0 for lbl in allowed}
    counts["_other"] = 0
    for v in norm.values():
        lbl = get_label(v)
        if lbl in counts:
            counts[lbl] += 1
        else:
            counts["_other"] += 1
    return counts


def analyze_job(job_id: str, threshold_pct: float = 80.0) -> dict:
    job = _fetch_job(job_id)
    if not job:
        return {"job_id": job_id, "error": "job not found"}

    rows = _fetch_rows(job_id)
    inc_totals = {lbl: 0 for lbl in INCLUSION_LABELS}
    exc_totals = {lbl: 0 for lbl in EXCLUSION_LABELS}

    candidates = []
    pass_rates = []
    relevances = []
    eligible_count = 0
    meets_threshold = 0

    for r in rows:
        inc = normalize_criteria_dict(r.get("inclusion_results"))
        exc = normalize_criteria_dict(r.get("exclusion_results"))

        for lbl, n in _label_counts(inc, INCLUSION_LABELS).items():
            if lbl in inc_totals:
                inc_totals[lbl] += n
        for lbl, n in _label_counts(exc, EXCLUSION_LABELS).items():
            if lbl in exc_totals:
                exc_totals[lbl] += n

        rate = criterion_pass_rate(inc, exc)
        elig = compute_eligible(inc, exc)
        rel = float(r.get("relevance_score_r") or 0.0)

        pass_rates.append(rate)
        relevances.append(rel)
        if elig:
            eligible_count += 1
        if rate >= threshold_pct:
            meets_threshold += 1

        inc_met = sum(1 for v in inc.values() if get_label(v) == "included")
        exc_viol = sum(1 for v in exc.values() if get_label(v) == "excluded")
        candidates.append({
            "rank": r.get("rank_position"),
            "candidate_id": r.get("candidate_id"),
            "criteria_match_pct": round(rate, 1),
            "eligible": elig,
            "inclusion_met": f"{inc_met}/{len(inc)}",
            "exclusion_violated": f"{exc_viol}/{len(exc)}",
            "relevance_score_R": rel,
            "final_score": float(r.get("final_score") or 0.0),
        })

    def _stats(vals):
        if not vals:
            return {"min": None, "median": None, "max": None, "mean": None}
        return {
            "min": round(min(vals), 1),
            "median": round(statistics.median(vals), 1),
            "max": round(max(vals), 1),
            "mean": round(statistics.mean(vals), 1),
        }

    n = len(rows)
    return {
        "job_id": job_id,
        "flow_type": job["flow_type"],
        "query_id": job["query_id"],
        "candidate_count": n,
        "eligible_count": eligible_count,
        f"meets_{int(threshold_pct)}pct_count": meets_threshold,
        "criteria_match_pct_stats": _stats(pass_rates),
        "relevance_score_R_stats": _stats(relevances),
        "inclusion_label_totals": inc_totals,
        "exclusion_label_totals": exc_totals,
        "candidates": candidates,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", help="Specific job_id to analyze")
    ap.add_argument("--recent-flow", choices=["T2P", "P2T"], help="Analyze N most recent COMPLETED jobs of this flow")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--threshold", type=float, default=80.0, help="Criteria-match %% threshold to count as a strong match")
    ap.add_argument("--output", help="Optional path to write the JSON report")
    args = ap.parse_args()

    job_ids: list[str] = []
    if args.job:
        job_ids = [args.job]
    elif args.recent_flow:
        job_ids = _fetch_recent_jobs(args.recent_flow, args.limit)
    else:
        ap.error("Provide --job or --recent-flow")

    reports = [analyze_job(j, args.threshold) for j in job_ids]

    for rep in reports:
        print("=" * 70)
        print(f"job={rep.get('job_id')} flow={rep.get('flow_type')} query={str(rep.get('query_id'))[:40]}")
        if rep.get("error"):
            print("  ERROR:", rep["error"])
            continue
        print(f"  candidates={rep['candidate_count']} eligible={rep['eligible_count']} "
              f"meets_{int(args.threshold)}pct={rep[f'meets_{int(args.threshold)}pct_count']}")
        print(f"  criteria_match% -> {rep['criteria_match_pct_stats']}")
        print(f"  relevance_R    -> {rep['relevance_score_R_stats']}")
        print(f"  inclusion labels -> {rep['inclusion_label_totals']}")
        print(f"  exclusion labels -> {rep['exclusion_label_totals']}")
        print("  top candidates:")
        for c in rep["candidates"][:10]:
            print(f"    rank={c['rank']} match%={c['criteria_match_pct']} "
                  f"inc={c['inclusion_met']} exc={c['exclusion_violated']} "
                  f"relR={c['relevance_score_R']} eligible={c['eligible']} cand={str(c['candidate_id'])[:24]}")

    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(reports, f, indent=2, default=str)
        print(f"\n[written] {args.output}")


if __name__ == "__main__":
    main()
