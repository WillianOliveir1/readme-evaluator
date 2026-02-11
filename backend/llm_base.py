"""Abstract base class for LLM clients.

Every LLM backend (Gemini, Ollama, OpenAI-compatible, …) must implement
this thin interface so the rest of the codebase stays provider-agnostic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Optional


class LLMClient(ABC):
    """Minimal contract that all LLM backends must satisfy."""

    default_model: Optional[str]

    @abstractmethod
    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> str:
        """Return the full model response as a single string."""

    @abstractmethod
    def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> Iterator[str]:
        """Yield response chunks as they arrive."""


__all__ = ["LLMClient"]
