"""Tiny Gemini (Google GenAI) client wrapper.

This provides a minimal synchronous client with a generate(...) method that
mirrors the previous HuggingFaceClient API used by the backend modules.

It expects the GEMINI_API_KEY to be available in the environment. The
implementation uses the official `google-genai` package when available and
falls back to raising a helpful error if not installed.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from google import genai
from google.genai import types
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep_log,
)

from backend.config import DEFAULT_MODEL
from backend.llm_base import LLMClient

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration (tuneable via env vars)
# ---------------------------------------------------------------------------
GEMINI_MAX_RETRIES = int(os.environ.get("GEMINI_MAX_RETRIES", "3"))
GEMINI_BACKOFF_MIN = float(os.environ.get("GEMINI_BACKOFF_MIN", "1"))  # seconds
GEMINI_BACKOFF_MAX = float(os.environ.get("GEMINI_BACKOFF_MAX", "60"))  # seconds


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors that are safe to retry.

    Retries on:
    - Rate-limit (429) and server errors (5xx) from the GenAI SDK
    - Connection / timeout errors (OSError family)
    Non-retryable: validation errors, auth errors (401/403), etc.
    """
    exc_str = str(exc).lower()

    # google-genai SDK wraps HTTP errors; look for status codes in the message
    if "429" in exc_str or "rate limit" in exc_str or "resource_exhausted" in exc_str or "resource exhausted" in exc_str:
        return True
    if any(code in exc_str for code in ("500", "502", "503", "504")):
        return True

    # Network-level transient errors
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True

    return False

class GeminiClient(LLMClient):
    """Minimal client for Google Gemini (GenAI).

    - If `api_key` is provided it should be set in the environment prior to
      creating the underlying client (the GenAI SDK reads it from env).
    - The generate(...) method returns a single string with the model output.
    """

    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = DEFAULT_MODEL):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.default_model = default_model

        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not found. Set it as an environment variable "
                "or pass api_key= to GeminiClient()."
            )

        # Pass the API key directly to the client instead of leaking it
        # into os.environ, which would be visible to child processes and
        # any library that inspects the environment.
        try:
            self._client = genai.Client(api_key=self.api_key)
        except Exception as exc:
            raise RuntimeError("Failed to initialize GenAI client: %s" % exc)

    def generate(self, prompt: str, model: Optional[str] = None, max_tokens: int = 512, temperature: float = 0.0) -> str:
        """Generate text for the given prompt (with automatic retry on transient failures)."""
        model_id = model or self.default_model
        if not model_id:
            raise ValueError("model must be provided either via constructor or argument")

        @retry(
            stop=stop_after_attempt(GEMINI_MAX_RETRIES),
            wait=wait_exponential(min=GEMINI_BACKOFF_MIN, max=GEMINI_BACKOFF_MAX),
            retry=retry_if_exception(_is_retryable),
            before_sleep=before_sleep_log(LOG, logging.WARNING),
            reraise=True,
        )
        def _call() -> str:
            config = types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
            response = self._client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=config,
            )
            return response.text or ""

        try:
            return _call()
        except Exception as exc:
            raise RuntimeError(f"Gemini API error: {exc}")

    def generate_stream(self, prompt: str, model: Optional[str] = None, max_tokens: int = 512, temperature: float = 0.0):
        """Generate text for the given prompt, yielding chunks as they arrive.

        The initial API call (which opens the streaming connection) is retried
        with exponential back-off on transient failures.  Once chunks start
        flowing, a mid-stream error is surfaced immediately (no retry).
        """
        model_id = model or self.default_model
        if not model_id:
            raise ValueError("model must be provided either via constructor or argument")

        @retry(
            stop=stop_after_attempt(GEMINI_MAX_RETRIES),
            wait=wait_exponential(min=GEMINI_BACKOFF_MIN, max=GEMINI_BACKOFF_MAX),
            retry=retry_if_exception(_is_retryable),
            before_sleep=before_sleep_log(LOG, logging.WARNING),
            reraise=True,
        )
        def _open_stream():
            config = types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
            return self._client.models.generate_content_stream(
                model=model_id,
                contents=prompt,
                config=config,
            )

        try:
            response_stream = _open_stream()
        except Exception as exc:
            raise RuntimeError(f"Gemini API streaming error: {exc}")

        try:
            for chunk in response_stream:
                if hasattr(chunk, "text") and chunk.text:
                    yield chunk.text
                elif hasattr(chunk, "parts") and chunk.parts:
                    for part in chunk.parts:
                        if hasattr(part, "text"):
                            yield part.text
        except Exception as exc:
            raise RuntimeError(f"Gemini API streaming error: {exc}")


__all__ = ["GeminiClient"]
