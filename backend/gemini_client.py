"""Tiny Gemini (Google GenAI) client wrapper.

This provides a minimal synchronous client with a generate(...) method that
mirrors the previous HuggingFaceClient API used by the backend modules.

It expects the GEMINI_API_KEY to be available in the environment. The
implementation uses the official `google-genai` package when available and
falls back to raising a helpful error if not installed.
"""
from __future__ import annotations

import os
from typing import Optional
from google import genai
from google.genai import types
from backend.config import DEFAULT_MODEL

class GeminiClient:
    """Minimal client for Google Gemini (GenAI).

    - If `api_key` is provided it should be set in the environment prior to
      creating the underlying client (the GenAI SDK reads it from env).
    - The generate(...) method returns a single string with the model output.
    """

    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = DEFAULT_MODEL):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.default_model = default_model

        # The GenAI client will read configuration (like API key) from the
        # environment by default. If an explicit API key was passed, ensure it
        # is available to the library.
        if self.api_key:
            # setenv is safe here for the current process
            os.environ["GEMINI_API_KEY"] = self.api_key

        # instantiate client (the SDK may accept configuration in different
        # ways across versions; creating a client object is the pattern used
        # in our small test harness).
        try:
            self._client = genai.Client()
        except Exception as exc:
            raise RuntimeError("Failed to initialize GenAI client: %s" % exc)

    def generate(self, prompt: str, model: Optional[str] = None, max_tokens: int = 512, temperature: float = 0.0) -> str:
        """Generate text for the given prompt."""
        model_id = model or self.default_model
        if not model_id:
            raise ValueError("model must be provided either via constructor or argument")

        try:
            config = types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature
            )
            
            response = self._client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=config
            )
            return response.text
        except Exception as exc:
            raise RuntimeError(f"Gemini API error: {exc}")

    def generate_stream(self, prompt: str, model: Optional[str] = None, max_tokens: int = 512, temperature: float = 0.0):
        """Generate text for the given prompt, yielding chunks of text as they are generated."""
        model_id = model or self.default_model
        if not model_id:
            raise ValueError("model must be provided either via constructor or argument")

        try:
            config = types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature
            )
            
            response_stream = self._client.models.generate_content_stream(
                model=model_id,
                contents=prompt,
                config=config
            )
            
            for chunk in response_stream:
                if hasattr(chunk, "text") and chunk.text:
                    yield chunk.text
                elif hasattr(chunk, "parts"):
                     for part in chunk.parts:
                         if hasattr(part, "text"):
                             yield part.text
        except Exception as exc:
            raise RuntimeError(f"Gemini API streaming error: {exc}")


__all__ = ["GeminiClient"]
