"""Tests for backend.llm_factory — factory function returning the right client."""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

from backend.llm_factory import get_llm_client
from backend.llm_base import LLMClient


# =====================================================================
# get_llm_client
# =====================================================================

class TestGetLlmClient:
    """Unit tests for the get_llm_client factory."""

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    @patch("backend.llm_factory.LLM_PROVIDER", "gemini")
    @patch("backend.gemini_client.genai")
    def test_default_returns_gemini(self, mock_genai):
        """Default provider (gemini) returns GeminiClient."""
        mock_genai.Client.return_value = MagicMock()
        client = get_llm_client()
        from backend.gemini_client import GeminiClient
        assert isinstance(client, GeminiClient)
        assert isinstance(client, LLMClient)

    @patch("backend.llm_factory.LLM_PROVIDER", "ollama")
    def test_ollama_returns_ollama_client(self):
        """Provider 'ollama' returns OllamaClient."""
        client = get_llm_client(provider="ollama")
        from backend.ollama_client import OllamaClient
        assert isinstance(client, OllamaClient)
        assert isinstance(client, LLMClient)

    def test_explicit_provider_overrides_env(self):
        """Provider kwarg takes precedence over env var."""
        client = get_llm_client(provider="ollama")
        from backend.ollama_client import OllamaClient
        assert isinstance(client, OllamaClient)

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    @patch("backend.gemini_client.genai")
    def test_explicit_gemini_provider(self, mock_genai):
        mock_genai.Client.return_value = MagicMock()
        client = get_llm_client(provider="gemini")
        from backend.gemini_client import GeminiClient
        assert isinstance(client, GeminiClient)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
            get_llm_client(provider="openai")

    def test_case_insensitive_provider(self):
        client = get_llm_client(provider="OLLAMA")
        from backend.ollama_client import OllamaClient
        assert isinstance(client, OllamaClient)

    def test_whitespace_trimmed(self):
        client = get_llm_client(provider="  ollama  ")
        from backend.ollama_client import OllamaClient
        assert isinstance(client, OllamaClient)

    def test_default_model_forwarded_to_ollama(self):
        client = get_llm_client(provider="ollama", default_model="codellama")
        assert client.default_model == "codellama"

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    @patch("backend.gemini_client.genai")
    def test_default_model_forwarded_to_gemini(self, mock_genai):
        mock_genai.Client.return_value = MagicMock()
        client = get_llm_client(provider="gemini", default_model="gemini-2.0")
        assert client.default_model == "gemini-2.0"
