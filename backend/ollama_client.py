"""Ollama client — talk to local LLMs via the Ollama HTTP API.

Ollama exposes an OpenAI-compatible API on ``http://localhost:11434`` by
default.  This client uses ``requests`` (already in the dependency tree)
to call the ``/api/generate`` endpoint, with retry logic identical to
``GeminiClient``.

Configuration (environment variables):
    OLLAMA_BASE_URL   – default ``http://localhost:11434``
    OLLAMA_MODEL      – default model name, e.g. ``llama3``, ``mistral``
"""
from __future__ import annotations

import json
import logging
import os
from typing import Iterator, Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep_log,
)

from backend.llm_base import LLMClient

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
OLLAMA_MAX_RETRIES = int(os.environ.get("OLLAMA_MAX_RETRIES", "3"))
OLLAMA_BACKOFF_MIN = float(os.environ.get("OLLAMA_BACKOFF_MIN", "1"))
OLLAMA_BACKOFF_MAX = float(os.environ.get("OLLAMA_BACKOFF_MAX", "30"))


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient Ollama errors safe to retry."""
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    exc_str = str(exc).lower()
    if any(code in exc_str for code in ("500", "502", "503", "504", "429")):
        return True
    return False


class OllamaClient(LLMClient):
    """LLM client that calls a local Ollama instance.

    Parameters
    ----------
    base_url : str | None
        Ollama API root (default ``OLLAMA_BASE_URL`` env var).
    default_model : str | None
        Model name to use when none is provided per-call.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
    ):
        self.base_url = (base_url or OLLAMA_BASE_URL).rstrip("/")
        self.default_model = default_model or OLLAMA_DEFAULT_MODEL

    # ------------------------------------------------------------------
    # generate (non-streaming)
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> str:
        model_id = model or self.default_model
        if not model_id:
            raise ValueError("model must be provided either via constructor or argument")

        @retry(
            stop=stop_after_attempt(OLLAMA_MAX_RETRIES),
            wait=wait_exponential(min=OLLAMA_BACKOFF_MIN, max=OLLAMA_BACKOFF_MAX),
            retry=retry_if_exception(_is_retryable),
            before_sleep=before_sleep_log(LOG, logging.WARNING),
            reraise=True,
        )
        def _call() -> str:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model_id,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                    },
                },
                timeout=300,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")

        try:
            return _call()
        except Exception as exc:
            raise RuntimeError(f"Ollama API error: {exc}")

    # ------------------------------------------------------------------
    # generate_stream
    # ------------------------------------------------------------------

    def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> Iterator[str]:
        model_id = model or self.default_model
        if not model_id:
            raise ValueError("model must be provided either via constructor or argument")

        @retry(
            stop=stop_after_attempt(OLLAMA_MAX_RETRIES),
            wait=wait_exponential(min=OLLAMA_BACKOFF_MIN, max=OLLAMA_BACKOFF_MAX),
            retry=retry_if_exception(_is_retryable),
            before_sleep=before_sleep_log(LOG, logging.WARNING),
            reraise=True,
        )
        def _open_stream() -> requests.Response:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model_id,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                    },
                },
                stream=True,
                timeout=300,
            )
            resp.raise_for_status()
            return resp

        try:
            stream_resp = _open_stream()
        except Exception as exc:
            raise RuntimeError(f"Ollama API streaming error: {exc}")

        try:
            for line in stream_resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    token = data.get("response", "")
                    if token:
                        yield token
                    if data.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue
        except Exception as exc:
            raise RuntimeError(f"Ollama API streaming error: {exc}")


__all__ = ["OllamaClient"]
