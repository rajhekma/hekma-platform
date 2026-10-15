"""
Central LLM defaults for API workflows and compose services.

Override via environment:
  WORKFLOW_DEFAULT_MODEL       (default: claude-sonnet-4-6)
  WORKFLOW_DEFAULT_LLM_SERVICE (default: claude)
  COMPOSE_LLM_MODEL            (falls back to WORKFLOW_DEFAULT_MODEL)
  COMPOSE_LLM_SERVICE          (falls back to WORKFLOW_DEFAULT_LLM_SERVICE)
"""

import os

DEFAULT_WORKFLOW_MODEL = os.getenv("WORKFLOW_DEFAULT_MODEL", "claude-sonnet-4-6")
DEFAULT_WORKFLOW_LLM_SERVICE = os.getenv("WORKFLOW_DEFAULT_LLM_SERVICE", "claude")

DEFAULT_COMPOSE_MODEL = os.getenv("COMPOSE_LLM_MODEL", DEFAULT_WORKFLOW_MODEL)
DEFAULT_COMPOSE_LLM_SERVICE = os.getenv("COMPOSE_LLM_SERVICE", DEFAULT_WORKFLOW_LLM_SERVICE)


def resolve_workflow_model(model: str | None) -> str:
    return (model or "").strip() or DEFAULT_WORKFLOW_MODEL


def resolve_workflow_llm_service(llm_service: str | None) -> str:
    return (llm_service or "").strip() or DEFAULT_WORKFLOW_LLM_SERVICE


def resolve_compose_model(model: str | None = None) -> str:
    return (model or "").strip() or DEFAULT_COMPOSE_MODEL


def resolve_compose_llm_service(llm_service: str | None = None) -> str:
    return (llm_service or "").strip() or DEFAULT_COMPOSE_LLM_SERVICE
