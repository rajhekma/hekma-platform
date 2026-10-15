"""Run the FULL Patient-to-Trials (P2T) pipeline for one patient (subject UUID).

Usage:
  python scripts/_run_p2t.py [SUBJECT_ID] [corpus]
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from repositories.matching_jobs_repo import create_job, get_job
from workflows.patient_to_trials import run_patient_workflow


def main() -> int:
    subject_id = sys.argv[1] if len(sys.argv) > 1 else "00c13f8d-c0c1-55f2-b2d5-eab8ea4fdae2"
    corpus = sys.argv[2] if len(sys.argv) > 2 else "sigir"

    job_id = str(uuid.uuid4())
    parameters = {
        "patient_id": subject_id,
        "selected_disease": [],
        "selected_region": [],
        "corpus": corpus,
        "retrieval_mode": "rag",
        "debug": True,
    }

    print(f"[p2t] Creating job {job_id} for patient {subject_id}")
    create_job(
        job_id=job_id,
        flow_type="P2T",
        requested_user_id="cli-demo",
        user_type="ADMIN",
        query_id=subject_id,
        parameters=parameters,
    )

    run_patient_workflow(
        job_id,
        {
            "patient_id": subject_id,
            "selected_disease": [],
            "selected_region": [],
            "retrieval_mode": "rag",
            "debug": True,
        },
        corpus,
    )

    job = get_job(job_id)
    print("[p2t] Job status:", job.get("status"))
    print(f"[p2t] Done. job_id={job_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
