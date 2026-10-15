"""
Shared LLM calls for OpenAI and Anthropic (Claude).
"""

from __future__ import annotations

import json
import os
import re

from dotenv import load_dotenv

from utils.anthropic_messages import create_anthropic_message
from utils.llm_config import (
    resolve_compose_llm_service,
    resolve_compose_model,
    resolve_workflow_llm_service,
    resolve_workflow_model,
)
from services.ai_usage import current_usage_patient_id, emit_llm_usage

load_dotenv()


def _emit_invoke_usage(llm_service: str, model: str, response: object, feature: str) -> None:
    if not current_usage_patient_id():
        return
    usage = getattr(response, "usage", None)
    emit_llm_usage(
        provider=llm_service,
        model=model,
        usage=usage,
        feature=feature,
        source_service="hekma-trialgpt",
    )


def _openai_client():
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=api_key)


def _anthropic_client():
    from anthropic import Anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    return Anthropic(api_key=api_key)


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    return text


def complete_text(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    llm_service: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> str:
    model = resolve_compose_model(model)
    llm_service = resolve_compose_llm_service(llm_service)

    if llm_service == "claude":
        client = _anthropic_client()
        response = create_anthropic_message(
            client,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        _emit_invoke_usage(llm_service, model, response, "trial_match.compose")
        return "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text" and hasattr(block, "text")
        ).strip()

    client = _openai_client()
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    _emit_invoke_usage(llm_service, model, response, "trial_match.compose")
    return response.choices[0].message.content.strip()


def complete_workflow_text(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    llm_service: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> str:
    """Same as complete_text but uses WORKFLOW_* env defaults (P2T matching/aggregation)."""
    model = resolve_workflow_model(model)
    llm_service = resolve_workflow_llm_service(llm_service)

    if llm_service == "claude":
        client = _anthropic_client()
        response = create_anthropic_message(
            client,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        _emit_invoke_usage(llm_service, model, response, "trial_match.aggregation")
        return "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text" and hasattr(block, "text")
        ).strip()

    client = _openai_client()
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    _emit_invoke_usage(llm_service, model, response, "trial_match.aggregation")
    return response.choices[0].message.content.strip()


def complete_json_object(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    llm_service: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> dict:
    llm_service = resolve_compose_llm_service(llm_service)
    text = complete_text(
        system_prompt,
        user_prompt,
        model=model,
        llm_service=llm_service,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = _strip_json_fences(text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")
    return parsed
