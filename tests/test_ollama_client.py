"""Tests for backend.ollama_client — OllamaClient with mocked HTTP calls.

All requests to the Ollama HTTP API are mocked so no local Ollama is needed.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock

from backend.ollama_client import OllamaClient, _is_retryable


# =====================================================================
# _is_retryable
# =====================================================================

class TestIsRetryable:
    """Unit tests for the _is_retryable helper function."""

    def test_connection_error(self):
        assert _is_retryable(ConnectionError("refused")) is True

    def test_timeout_error(self):
        assert _is_retryable(TimeoutError("timeout")) is True

    def test_os_error(self):
        assert _is_retryable(OSError("network unreachable")) is True

    def test_requests_connection_error(self):
        import requests
        assert _is_retryable(requests.exceptions.ConnectionError()) is True

    def test_requests_timeout(self):
        import requests
        assert _is_retryable(requests.exceptions.Timeout()) is True

    @pytest.mark.parametrize("code", ["429", "500", "502", "503", "504"])
    def test_retryable_http_status_codes(self, code):
        assert _is_retryable(RuntimeError(f"HTTP {code}")) is True

    def test_non_retryable_value_error(self):
        assert _is_retryable(ValueError("bad input")) is False

    def test_non_retryable_key_error(self):
        assert _is_retryable(KeyError("missing")) is False

    def test_generic_runtime_error(self):
        assert _is_retryable(RuntimeError("something else")) is False


# =====================================================================
# OllamaClient.__init__
# =====================================================================

class TestOllamaClientInit:
    """Constructor tests."""

    def test_defaults_from_env(self):
        client = OllamaClient()
        assert "localhost" in client.base_url or "11434" in client.base_url
        assert client.default_model  # non-empty

    def test_custom_base_url(self):
        client = OllamaClient(base_url="http://gpu-box:11434/")
        assert client.base_url == "http://gpu-box:11434"  # trailing / stripped

    def test_custom_model(self):
        client = OllamaClient(default_model="mistral")
        assert client.default_model == "mistral"


# =====================================================================
# OllamaClient.generate  (non-streaming)
# =====================================================================

class TestOllamaGenerate:
    """Tests for the non-streaming generate method."""

    @patch("backend.ollama_client.requests.post")
    def test_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "Hello from Ollama!"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = OllamaClient(default_model="llama3")
        result = client.generate("Say hello", model="llama3")
        assert result == "Hello from Ollama!"

    @patch("backend.ollama_client.requests.post")
    def test_empty_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = OllamaClient(default_model="llama3")
        result = client.generate("test")
        assert result == ""

    @patch("backend.ollama_client.requests.post")
    def test_custom_parameters_forwarded(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "ok"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = OllamaClient(default_model="llama3")
        client.generate("prompt", model="mistral", max_tokens=1024, temperature=0.7)

        call_json = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert call_json["model"] == "mistral"
        assert call_json["options"]["num_predict"] == 1024
        assert call_json["options"]["temperature"] == 0.7
        assert call_json["stream"] is False

    def test_no_model_raises(self):
        client = OllamaClient()
        client.default_model = ""  # bypass __init__ fallback
        with pytest.raises(ValueError, match="model must be provided"):
            client.generate("test", model=None)

    @patch("backend.ollama_client.OLLAMA_MAX_RETRIES", 1)
    @patch("backend.ollama_client.OLLAMA_BACKOFF_MIN", 0.01)
    @patch("backend.ollama_client.OLLAMA_BACKOFF_MAX", 0.02)
    @patch("backend.ollama_client.requests.post")
    def test_non_retryable_error_raises_immediately(self, mock_post):
        mock_post.side_effect = ValueError("bad input")
        client = OllamaClient(default_model="llama3")
        with pytest.raises(RuntimeError, match="Ollama API error"):
            client.generate("test")
        assert mock_post.call_count == 1

    @patch("backend.ollama_client.OLLAMA_MAX_RETRIES", 2)
    @patch("backend.ollama_client.OLLAMA_BACKOFF_MIN", 0.01)
    @patch("backend.ollama_client.OLLAMA_BACKOFF_MAX", 0.02)
    @patch("backend.ollama_client.requests.post")
    def test_retryable_error_retries(self, mock_post):
        mock_post.side_effect = ConnectionError("refused")
        client = OllamaClient(default_model="llama3")
        with pytest.raises(RuntimeError, match="Ollama API error"):
            client.generate("test")
        assert mock_post.call_count == 2  # 1 original + 1 retry


# =====================================================================
# OllamaClient.generate_stream
# =====================================================================

class TestOllamaGenerateStream:
    """Tests for the streaming generate_stream method."""

    @patch("backend.ollama_client.requests.post")
    def test_stream_yields_tokens(self, mock_post):
        lines = [
            json.dumps({"response": "Hello", "done": False}),
            json.dumps({"response": " World", "done": False}),
            json.dumps({"response": "", "done": True}),
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)
        mock_post.return_value = mock_resp

        client = OllamaClient(default_model="llama3")
        tokens = list(client.generate_stream("test", model="llama3"))
        assert tokens == ["Hello", " World"]

    @patch("backend.ollama_client.requests.post")
    def test_stream_stops_on_done(self, mock_post):
        lines = [
            json.dumps({"response": "token", "done": True}),
            json.dumps({"response": "extra", "done": False}),
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)
        mock_post.return_value = mock_resp

        client = OllamaClient(default_model="llama3")
        tokens = list(client.generate_stream("test"))
        assert tokens == ["token"]

    @patch("backend.ollama_client.requests.post")
    def test_stream_skips_empty_lines(self, mock_post):
        lines = ["", json.dumps({"response": "ok", "done": True}), ""]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)
        mock_post.return_value = mock_resp

        client = OllamaClient(default_model="llama3")
        tokens = list(client.generate_stream("test"))
        assert tokens == ["ok"]

    @patch("backend.ollama_client.requests.post")
    def test_stream_sends_correct_params(self, mock_post):
        lines = [json.dumps({"response": "", "done": True})]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)
        mock_post.return_value = mock_resp

        client = OllamaClient(default_model="llama3")
        list(client.generate_stream("prompt", model="mistral", max_tokens=512))

        call_json = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert call_json["stream"] is True
        assert call_json["model"] == "mistral"

    def test_stream_no_model_raises(self):
        client = OllamaClient()
        client.default_model = ""  # bypass __init__ fallback
        with pytest.raises(ValueError, match="model must be provided"):
            list(client.generate_stream("test", model=None))

    @patch("backend.ollama_client.OLLAMA_MAX_RETRIES", 1)
    @patch("backend.ollama_client.OLLAMA_BACKOFF_MIN", 0.01)
    @patch("backend.ollama_client.OLLAMA_BACKOFF_MAX", 0.02)
    @patch("backend.ollama_client.requests.post")
    def test_stream_connection_error_raises(self, mock_post):
        mock_post.side_effect = ConnectionError("refused")
        client = OllamaClient(default_model="llama3")
        with pytest.raises(RuntimeError, match="Ollama API streaming error"):
            list(client.generate_stream("test"))
