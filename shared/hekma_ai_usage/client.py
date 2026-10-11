"""
Fire-and-forget LLM usage reporter.

Never raises. Never blocks the caller on the ingest path. Cache hits and
failed LLM calls must not call this.

Canonical copy: hekma-platform/shared/hekma_ai_usage.
Keep vendored copies in sync:
  - hekma_data_pipleline/services/ai_common/usage_emitter.py
  - TrialGPT/trailgpt/services/ai_usage.py
"""

from __future__ import annotations

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator, Optional
from uuid import uuid4

logger = logging.getLogger("hekma.ai_usage")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ai-usage")
_warned_unconfigured = False
_warn_lock = threading.Lock()


@dataclass(frozen=True)
class UsageContext:
    patient_id: str
    product: str
    feature: str = ""
    job_id: Optional[str] = None
    tenant_id: int = 1
    source_service: Optional[str] = None


_CTX: ContextVar[Optional[UsageContext]] = ContextVar("hekma_ai_usage_ctx", default=None)


def current_usage_context() -> Optional[UsageContext]:
    return _CTX.get()


def current_usage_patient_id() -> Optional[str]:
    ctx = _CTX.get()
    return ctx.patient_id if ctx else None


@contextmanager
def llm_usage_scope(
    *,
    patient_id: str,
    product: str,
    feature: str = "",
    job_id: Optional[str] = None,
    tenant_id: int = 1,
    source_service: Optional[str] = None,
) -> Iterator[UsageContext]:
    ctx = UsageContext(
        patient_id=str(patient_id),
        product=product,
        feature=feature,
        job_id=job_id,
        tenant_id=int(tenant_id or 1),
        source_service=source_service,
    )
    token: Token = _CTX.set(ctx)
    try:
        yield ctx
    finally:
        _CTX.reset(token)


def normalize_provider(raw: str) -> str:
    key = (raw or "other").strip().lower()
    return {
        "openai": "openai",
        "azure": "openai",
        "azure_openai": "openai",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "google": "google",
        "gemini": "google",
        "groq": "groq",
    }.get(key, key or "other")


def parse_usage_payload(usage: Any) -> tuple[int, int, int]:
    """Accept OpenAI / Anthropic / Gemini / dict usage objects."""
    if usage is None:
        return 0, 0, 0
    if isinstance(usage, dict):
        prompt = int(
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or usage.get("prompt_token_count")
            or 0
        )
        completion = int(
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or usage.get("candidates_token_count")
            or 0
        )
        total = int(usage.get("total_tokens") or (prompt + completion))
        return prompt, completion, total

    prompt = int(
        getattr(usage, "prompt_tokens", 0)
        or getattr(usage, "input_tokens", 0)
        or getattr(usage, "prompt_token_count", 0)
        or 0
    )
    completion = int(
        getattr(usage, "completion_tokens", 0)
        or getattr(usage, "output_tokens", 0)
        or getattr(usage, "candidates_token_count", 0)
        or 0
    )
    total = int(getattr(usage, "total_tokens", 0) or (prompt + completion))
    return prompt, completion, total


def emit_llm_usage(
    *,
    patient_id: Optional[str] = None,
    product: Optional[str] = None,
    feature: Optional[str] = None,
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: Optional[int] = None,
    usage: Any = None,
    job_id: Optional[str] = None,
    tenant_id: Optional[int] = None,
    source_service: Optional[str] = None,
    request_id: Optional[str] = None,
    cached: bool = False,
) -> None:
    """Queue one usage event. Safe to call from request threads and worker pools."""
    try:
        if cached:
            return
        if os.getenv("AI_USAGE_ENABLED", "true").strip().lower() in {"0", "false", "no"}:
            return

        ctx = _CTX.get()
        pid = str(patient_id or (ctx.patient_id if ctx else "") or "").strip()
        prod = (product or (ctx.product if ctx else "") or "").strip()
        if not pid or not prod:
            return
        if usage is not None and prompt_tokens == 0 and completion_tokens == 0:
            prompt_tokens, completion_tokens, parsed_total = parse_usage_payload(usage)
            if total_tokens is None:
                total_tokens = parsed_total
        prompt_tokens = max(int(prompt_tokens or 0), 0)
        completion_tokens = max(int(completion_tokens or 0), 0)
        if prompt_tokens == 0 and completion_tokens == 0:
            return

        payload = {
            "schema_version": 1,
            "request_id": request_id or str(uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id": int(tenant_id or (ctx.tenant_id if ctx else 1) or 1),
            "patient_id": pid,
            "product": prod,
            "feature": (feature or (ctx.feature if ctx else "") or ""),
            "provider": normalize_provider(provider),
            "model": (model or "").strip() or "unknown",
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": int(total_tokens if total_tokens is not None else prompt_tokens + completion_tokens),
            "cached": False,
            "job_id": job_id or (ctx.job_id if ctx else None),
            "source_service": source_service or (ctx.source_service if ctx else None),
        }
        _executor.submit(_dispatch, payload)
    except Exception:
        logger.debug("emit_llm_usage swallowed an error", exc_info=True)


def _dispatch(payload: dict) -> None:
    try:
        queue_url = os.getenv("AI_USAGE_SQS_QUEUE_URL", "").strip()
        if queue_url:
            if _send_sqs(queue_url, payload):
                return
        ingest_url = os.getenv(
            "AI_USAGE_INGEST_URL",
            "http://localhost:8090/internal/v1/ai-usage/events",
        ).strip()
        if ingest_url:
            _send_http(ingest_url, payload)
            return
        _warn_once("AI usage ingest is not configured; dropping events")
    except Exception:
        logger.warning("failed to dispatch AI usage event patient_id=%s", payload.get("patient_id"), exc_info=True)


def _send_http(url: str, payload: dict) -> None:
    import requests

    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("AI_COST_API_KEY", "").strip()
    if api_key:
        headers["X-API-Key"] = api_key
    response = requests.post(url, json=payload, headers=headers, timeout=2.5)
    if response.status_code >= 400:
        logger.warning(
            "AI usage ingest HTTP %s patient_id=%s body=%s",
            response.status_code,
            payload.get("patient_id"),
            response.text[:200],
        )


def _send_sqs(queue_url: str, payload: dict) -> bool:
    try:
        import boto3
    except ImportError:
        return False
    client = boto3.client(
        "sqs",
        region_name=os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION") or "us-east-1",
        endpoint_url=os.getenv("AWS_ENDPOINT_URL") or None,
    )
    client.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))
    return True


def _warn_once(message: str) -> None:
    global _warned_unconfigured
    with _warn_lock:
        if _warned_unconfigured:
            return
        _warned_unconfigured = True
    logger.info(message)
