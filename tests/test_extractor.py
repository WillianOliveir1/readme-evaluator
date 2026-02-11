"""Tests for backend.evaluate.extractor — LLM factory is mocked."""
from __future__ import annotations

import json
import copy
import pytest
from unittest.mock import patch, MagicMock

from backend.evaluate.extractor import extract_json_from_readme
from backend.evaluate.progress import EvaluationResult, ProgressStage


# =====================================================================
# Helpers
# =====================================================================

def _valid_model_output(evaluation: dict) -> str:
    """Wrap a dict in the kind of string the model typically returns."""
    return json.dumps(evaluation, ensure_ascii=False, indent=2)


def _valid_model_output_with_backticks(evaluation: dict) -> str:
    """Model sometimes wraps JSON in markdown backticks."""
    return "```json\n" + json.dumps(evaluation, ensure_ascii=False) + "\n```"


# =====================================================================
# Without model (prompt-only mode)
# =====================================================================

class TestExtractorPromptOnly:
    """When model=None, only the prompt should be built."""

    def test_returns_evaluation_result(self, schema_path, sample_readme):
        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model=None,
        )
        assert isinstance(result, EvaluationResult)
        assert result.success is True
        assert len(result.prompt) > 0
        assert result.model_output is None
        assert result.parsed is None

    def test_prompt_contains_readme(self, schema_path, sample_readme):
        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model=None,
        )
        assert "My Project" in result.prompt

    def test_prompt_contains_schema(self, schema_path, sample_readme):
        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model=None,
        )
        assert "properties" in result.prompt

    def test_progress_history_populated(self, schema_path, sample_readme):
        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model=None,
        )
        stages = [u.stage for u in result.progress_history]
        assert ProgressStage.BUILDING_PROMPT in stages
        assert ProgressStage.COMPLETED in stages

    def test_timing_has_prompt_build(self, schema_path, sample_readme):
        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model=None,
        )
        assert "prompt_build" in result.timing
        assert result.timing["prompt_build"] >= 0


# =====================================================================
# With model (mocked Gemini)
# =====================================================================

class TestExtractorWithModel:
    """When model is provided, the LLM factory is mocked."""

    @patch("backend.evaluate.extractor.get_llm_client")
    def test_valid_json_parsed_and_validated(
        self, mock_factory, schema_path, sample_readme, minimal_evaluation
    ):
        raw = _valid_model_output(minimal_evaluation)
        instance = mock_factory.return_value
        instance.generate_stream.return_value = iter([raw])

        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model="gemini-test",
        )
        assert result.success is True
        assert result.parsed is not None
        assert result.model_output == raw
        assert result.validation_ok is True

    @patch("backend.evaluate.extractor.get_llm_client")
    def test_backtick_wrapped_json_parsed(
        self, mock_factory, schema_path, sample_readme, minimal_evaluation
    ):
        raw = _valid_model_output_with_backticks(minimal_evaluation)
        instance = mock_factory.return_value
        instance.generate_stream.return_value = iter([raw])

        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model="gemini-test",
        )
        assert result.parsed is not None

    @patch("backend.evaluate.extractor.get_llm_client")
    def test_invalid_json_gives_none_parsed(
        self, mock_factory, schema_path, sample_readme
    ):
        instance = mock_factory.return_value
        instance.generate_stream.return_value = iter(["this is not json {{{"])

        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model="gemini-test",
        )
        assert result.parsed is None
        assert len(result.recovery_suggestions) > 0

    @patch("backend.evaluate.extractor.get_llm_client")
    def test_empty_response_handled(
        self, mock_factory, schema_path, sample_readme
    ):
        instance = mock_factory.return_value
        instance.generate_stream.return_value = iter([""])

        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model="gemini-test",
        )
        assert result.parsed is None
        assert len(result.recovery_suggestions) > 0

    @patch("backend.evaluate.extractor.get_llm_client")
    def test_model_exception_handled(
        self, mock_factory, schema_path, sample_readme
    ):
        instance = mock_factory.return_value
        instance.generate_stream.side_effect = RuntimeError("API down")

        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model="gemini-test",
        )
        assert len(result.recovery_suggestions) > 0

    @patch("backend.evaluate.extractor.get_llm_client")
    def test_progress_callback_invoked(
        self, mock_factory, schema_path, sample_readme, minimal_evaluation
    ):
        raw = _valid_model_output(minimal_evaluation)
        instance = mock_factory.return_value
        instance.generate_stream.return_value = iter([raw])

        received = []
        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model="gemini-test",
            progress_callback=lambda u: received.append(u),
        )
        assert len(received) > 0

    @patch("backend.evaluate.extractor.get_llm_client")
    def test_metadata_injection(
        self, mock_factory, schema_path, sample_readme, minimal_evaluation
    ):
        """owner, repo, readme_raw_link should be injected into metadata."""
        # Clear metadata fields so the extractor will inject them
        # (the code only overwrites empty / "N/A" values)
        evaluation = copy.deepcopy(minimal_evaluation)
        evaluation["metadata"]["repository_link"] = "N/A"
        evaluation["metadata"]["readme_raw_link"] = "N/A"
        evaluation["metadata"]["repository_name"] = "N/A"

        raw = _valid_model_output(evaluation)
        instance = mock_factory.return_value
        instance.generate_stream.return_value = iter([raw])

        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model="gemini-test",
            owner="test-owner",
            repo="test-repo",
            readme_raw_link="https://example.com/README.md",
        )
        meta = result.parsed["metadata"]
        assert meta["repository_owner"] == "test-owner"
        assert meta["repository_name"] == "test-repo"
        assert meta["repository_link"] == "https://github.com/test-owner/test-repo"
        assert meta["readme_raw_link"] == "https://example.com/README.md"
        assert meta["evaluator"] == "gemini-test"
        assert meta["evaluation_date"]  # should be set

    @patch("backend.evaluate.extractor.get_llm_client")
    def test_postprocessing_applied(
        self, mock_factory, schema_path, sample_readme, minimal_evaluation
    ):
        """String arrays in model output should be converted to lists."""
        broken = copy.deepcopy(minimal_evaluation)
        broken["categories"]["what"]["justifications"] = "a single string"

        raw = _valid_model_output(broken)
        instance = mock_factory.return_value
        instance.generate_stream.return_value = iter([raw])

        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model="gemini-test",
        )
        # Should have been fixed to a list
        assert isinstance(result.parsed["categories"]["what"]["justifications"], list)


# =====================================================================
# Schema validation
# =====================================================================

class TestExtractorValidation:
    """Test that validation results are correctly reported."""

    @patch("backend.evaluate.extractor.get_llm_client")
    def test_validation_failure_reported(
        self, mock_factory, schema_path, sample_readme
    ):
        """A JSON that doesn't match the schema should set validation_ok=False."""
        bad_json = {"metadata": {}, "wrong_key": True}
        raw = json.dumps(bad_json)
        instance = mock_factory.return_value
        instance.generate_stream.return_value = iter([raw])

        result = extract_json_from_readme(
            readme_text=sample_readme,
            schema_path=schema_path,
            model="gemini-test",
        )
        assert result.parsed is not None
        assert result.validation_ok is False
        assert result.validation_errors is not None
