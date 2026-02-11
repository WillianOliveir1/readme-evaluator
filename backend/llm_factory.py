"""LLM provider factory — returns the right client based on configuration.

The provider is selected by the ``LLM_PROVIDER`` environment variable:

- ``gemini``  (default) — uses the Gemini (Google GenAI) SDK
- ``ollama``            — calls a local Ollama instance

Callers should use ``get_llm_client()`` instead of instantiating
``GeminiClient`` / ``OllamaClient`` directly so the provider can be
swapped by configuration alone.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from backend.llm_base import LLMClient

LOG = logging.getLogger(__name__)

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower().strip()


def get_llm_client(
    *,
    provider: Optional[str] = None,
    default_model: Optional[str] = None,
) -> LLMClient:
    """Instantiate and return the configured LLM client.

    Parameters
    ----------
    provider : str | None
        Override ``LLM_PROVIDER`` env var for this call.
    default_model : str | None
        Override the provider's default model for this instance.
    """
    prov = (provider or LLM_PROVIDER).lower().strip()

    if prov == "gemini":
        from backend.gemini_client import GeminiClient
        kwargs: dict = {}
        if default_model:
            kwargs["default_model"] = default_model
        return GeminiClient(**kwargs)

    if prov == "ollama":
        from backend.ollama_client import OllamaClient
        kwargs = {}
        if default_model:
            kwargs["default_model"] = default_model
        return OllamaClient(**kwargs)

    raise ValueError(
        f"Unknown LLM_PROVIDER '{prov}'. "
        "Supported values: gemini, ollama"
    )


__all__ = ["get_llm_client", "LLM_PROVIDER"]
