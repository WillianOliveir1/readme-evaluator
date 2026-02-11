"""Tests for backend.present.renderer — LLM factory is mocked."""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock

from backend.present.renderer import render_from_json


# =====================================================================
# Without model (fallback mode)
# =====================================================================

class TestRendererFallback:
    """When model=None, a simple key:value rendering is returned."""

    def test_returns_dict(self):
        result = render_from_json({"key": "value"}, model=None)
        assert isinstance(result, dict)
        assert "text" in result
        assert "prompt" in result

    def test_text_contains_keys(self):
        data = {"score": 4, "name": "test"}
        result = render_from_json(data, model=None)
        assert "score" in result["text"]
        assert "name" in result["text"]

    def test_prompt_built_with_json(self):
        data = {"hello": "world"}
        result = render_from_json(data, model=None)
        assert "hello" in result["prompt"]
        assert "world" in result["prompt"]

    def test_no_model_output_key(self):
        result = render_from_json({"a": 1}, model=None)
        assert "model_output" not in result

    def test_style_instructions_in_prompt(self):
        result = render_from_json({"a": 1}, style_instructions="Be concise", model=None)
        assert "Be concise" in result["prompt"]


# =====================================================================
# With model (mocked Gemini)
# =====================================================================

class TestRendererWithModel:
    """When a model is provided, the LLM factory is mocked."""

    @patch("backend.present.renderer.get_llm_client")
    def test_model_output_returned(self, mock_factory):
        instance = mock_factory.return_value
        instance.generate.return_value = "# Report\n\nGreat documentation!"

        result = render_from_json(
            {"score": 5},
            model="gemini-test",
        )
        assert result["text"] == "# Report\n\nGreat documentation!"
        assert result["model_output"] == "# Report\n\nGreat documentation!"

    @patch("backend.present.renderer.get_llm_client")
    def test_prompt_includes_json_data(self, mock_factory):
        instance = mock_factory.return_value
        instance.generate.return_value = "rendered"

        data = {"categories": {"what": {"score": 4}}}
        result = render_from_json(data, model="gemini-test")
        assert "categories" in result["prompt"]

    @patch("backend.present.renderer.get_llm_client")
    def test_generate_called_with_correct_params(self, mock_factory):
        instance = mock_factory.return_value
        instance.generate.return_value = "ok"

        render_from_json(
            {"a": 1},
            model="gemini-test",
            max_tokens=1024,
            temperature=0.5,
        )
        call_args = instance.generate.call_args
        assert call_args.kwargs.get("model") == "gemini-test" or call_args[1].get("model") == "gemini-test"
        assert call_args.kwargs.get("max_tokens") == 1024 or call_args[1].get("max_tokens") == 1024

    @patch("backend.present.renderer.get_llm_client")
    def test_style_instructions_passed_to_prompt(self, mock_factory):
        instance = mock_factory.return_value
        instance.generate.return_value = "styled"

        result = render_from_json(
            {"a": 1},
            style_instructions="Use bullet points",
            model="gemini-test",
        )
        assert "Use bullet points" in result["prompt"]


# =====================================================================
# Complex evaluation data
# =====================================================================

class TestRendererWithEvaluation:
    """Test with a realistic evaluation structure."""

    def test_full_evaluation_renders(self, minimal_evaluation):
        result = render_from_json(minimal_evaluation, model=None)
        assert "text" in result
        assert len(result["text"]) > 0

    @patch("backend.present.renderer.get_llm_client")
    def test_full_evaluation_with_model(self, mock_factory, minimal_evaluation):
        instance = mock_factory.return_value
        instance.generate.return_value = "## Full Report\nExcellent README."

        result = render_from_json(minimal_evaluation, model="gemini-test")
        assert "Full Report" in result["text"]
