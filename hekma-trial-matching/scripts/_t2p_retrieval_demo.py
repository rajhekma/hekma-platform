"""Quick T2P RETRIEVAL demo: trial -> top candidate patients from Qdrant.

No LLM matching/aggregation and no DB writes. Just proves the patient vector
index is searchable for the T2P flow.

Usage:
  python scripts/_t2p_retrieval_demo.py [NCT_ID] [top_k]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from repositories.trialgpt_corpus_repo import fetch_trial_by_id
from repositories.compose_repo import fetch_compose_summary
from services.rag_retrieval_service import retrieve_patient_ids_for_trial
from utils.trial_criteria_util import criteria_to_matching_text
from utils.pg_util import pg_transaction


def _pick_nct_id() -> str:
    with pg_transaction() as (_, cur):
        cur.execute("SELECT nct_id FROM trialgpt_corpus ORDER BY nct_id LIMIT 1")
        row = cur.fetchone()
    return row["nct_id"] if row else None


def main() -> int:
    nct_id = sys.argv[1] if len(sys.argv) > 1 else _pick_nct_id()
    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    if not nct_id:
        print("No trial found in trialgpt_corpus.")
        return 1

    trial = fetch_trial_by_id(nct_id)
    if not trial:
        print(f"Trial {nct_id} not found.")
        return 1
    trial = dict(trial)

    rag_trial = {
        "title": trial.get("title", ""),
        "text": trial.get("text", ""),
        "inclusion_criteria": criteria_to_matching_text(trial.get("inclusion_criteria")),
        "exclusion_criteria": criteria_to_matching_text(trial.get("exclusion_criteria")),
        "diseases": trial.get("diseases", []) or [],
        "drugs": trial.get("drugs", []) or [],
    }

    print("=" * 90)
    print(f"TRIAL: {nct_id}")
    print(f"Title: {trial.get('title', '')}")
    print(f"Diseases: {rag_trial['diseases']}")
    print(f"Drugs: {rag_trial['drugs']}")
    print("=" * 90)

    patient_ids = retrieve_patient_ids_for_trial(
        trial=rag_trial, top_k=top_k, threshold=0.0, debug=True
    )
    print(f"\nTop {len(patient_ids)} candidate patients:\n")

    for i, pid in enumerate(patient_ids, 1):
        print(f"{i:>2}. patient_id={pid}")
        try:
            summ = fetch_compose_summary(pid) or ""
        except Exception as exc:
            summ = f"(summary fetch error: {exc})"
        snippet = (summ[:240] + "...") if len(summ) > 240 else summ
        if snippet:
            print(f"    {snippet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
