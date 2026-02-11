"""Abstract base class for LLM clients.

Every LLM backend (Gemini, Ollama, OpenAI-compatible, …) must implement
this thin interface so the rest of the codebase stays provider-agnostic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Optional, Dict, Any


@dataclass
class UsageStats:
    """Token usage and cost information returned after generation."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    # Estimated cost in USD (0 for local models)
    estimated_cost_usd: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "model": self.model,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            **{k: v for k, v in self.extra.items()},
        }


class LLMClient(ABC):
    """Minimal contract that all LLM backends must satisfy."""

    default_model: Optional[str]

    # Populated after generate / generate_stream completes
    last_usage: Optional[UsageStats] = None

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


__all__ = ["LLMClient", "UsageStats"]
