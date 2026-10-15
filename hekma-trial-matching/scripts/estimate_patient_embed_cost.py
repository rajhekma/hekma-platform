"""Smoke-check TrialGPT reads from trialgpt_eligible_patients + estimate embed cost."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from repositories.compose_repo import (
    COMPOSE_READ_TABLE,
    count_compose_summary_block,
    fetch_compose_structured_profile,
    fetch_compose_summary,
    fetch_compose_summaries_map,
)
from utils.pg_util import pg_transaction


def _profile_to_dense_text(profile: dict) -> str:
    sections = [
        "demographics",
        "allergies",
        "conditions",
        "procedures",
        "medications",
        "observations",
        "immunizations",
    ]
    parts = []
    for section in sections:
        value = profile.get(section)
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            parts.append(f"{section}: {value.strip()}")
        elif isinstance(value, dict):
            nested = ", ".join(f"{k}: {v}" for k, v in value.items() if v is not None)
            if nested:
                parts.append(f"{section}: {nested}")
        elif isinstance(value, list) and value:
            parts.append(f"{section}: {json.dumps(value, ensure_ascii=False)}")
    return " ".join(parts)


def main() -> int:
    print("COMPOSE_READ_TABLE =", COMPOSE_READ_TABLE)
    ready = count_compose_summary_block()
    print("ready_patients", ready)

    with pg_transaction() as (_, cur):
        cur.execute(
            """
            SELECT subject_id, mysql_patient_id
            FROM trialgpt_eligible_patients
            WHERE summary_text IS NOT NULL AND structured_json IS NOT NULL
            ORDER BY subject_id
            LIMIT 1
            """
        )
        sample = cur.fetchone()

    if not sample:
        print("ERROR: no sample patient")
        return 1

    sid = sample["subject_id"]
    summary = fetch_compose_summary(sid)
    profile = fetch_compose_structured_profile(sid)
    print("sample_subject_id", sid)
    print("sample_mysql_patient_id", sample.get("mysql_patient_id"))
    print("summary_chars", len(summary or ""))
    print("summary_ok", bool(summary and summary.strip()))
    print("profile_keys", sorted((profile or {}).keys()))
    print("has_7_blocks", all(
        k in (profile or {})
        for k in (
            "demographics",
            "allergies",
            "conditions",
            "procedures",
            "medications",
            "observations",
            "immunizations",
        )
    ))

    # Embed cost estimate from sample of profiles
    with pg_transaction() as (_, cur):
        cur.execute(
            """
            SELECT subject_id, structured_json
            FROM trialgpt_eligible_patients
            WHERE structured_json IS NOT NULL
            ORDER BY subject_id
            LIMIT 100
            """
        )
        rows = cur.fetchall() or []

    token_ests = []
    for row in rows:
        profile = row["structured_json"]
        if isinstance(profile, str):
            profile = json.loads(profile)
        if not isinstance(profile, dict):
            continue
        # Match compose_repo normalization lightly
        text = _profile_to_dense_text(profile)
        token_ests.append(max(1, len(text) // 4))

    if not token_ests:
        print("ERROR: no profiles for cost estimate")
        return 1

    token_ests.sort()
    median = token_ests[len(token_ests) // 2]
    mean = sum(token_ests) / len(token_ests)
    p90 = token_ests[int(len(token_ests) * 0.9)]

    # text-embedding-3-large ~ $0.13 / 1M tokens
    price_per_mtok = 0.13
    total_tokens_mid = ready * mean
    total_tokens_p90 = ready * p90
    cost_mid = total_tokens_mid / 1_000_000 * price_per_mtok
    cost_p90 = total_tokens_p90 / 1_000_000 * price_per_mtok

    # Map size check (don't load all into memory for smoke if huge)
    # Just count via SQL already have ready

    estimate = {
        "ready_patients": ready,
        "sample_n": len(token_ests),
        "dense_tokens_per_patient_min": token_ests[0],
        "dense_tokens_per_patient_median": median,
        "dense_tokens_per_patient_mean": round(mean, 1),
        "dense_tokens_per_patient_p90": p90,
        "embedding_model": "text-embedding-3-large",
        "price_usd_per_1m_tokens": price_per_mtok,
        "estimated_total_tokens_mean": int(total_tokens_mid),
        "estimated_total_tokens_p90": int(total_tokens_p90),
        "estimated_embed_cost_usd_mean": round(cost_mid, 4),
        "estimated_embed_cost_usd_p90": round(cost_p90, 4),
        "notes": [
            "Cost is OpenAI dense embeddings only; BM25 sparse is local/free.",
            "Skip query expansion keeps chat LLM cost at $0 for ingest.",
            "Do not run full embed until this estimate is accepted.",
        ],
    }
    out = ROOT / "results" / "patient_embed_cost_estimate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(estimate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(estimate, indent=2))
    print(f"[done] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
