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

try:
    from google import genai
except Exception:  # pragma: no cover - runtime dependency may be missing in some envs
    genai = None


class GeminiClient:
    """Minimal client for Google Gemini (GenAI).

    - If `api_key` is provided it should be set in the environment prior to
      creating the underlying client (the GenAI SDK reads it from env).
    - The generate(...) method returns a single string with the model output.
    """

    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.default_model = default_model

        if genai is None:
            raise RuntimeError("google-genai package is not installed. Install 'google-genai' to use GeminiClient.")

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
        """Generate text for the given prompt.

        Returns the generated text as a string. Raises RuntimeError on failure.
        """
        model_id = model or self.default_model
        if not model_id:
            raise ValueError("model must be provided either via constructor or argument")

        try:
            resp = self._client.models.generate_content(model=model_id, contents=prompt)
        except Exception as exc:
            raise RuntimeError(f"Gemini API error: {exc}")

        # The SDK response shapes can vary across versions. Prefer a `.text`
        # attribute if present (used in our test harness). Otherwise, try
        # common fallbacks like .output or converting to str().
        if hasattr(resp, "text"):
            return getattr(resp, "text")
        if hasattr(resp, "output"):
            out = getattr(resp, "output")
            try:
                # if output is a structured object, try to extract text
                if isinstance(out, (list, tuple)) and out:
                    first = out[0]
                    if isinstance(first, dict) and "text" in first:
                        return first["text"]
                return str(out)
            except Exception:
                return str(out)

        return str(resp)


__all__ = ["GeminiClient"]
