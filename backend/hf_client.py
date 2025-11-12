"""Tiny Hugging Face client wrapper for text generation.

This module provides a minimal synchronous client that calls the Hugging Face
Inference API using the standard REST endpoint. It expects an API token to be
available via the HUGGINGFACE_API_TOKEN environment variable (or passed to the
constructor). The code intentionally keeps dependencies minimal and uses
`requests` which is already listed in `backend/requirements.txt`.

Usage:
    from backend.hf_client import HuggingFaceClient
    client = HuggingFaceClient()
    text = client.generate("Hello world", model="qwen/qwen-2.5-7b-instruct")

Notes:
    - This is scaffolding for future integration. For production / high-throughput
      usage you may prefer the official SDK, streaming, async httpx usage, or
      running a local inference server.
"""
from __future__ import annotations

import os
from typing import Optional

import requests


# Try to import the higher-level Hugging Face client when available. We will
# prefer it because it knows the correct endpoints and payload formats.
try:
    from huggingface_hub import InferenceClient
except Exception:
    InferenceClient = None


class HuggingFaceClient:
    """Minimal client for Hugging Face Inference API.

    Parameters
    - token: optional API token (falls back to HUGGINGFACE_API_TOKEN env var)
    - default_model: default model id to call (user can override per request)
    """

    # The legacy API base (api-inference.huggingface.co/models) has been
    # replaced by the router endpoint. Use the router integration which
    # forwards requests to the appropriate inference backend.
    # Use the router hf-inference endpoint and include the /models prefix so
    # the full request URL becomes: {HF_API_BASE}/{owner}/{model}
    HF_API_BASE = "https://router.huggingface.co/hf-inference/models"

    def __init__(self, token: Optional[str] = None, default_model: Optional[str] = "Qwen/Qwen2.5-7B-Instruct"):
        self.token = token or os.environ.get("HUGGINGFACE_API_TOKEN")
        self.default_model = default_model

    def _get_headers(self) -> dict:
        if not self.token:
            raise RuntimeError("HUGGINGFACE_API_TOKEN is not set")
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def generate(self, prompt: str, model: Optional[str] = None, max_tokens: int = 512, temperature: float = 0.0, top_p: float = 1.0) -> str:
        """Generate text from a prompt.

        Returns the generated text (string). Raises RuntimeError on API errors.
        """
        model_id = model or self.default_model
        if not model_id:
            raise ValueError("model must be provided either via constructor or argument")

        # First, try using the official huggingface_hub InferenceClient if
        # available. This client handles router vs api endpoints internally and
        # generally provides better compatibility across models.
        if InferenceClient is not None:
            try:
                hf_client = InferenceClient(token=self.token)
                # The InferenceClient.text_generation signature expects the
                # prompt as the first arg and generation params as keyword
                # arguments. Provide model and common parameters directly.
                out = hf_client.text_generation(
                    prompt,
                    model=model_id,
                    max_new_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    return_full_text=False,
                    stream=False,
                )

                # The return type can vary across versions: string, dict,
                # list, or a typed object. Normalize common shapes to string.
                if isinstance(out, str):
                    return out
                # object-like with attribute
                if hasattr(out, "generated_text"):
                    return getattr(out, "generated_text")
                if hasattr(out, "text"):
                    return getattr(out, "text")
                if isinstance(out, dict):
                    if "generated_text" in out:
                        return out["generated_text"]
                    if "generated_texts" in out and out["generated_texts"]:
                        return out["generated_texts"][0]
                if isinstance(out, list) and out:
                    first = out[0]
                    if isinstance(first, dict) and "generated_text" in first:
                        return first["generated_text"]
                    if isinstance(first, str):
                        return first
            except Exception:
                # if the high-level client fails for any reason, fall back to
                # the HTTP router approach below. We'll not fail loudly here
                # to preserve the fallback path.
                pass

        # Fallback: issue a raw HTTP POST to the router/models endpoint. Keep
        # this as a lower-level backup for environments where huggingface_hub
        # isn't installed.
        url = f"{self.HF_API_BASE}/{model_id}"
        headers = self._get_headers()
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
            },
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.status_code >= 400:
            # surface helpful message
            raise RuntimeError(f"Hugging Face API error {resp.status_code}: {resp.text}")

        # HF sometimes returns dict with 'generated_text' or a list of objects.
        try:
            data = resp.json()
        except ValueError:
            return resp.text

        # common shapes: {"generated_text": "..."} or [{"generated_text": "..."}]
        if isinstance(data, dict) and "generated_text" in data:
            return data["generated_text"]
        if isinstance(data, list) and data and isinstance(data[0], dict) and "generated_text" in data[0]:
            return data[0]["generated_text"]

        # if the model returns plain text or another shape, fallback to text
        return resp.text


__all__ = ["HuggingFaceClient"]
