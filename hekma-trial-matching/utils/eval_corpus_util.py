"""
Fixed trial cohorts for dev eval (e.g. annot_10 pins 10 NCTs for P2T).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from dataset.block_summary.paths import CORPUS_ANNOT_10_JSONL

EVAL_CORPUS_ALIASES = {
    "annot_10": str(CORPUS_ANNOT_10_JSONL.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    "annot10": str(CORPUS_ANNOT_10_JSONL.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    "sigir-eval": str(CORPUS_ANNOT_10_JSONL.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    "eval": str(CORPUS_ANNOT_10_JSONL.relative_to(PROJECT_ROOT)).replace("\\", "/"),
}


def resolve_eval_corpus_jsonl_path(corpus: str | None) -> str | None:
    """
    Return path to a JSONL corpus file that defines a fixed NCT list, or None.
    """
    env_path = os.getenv("P2T_EVAL_CORPUS_JSONL", "").strip()
    if env_path and os.path.isfile(env_path):
        return env_path

    if corpus:
        key = corpus.strip().lower()
        if key in EVAL_CORPUS_ALIASES:
            path = PROJECT_ROOT / EVAL_CORPUS_ALIASES[key]
            if path.is_file():
                return str(path)
        candidate = PROJECT_ROOT / "dataset" / f"corpus_{corpus}.jsonl"
        if candidate.is_file():
            return str(candidate)

    return None


def load_nct_ids_from_corpus_jsonl(path: str) -> list[str]:
    ids: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            nct_id = row.get("nct_id") or row.get("_id")
            if nct_id:
                ids.append(str(nct_id))
    return ids


def load_corpus_jsonl_by_nct(path: str) -> dict[str, dict]:
    """Index corpus JSONL rows by NCT id."""
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            nct_id = row.get("nct_id") or row.get("_id")
            if nct_id:
                out[str(nct_id)] = row
    return out


def merge_retrieval_nct_ids(pinned: list[str], retrieved: list[str] | None) -> list[str]:
    """
    Pinned IDs first (eval cohort), then unique RAG hits.
    When pinned is non-empty and P2T_EVAL_PIN_ONLY=1, return pinned only.
    """
    if not pinned:
        return list(retrieved or [])

    pin_only = os.getenv("P2T_EVAL_PIN_ONLY", "1").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if pin_only:
        return list(pinned)

    seen: set[str] = set()
    merged: list[str] = []
    for nct in pinned + (retrieved or []):
        if nct and nct not in seen:
            seen.add(nct)
            merged.append(nct)
    return merged
