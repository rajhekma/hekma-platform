import json
import time
import argparse
from collections import defaultdict
from tqdm import tqdm
from retrieval import hybrid_retrieve
from utils import load_or_build_profiles

def load_queries(path: str) -> list[dict]:
    queries = []
    with open(path) as f:
        for line in f:
            queries.append(json.loads(line))
    return queries


def load_qrels(path: str) -> dict[str, set[str]]:
    qrels = defaultdict(set)
    with open(path) as f:
        next(f)
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) != 3:
                continue
            query_id, corpus_id, score = parts[0].strip(), parts[1].strip(), int(parts[2].strip())
            if score >= 1:
                qrels[query_id].add(corpus_id)
    return qrels


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not retrieved:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / min(k, len(retrieved))


def average_precision(retrieved: list[str], relevant: set[str]) -> float:
    if not relevant:
        return 0.0
    hits, score = 0, 0.0
    for i, doc in enumerate(retrieved, 1):
        if doc in relevant:
            hits += 1
            score += hits / i
    return score / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for i, doc in enumerate(retrieved, 1):
        if doc in relevant:
            return 1.0 / i
    return 0.0


def run_benchmark(queries_path, qrels_path, top_k, k_values, threshold, output_path, profiles_path):
    queries = load_queries(queries_path)
    qrels   = load_qrels(qrels_path)
    queries = [q for q in queries if q["_id"] in qrels]
    profiles = load_or_build_profiles(queries, profiles_path)

    print(f"[benchmark] Evaluating {len(queries)} queries | K={k_values} | threshold={threshold}\n")

    scores      = defaultdict(lambda: defaultdict(list))  # metric -> k -> [scores]
    ap_scores   = []
    rr_scores   = []
    per_query   = []

    for query in tqdm(queries, desc="Evaluating", unit="query"):
        qid      = query["_id"]
        relevant = qrels[qid]

        t0   = time.time()
        hits = hybrid_retrieve(query["text"], top_k_final=top_k, profile=profiles[query["_id"]])
        # hits = hybrid_retrieve(query["text"], top_k_final=top_k)
        elapsed = time.time() - t0

        retrieved_ids = [h["nct_id"] for h in hits if h["score"] >= threshold]

        ap = average_precision(retrieved_ids, relevant)
        rr = reciprocal_rank(retrieved_ids, relevant)
        ap_scores.append(ap)
        rr_scores.append(rr)

        query_result = {
            "query_id":      qid,
            "relevant":      list(relevant),
            "retrieved":     retrieved_ids,
            "elapsed_sec":   round(elapsed, 2),
            "ap":            round(ap, 4),
            "rr":            round(rr, 4),
            "metrics":       {},
        }

        for k in k_values:
            r_at_k = recall_at_k(retrieved_ids, relevant, k)
            p_at_k = precision_at_k(retrieved_ids, relevant, k)
            scores["recall"][k].append(r_at_k)
            scores["precision"][k].append(p_at_k)
            query_result["metrics"][f"recall@{k}"]    = round(r_at_k, 4)
            query_result["metrics"][f"precision@{k}"] = round(p_at_k, 4)

        per_query.append(query_result)

        tqdm.write(
            f"  {qid} | {len(relevant)} relevant | {elapsed:.1f}s | "
            f"AP={ap:.4f} RR={rr:.4f} | "
            + " ".join(f"R@{k}={scores['recall'][k][-1]:.4f}" for k in k_values)
        )

    # ── Aggregate results ──────────────────────────────────────────────────────
    summary = {
        "MAP":  round(sum(ap_scores) / len(ap_scores), 4),
        "MRR":  round(sum(rr_scores) / len(rr_scores), 4),
    }
    for k in k_values:
        summary[f"mean_recall@{k}"]    = round(sum(scores["recall"][k])    / len(scores["recall"][k]),    4)
        #summary[f"mean_precision@{k}"] = round(sum(scores["precision"][k]) / len(scores["precision"][k]), 4)

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for key, val in summary.items():
        print(f"  {key:<25} = {val:.4f}")

    # ── Save output ────────────────────────────────────────────────────────────
    output = {"summary": summary, "per_query": per_query}
    with open(output_path, "w") as f:
        json.dump(output, f, indent=4)
    print(f"\n[done] Results saved to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark hybrid retrieval")
    parser.add_argument("-qu", "--queries", required=True, help="Path to queries.jsonl")
    parser.add_argument("-qr", "--qrels", required=True, help="Path to qrels TSV file")
    parser.add_argument("--top-k", type=int, default=80, help="Max trials to retrieve per query")
    parser.add_argument("-k", "--k-values", type=int,   nargs="+", default=[10, 20, 30], help="K values for Recall/Precision@K")
    parser.add_argument("-t", "--threshold", type=float, default=0.1, help="Minimum score threshold")
    parser.add_argument("-o", "--output", default="benchmark_results.json", help="Output JSON file path")
    parser.add_argument("--profiles", default="profiles.json", help="Path to profiles cache file")
    args = parser.parse_args()

    run_benchmark(args.queries, args.qrels, args.top_k, args.k_values, args.threshold, args.output, args.profiles)