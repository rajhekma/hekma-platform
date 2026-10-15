import json
import argparse
from utils import load_or_build_profiles
from retrieval import hybrid_retrieve


def load_queries(path: str) -> list[dict]:
    queries = []
    with open(path) as f:
        for line in f:
            queries.append(json.loads(line))
    return queries


def load_corpus(path: str) -> dict[str, dict]:
    """Returns {nct_id: metadata dict}."""
    corpus = {}
    with open(path) as f:
        for line in f:
            trial = json.loads(line)
            nct_id = trial.get("_id") or trial.get("NCTID")
            if nct_id:
                corpus[nct_id] = trial
    return corpus


def build_trial_entry(trial: dict) -> dict:
    m = trial.get("metadata", {})
    return {
        "brief_title":       trial.get("title", m.get("brief_title", "")),
        "phase":             m.get("phase", ""),
        "drugs":             m.get("drugs", ""),
        "drugs_list":        m.get("drugs_list", []),
        "diseases":          m.get("diseases", ""),
        "diseases_list":     m.get("diseases_list", []),
        "enrollment":        m.get("enrollment", ""),
        "inclusion_criteria": m.get("inclusion_criteria", ""),
        "exclusion_criteria": m.get("exclusion_criteria", ""),
        "brief_summary":     m.get("brief_summary", ""),
        "NCTID":             trial.get("_id", m.get("NCTID", "")),
    }


def run(queries_path, corpus_path, output_path, top_k, threshold, profiles_path):
    queries = load_queries(queries_path)
    corpus  = load_corpus(corpus_path)
    profiles = load_or_build_profiles(queries, profiles_path)
    results = []

    for i, query in enumerate(queries, 1):
        patient_id = query["_id"]
        note       = query["text"]

        print(f"[{i}/{len(queries)}] {patient_id}")

        hits = hybrid_retrieve(note, top_k_final=top_k, profile=profiles[query["_id"]])
        #hits = hybrid_retrieve(note, top_k_final=top_k)
        hits = [h for h in hits if h["score"] >= threshold]

        trial_list = []
        for hit in hits:
            nct_id = hit["nct_id"]
            if nct_id in corpus:
                trial_list.append(build_trial_entry(corpus[nct_id]))
            else:
                trial_list.append({"NCTID": nct_id, "brief_title": hit.get("title", "")})

        results.append({"patient_id": patient_id, "patient": note, "0": trial_list})

    with open(output_path, "w") as f:
        json.dump(results, f, indent=4)

    print(f"\n[done] Saved {len(results)} patient results to {output_path}")




if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retrieve trials for all queries and save structured output")
    parser.add_argument("-qu", "--queries",   required=True, help="Path to queries.jsonl")
    parser.add_argument("-c", "--corpus",    required=True, help="Path to corpus.jsonl")
    parser.add_argument("--output",    default="retrieved.json",  help="Output JSON file path")
    parser.add_argument("--top-k",     type=int,   default=80,    help="Max trials to retrieve per query")
    parser.add_argument("--threshold", type=float, default=0.1,   help="Minimum score threshold")
    parser.add_argument("--profiles", default="profiles.json", help="Path to profiles cache file")
    args = parser.parse_args()

    run(args.queries, args.corpus, args.output, args.top_k, args.threshold, args.profiles)