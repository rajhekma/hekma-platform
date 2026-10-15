"""Anthropic Messages.create compat for SDKs that reject temperature."""

from __future__ import annotations

from typing import Any


def create_anthropic_message(client: Any, **kwargs: Any) -> Any:
    """
    Call client.messages.create without temperature.

    Claude Sonnet 4.x + newer anthropic packages raise:
    TypeError: Messages.create() got an unexpected keyword argument 'temperature'
    """
    kwargs.pop("temperature", None)
    return client.messages.create(**kwargs)
