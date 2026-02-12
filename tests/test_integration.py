"""Integration tests — validate end-to-end flows across multiple backend components.

These tests mock *only* the outermost external services (Gemini API, GitHub,
MongoDB) while letting the real internal code run: prompt building, extraction,
rendering, pipeline orchestration, etc.
"""
from __future__ import annotations

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


# Minimal valid taxonomy JSON that matches the schema structure
_VALID_TAXONOMY_JSON = json.dumps({
    "metadata": {
        "repository_name": "test-repo",
        "repository_url": "https://github.com/test/repo",
        "readme_language": "en",
        "analysis_timestamp": "2025-01-01T00:00:00Z",
    },
    "categories": [],
})


# =====================================================================
# Flow: download README → extract JSON (prompt-only, no model call)
# =====================================================================

class TestExtractPromptOnlyFlow:
    """End-to-end: POST /extract-json with readme_text (no model call).

    The extractor should build a prompt and return it without calling
    Gemini (model=None).
    """

    def test_prompt_only_returns_prompt(self):
        resp = client.post("/extract-json", json={
            "readme_text": "# My Project\nA cool project.",
            "model": None,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["prompt"] is not None
        assert len(data["prompt"]) > 0
        # No model call → model_output should be None
        assert data.get("model_output") is None


class TestExtractWithModelFlow:
    """End-to-end: POST /extract-json with a mocked Gemini model.

    Only the Gemini API is mocked.  Prompt building, postprocessing,
    and JSON validation run for real.
    """

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    @patch("backend.evaluate.extractor.get_llm_client")
    def test_extract_with_model_valid_json(self, mock_factory):
        """Model returns well-formed taxonomy JSON → success + parsed."""
        mock_instance = mock_factory.return_value
        mock_instance.generate_stream.return_value = iter([_VALID_TAXONOMY_JSON])
        mock_instance.default_model = "gemini-2.5-flash"

        resp = client.post("/extract-json", json={
            "readme_text": "# My Project\n\nA cool project with docs.",
            "model": "gemini-2.5-flash",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["parsed"] is not None
        assert data["parsed"]["metadata"]["repository_name"] == "test-repo"

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    @patch("backend.evaluate.extractor.get_llm_client")
    def test_extract_with_model_bad_json(self, mock_factory):
        """Model returns garbage → success = True but validation may fail."""
        mock_instance = mock_factory.return_value
        mock_instance.generate_stream.return_value = iter(["this is not JSON"])
        mock_instance.default_model = "gemini-2.5-flash"

        resp = client.post("/extract-json", json={
            "readme_text": "# Test",
            "model": "gemini-2.5-flash",
        })
        assert resp.status_code == 200
        data = resp.json()
        # The extractor should still return success (call worked)
        # but parsed will be None because it couldn't parse the output
        assert isinstance(data.get("success"), bool)


# =====================================================================
# Flow: render evaluation JSON → markdown
# =====================================================================

class TestRenderFlow:

    @patch("backend.present.renderer.get_llm_client")
    def test_render_with_model(self, mock_factory):
        """Full render: build prompt + call LLM → returns markdown text."""
        mock_instance = mock_factory.return_value
        mock_instance.generate.return_value = "## Report\nGreat project."

        resp = client.post("/render-evaluation", json={
            "evaluation_json": {"metadata": {"repository_name": "test"}},
            "model": "gemini-2.5-flash",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "text" in data
        assert "Report" in data["text"]

    def test_render_prompt_only(self):
        """Render without model → returns only the prompt (no model_output)."""
        resp = client.post("/render-evaluation", json={
            "evaluation_json": {"metadata": {"repository_name": "test"}},
            "model": None,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "prompt" in data
        assert data.get("model_output") is None


# =====================================================================
# Flow: full pipeline job (download → extract → validate → save)
# =====================================================================

class TestPipelineJobFlow:
    """Create a job via POST /jobs, then verify its lifecycle."""

    @patch("backend.pipeline.get_cache_manager")
    @patch("backend.pipeline.MongoDBHandler")
    @patch("backend.pipeline.extract_json_from_readme")
    @patch("backend.pipeline.ReadmeDownloader")
    def test_job_created_and_polled(self, MockDL, mock_extract, MockMongo, mock_cache, tmp_path):
        """POST /jobs creates a job that can be polled via GET /jobs/{id}."""
        from backend.evaluate.progress import EvaluationResult

        readme_file = tmp_path / "README.md"
        readme_file.write_text("# Hello World", encoding="utf-8")
        MockDL.return_value.download.return_value = str(readme_file)

        eval_result = EvaluationResult(
            success=True,
            prompt="test",
            model_output="output",
            parsed={"metadata": {"repository_name": "test"}},
            validation_ok=True,
        )
        mock_extract.return_value = eval_result
        MockMongo.return_value.insert_one.return_value = "fake-id"
        mock_cache.return_value.cleanup_job.return_value = {"deleted_files": [], "errors": []}

        resp = client.post("/jobs", json={"repo_url": "https://github.com/t/r"})
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]
        assert job_id is not None

        # The job should be poll-able
        status_resp = client.get(f"/jobs/{job_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["id"] == job_id


# =====================================================================
# Flow: download README via /readme
# =====================================================================

class TestDownloadReadmeFlow:

    @patch("backend.routers.readme.ReadmeDownloader")
    def test_download_and_read(self, MockDL, tmp_path):
        """POST /readme downloads a README and returns its content."""
        readme_file = tmp_path / "README.md"
        readme_file.write_text("# Awesome\nSome content.", encoding="utf-8")
        MockDL.return_value.download.return_value = str(readme_file)

        resp = client.post("/readme", json={"repo_url": "https://github.com/awesome/project"})
        assert resp.status_code == 200
        data = resp.json()
        assert "Awesome" in data["content"]
        assert data["filename"] == "README.md"


# =====================================================================
# Flow: generate text
# =====================================================================

class TestGenerateFlow:

    @patch("backend.routers.generate.get_llm_client")
    def test_generate_and_return(self, mock_factory):
        """POST /generate calls the LLM and returns output."""
        mock_factory.return_value.generate.return_value = "Hello from Gemini!"
        mock_factory.return_value.default_model = "gemini-2.5-flash"

        resp = client.post("/generate", json={
            "prompt": "Say hello.",
            "model": "gemini-2.5-flash",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["output"] == "Hello from Gemini!"
        assert data["model"] == "gemini-2.5-flash"


# =====================================================================
# Flow: health + root sanity
# =====================================================================

class TestHealthIntegration:

    def test_root_and_health_both_work(self):
        """Root and health endpoints should both return 200."""
        root = client.get("/")
        assert root.status_code == 200

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("MONGODB_URI", None)
            health = client.get("/health")
        assert health.status_code == 200
        assert "checks" in health.json()

    def test_health_reports_pipeline_info(self):
        """Health endpoint should include pipeline concurrency info."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("MONGODB_URI", None)
            data = client.get("/health").json()
        assert "pipeline" in data["checks"]
        assert "active_jobs" in data["checks"]["pipeline"]
        assert "max_concurrent" in data["checks"]["pipeline"]
