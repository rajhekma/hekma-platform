"""Fire-and-forget LLM usage reporter. Canonical copy is ai-usage/backend/hekma_ai_usage."""

from .client import emit_llm_usage, llm_usage_scope, current_usage_context

__all__ = ["emit_llm_usage", "llm_usage_scope", "current_usage_context"]
