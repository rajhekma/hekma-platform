#!/usr/bin/env python3
"""Fire a cheap real LLM call per product, emit usage, then print patient cost.

Does not print API keys. Loads OPENAI_API_KEY / ANTHROPIC_API_KEY from the
environment or from the existing product .env files.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

BACKEND = Path(__file__).resolve().parents[1]
PLATFORM = BACKEND.parents[1]
WORKSPACE = PLATFORM.parent
sys.path.insert(0, str(BACKEND))

from hekma_ai_usage.client import emit_llm_usage  # noqa: E402

PATIENT_ID = os.getenv("AI_COST_DEMO_PATIENT_ID", "203664")
COST_BASE = os.getenv("AI_USAGE_INGEST_URL", "http://127.0.0.1:8090").rsplit("/internal", 1)[0]
INGEST_URL = os.getenv(
    "AI_USAGE_INGEST_URL",
    "http://127.0.0.1:8090/internal/v1/ai-usage/events",
)
os.environ.setdefault("AI_USAGE_INGEST_URL", INGEST_URL)

ENV_CANDIDATES = [
    WORKSPACE / "Backend API Hekma" / "hekma_data_pipleline" / ".env",
    WORKSPACE / "TrialGPT" / "trailgpt" / ".env",
]


def _load_env_files() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    for path in ENV_CANDIDATES:
        if path.is_file() and load_dotenv:
            load_dotenv(path, override=False)


def _get_cost() -> dict:
    response = requests.get(f"{COST_BASE}/v1/patients/{PATIENT_ID}/ai-cost", timeout=10)
    response.raise_for_status()
    return response.json()


def _print_cost(label: str, body: dict) -> None:
    totals = body["totals"]
    print(f"\n=== {label} ===")
    print(
        f"calls={totals['llm_calls']}  tokens={totals['total_tokens']}  "
        f"cost_usd={totals['cost_usd']}"
    )
    for row in body.get("by_product") or []:
        print(
            f"  product={row['product']:18} tokens={row['total_tokens']:<8} "
            f"${row['cost_usd']}"
        )
    for row in body.get("by_provider") or []:
        models = ", ".join(m["model"] for m in row.get("models") or [])
        print(
            f"  provider={row['provider']:12} tokens={row['total_tokens']:<8} "
            f"${row['cost_usd']}  ({models})"
        )


def _call_openai(prompt: str) -> dict:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": 0,
            "max_tokens": 24,
            "messages": [
                {"role": "system", "content": "Reply in one short sentence."},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    text = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return {"model": model, "usage": payload.get("usage") or {}, "text": text.strip()}


def _call_claude(prompt: str) -> dict:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    model = os.getenv("WORKFLOW_DEFAULT_MODEL", "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 24,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    blocks = payload.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    usage = payload.get("usage") or {}
    return {
        "model": payload.get("model") or model,
        "usage": {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        },
        "text": text.strip(),
    }


def _emit_and_wait(*, product: str, feature: str, provider: str, model: str, usage: dict) -> None:
    emit_llm_usage(
        patient_id=PATIENT_ID,
        product=product,
        feature=feature,
        provider=provider,
        model=model,
        usage=usage,
        source_service="live-llm-cost-demo",
    )
    time.sleep(1.2)


def main() -> int:
    _load_env_files()
    health = requests.get(f"{COST_BASE}/health", timeout=5)
    health.raise_for_status()
    print(f"commerce={health.json()['status']}  patient_id={PATIENT_ID}")
    _print_cost("before", _get_cost())

    steps = [
        ("scan_ai", "smart_scan.demo", "openai", "Name one typical lab on a CBC panel."),
        ("patient_summary", "patient_summary.overview", "openai", "Summarize: adult with hypertension, on lisinopril."),
        ("trial_match", "trial_match.matching", "anthropic", "Is type 2 diabetes a common trial condition? Yes or no."),
    ]

    for product, feature, provider, prompt in steps:
        print(f"\n--- LLM {provider} · {product} ---")
        try:
            if provider == "anthropic":
                result = _call_claude(prompt)
            else:
                result = _call_openai(prompt)
        except Exception as exc:
            print(f"SKIP {product}: {exc}")
            continue
        print(f"model={result['model']} usage={result['usage']}")
        print(f"reply={result['text'][:120]}")
        _emit_and_wait(
            product=product,
            feature=feature,
            provider=provider,
            model=result["model"],
            usage=result["usage"],
        )
        _print_cost("after this call", _get_cost())

    final = _get_cost()
    _print_cost("final", final)
    print("\n" + json.dumps(final, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
