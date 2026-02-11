"""Tests for backend.gemini_client — retry logic and error handling.

The google-genai client is mocked so tests run offline.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from backend.gemini_client import GeminiClient, _is_retryable


# =====================================================================
# _is_retryable helper
# =====================================================================

class TestIsRetryable:

    def test_rate_limit_429(self):
        assert _is_retryable(RuntimeError("status 429 too many requests"))

    def test_rate_limit_resource_exhausted(self):
        assert _is_retryable(RuntimeError("RESOURCE_EXHAUSTED"))

    def test_server_500(self):
        assert _is_retryable(RuntimeError("500 Internal Server Error"))

    def test_server_503(self):
        assert _is_retryable(RuntimeError("503 Service Unavailable"))

    def test_connection_error(self):
        assert _is_retryable(ConnectionError("reset by peer"))

    def test_timeout_error(self):
        assert _is_retryable(TimeoutError("timed out"))

    def test_os_error(self):
        assert _is_retryable(OSError("network unreachable"))

    def test_auth_error_not_retryable(self):
        assert not _is_retryable(RuntimeError("401 Unauthorized"))

    def test_validation_error_not_retryable(self):
        assert not _is_retryable(ValueError("invalid input"))

    def test_generic_error_not_retryable(self):
        assert not _is_retryable(RuntimeError("something unexpected"))


# =====================================================================
# GeminiClient.__init__
# =====================================================================

class TestGeminiClientInit:

    @patch("backend.gemini_client.genai")
    def test_requires_api_key(self, mock_genai):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("GEMINI_API_KEY", None)
            with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
                GeminiClient(api_key=None)

    @patch("backend.gemini_client.genai")
    def test_explicit_api_key(self, mock_genai):
        client = GeminiClient(api_key="test-key")
        mock_genai.Client.assert_called_once_with(api_key="test-key")
        assert client.api_key == "test-key"


# =====================================================================
# generate() with retries
# =====================================================================

class TestGenerateRetry:

    @patch("backend.gemini_client.genai")
    def test_success_on_first_try(self, mock_genai):
        mock_response = MagicMock()
        mock_response.text = "Hello world"
        mock_genai.Client.return_value.models.generate_content.return_value = mock_response

        client = GeminiClient(api_key="key")
        result = client.generate("prompt", model="gemini-2.5-flash")
        assert result == "Hello world"

    @patch("backend.gemini_client.GEMINI_BACKOFF_MIN", 0.01)
    @patch("backend.gemini_client.GEMINI_BACKOFF_MAX", 0.02)
    @patch("backend.gemini_client.genai")
    def test_retries_on_429(self, mock_genai):
        """Should retry when a 429 rate limit error occurs."""
        mock_response = MagicMock()
        mock_response.text = "Success after retry"
        api = mock_genai.Client.return_value.models.generate_content
        api.side_effect = [
            RuntimeError("429 Resource Exhausted"),
            mock_response,
        ]

        client = GeminiClient(api_key="key")
        result = client.generate("prompt", model="m")
        assert result == "Success after retry"
        assert api.call_count == 2

    @patch("backend.gemini_client.GEMINI_BACKOFF_MIN", 0.01)
    @patch("backend.gemini_client.GEMINI_BACKOFF_MAX", 0.02)
    @patch("backend.gemini_client.genai")
    def test_retries_on_500(self, mock_genai):
        mock_response = MagicMock()
        mock_response.text = "ok"
        api = mock_genai.Client.return_value.models.generate_content
        api.side_effect = [
            RuntimeError("500 Internal Server Error"),
            mock_response,
        ]

        client = GeminiClient(api_key="key")
        result = client.generate("prompt", model="m")
        assert result == "ok"
        assert api.call_count == 2

    @patch("backend.gemini_client.GEMINI_MAX_RETRIES", 2)
    @patch("backend.gemini_client.GEMINI_BACKOFF_MIN", 0.01)
    @patch("backend.gemini_client.GEMINI_BACKOFF_MAX", 0.02)
    @patch("backend.gemini_client.genai")
    def test_gives_up_after_max_retries(self, mock_genai):
        api = mock_genai.Client.return_value.models.generate_content
        api.side_effect = RuntimeError("503 Service Unavailable")

        client = GeminiClient(api_key="key")
        with pytest.raises(RuntimeError, match="Gemini API error"):
            client.generate("prompt", model="m")
        assert api.call_count == 2

    @patch("backend.gemini_client.genai")
    def test_no_retry_on_auth_error(self, mock_genai):
        api = mock_genai.Client.return_value.models.generate_content
        api.side_effect = RuntimeError("401 Unauthorized - invalid API key")

        client = GeminiClient(api_key="key")
        with pytest.raises(RuntimeError, match="Gemini API error"):
            client.generate("prompt", model="m")
        # Should fail immediately — no retries
        assert api.call_count == 1


# =====================================================================
# generate_stream() with retries
# =====================================================================

class TestGenerateStreamRetry:

    @patch("backend.gemini_client.genai")
    def test_stream_success(self, mock_genai):
        chunk1, chunk2 = MagicMock(), MagicMock()
        chunk1.text = "Hello "
        chunk2.text = "world"
        mock_genai.Client.return_value.models.generate_content_stream.return_value = [chunk1, chunk2]

        client = GeminiClient(api_key="key")
        result = "".join(client.generate_stream("prompt", model="m"))
        assert result == "Hello world"

    @patch("backend.gemini_client.GEMINI_BACKOFF_MIN", 0.01)
    @patch("backend.gemini_client.GEMINI_BACKOFF_MAX", 0.02)
    @patch("backend.gemini_client.genai")
    def test_stream_retries_on_rate_limit(self, mock_genai):
        chunk = MagicMock()
        chunk.text = "ok"
        api = mock_genai.Client.return_value.models.generate_content_stream
        api.side_effect = [
            RuntimeError("429 rate limit exceeded"),
            [chunk],
        ]

        client = GeminiClient(api_key="key")
        result = "".join(client.generate_stream("prompt", model="m"))
        assert result == "ok"
        assert api.call_count == 2

    def test_model_required(self):
        with patch("backend.gemini_client.genai"):
            client = GeminiClient(api_key="key", default_model=None)
            with pytest.raises(ValueError, match="model must be provided"):
                list(client.generate_stream("prompt", model=None))
