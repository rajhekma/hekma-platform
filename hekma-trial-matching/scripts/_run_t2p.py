"""Run the FULL Trial-to-Patients (T2P) pipeline for one NCT id.

Creates a matching_jobs record, runs retrieval -> LLM matching -> aggregation ->
ranking (persisted to Postgres), then prints the final ranked patients.

Usage:
  python scripts/_run_t2p.py [NCT_ID] [prospective_count]
"""
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from repositories.matching_jobs_repo import create_job, get_job
from workflows.trial_to_patients import run_trial_to_patients_workflow_db
from utils.pg_util import pg_transaction


def main() -> int:
    nct_id = sys.argv[1] if len(sys.argv) > 1 else "NCT00002288"
    prospective = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    job_id = str(uuid.uuid4())

    parameters = {
        "nct_id": nct_id,
        "corpus": "sigir",
        "retrieval_mode": "rag",
        "prospective_patient_count": prospective,
        "rag_threshold": 0.0,
        "debug": True,
    }

    print(f"[t2p] Creating job {job_id} for {nct_id} (prospective={prospective})")
    create_job(
        job_id=job_id,
        flow_type="T2P",
        requested_user_id="cli-demo",
        user_type="ADMIN",
        query_id=nct_id,
        parameters=parameters,
    )

    print("[t2p] Running full pipeline (retrieval -> matching -> aggregation -> ranking)...")
    run_trial_to_patients_workflow_db(job_id)

    job = get_job(job_id)
    print("\n[t2p] Job status:", job.get("status"))
    print(
        "[t2p] Stages:",
        {
            "compose": job.get("compose_status"),
            "retrieve": job.get("retrieve_status"),
            "evaluate": job.get("evaluate_status"),
            "rank": job.get("rank_status"),
        },
    )

    with pg_transaction() as (_, cur):
        cur.execute(
            """
            SELECT candidate_id, final_score, rank_position
            FROM final_ranking
            WHERE job_id = %s AND flow_type = 'T2P'
            ORDER BY rank_position
            """,
            (job_id,),
        )
        ranked = cur.fetchall() or []

        cur.execute(
            """
            SELECT candidate_id, relevance_score, eligibility_score,
                   relevance_explanation, eligibility_explanation
            FROM aggregation_results
            WHERE job_id = %s AND flow_type = 'T2P'
            """,
            (job_id,),
        )
        agg = {r["candidate_id"]: r for r in (cur.fetchall() or [])}

    print(f"\n[t2p] Final ranked patients ({len(ranked)}):\n")
    for r in ranked:
        pid = r["candidate_id"]
        a = agg.get(pid, {})
        print(f"#{r['rank_position']}  patient_id={pid}  final_score={r['final_score']}")
        print(f"     relevance={a.get('relevance_score')}  eligibility={a.get('eligibility_score')}")
        rex = (a.get("relevance_explanation") or "").strip()
        eex = (a.get("eligibility_explanation") or "").strip()
        if rex:
            print(f"     relevance: {rex[:300]}")
        if eex:
            print(f"     eligibility: {eex[:300]}")
        print()

    print(f"[t2p] Done. job_id={job_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
