import argparse
from ingestion import ingest_corpus
from retrieval import hybrid_retrieve


def parse_args():
    parser = argparse.ArgumentParser(description="TrialGPT hybrid retrieval pipeline")
    parser.add_argument("-c","--corpus", default="corpus.jsonl", help="Path to corpus JSONL file")
    parser.add_argument("--patient", default=None, help="Patient note string")
    parser.add_argument("-tk","--topk", type=int, default=10, help="Number of trials to retrieve")
    parser.add_argument("-noi", "--no-ingest", action="store_true", help="Skip ingestion, query only")
    parser.add_argument("-rec", "--recreate", action="store_true", help="Drop and recreate Qdrant collection before ingestion")
    return parser.parse_args()


SAMPLE_PATIENT = (
    "A 58-year-old African-American woman presents to the ER with episodic "
    "pressing/burning anterior chest pain that began two days earlier for the "
    "first time in her life. The pain started while she was walking, radiates "
    "to the back, and is accompanied by nausea, diaphoresis and mild dyspnea, "
    "but is not increased on inspiration. The latest episode of pain ended half "
    "an hour prior to her arrival. She is known to have hypertension and obesity. "
    "She denies smoking, diabetes, hypercholesterolemia, or a family history of "
    "heart disease. She currently takes no medications. Physical examination is "
    "normal. The EKG shows nonspecific changes."
)


if __name__ == "__main__":
    args = parse_args()

    if not args.no_ingest:
        ingest_corpus(args.corpus, recreate=args.recreate)

    patient_note = args.patient or SAMPLE_PATIENT
    hits = hybrid_retrieve(patient_note, top_k_final=args.topk)

    print(f"\n[results] Top {len(hits)} candidates:")
    for i, h in enumerate(hits[:80], 1):
        print(f"  {i:>2}. [{h['score']:.4f}] {h['nct_id']} — {h['title'][:80]}")