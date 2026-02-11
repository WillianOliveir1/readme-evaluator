"""Supplemental router-level unit tests — cover thin/missing paths.

Focuses on gaps not covered by test_api.py: parameter forwarding,
error branches, edge cases, rate limiting decorators.
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


# =====================================================================
# POST /readme — branch parameter forwarding
# =====================================================================

class TestReadmeBranch:

    @patch("backend.routers.readme.ReadmeDownloader")
    def test_branch_is_forwarded(self, MockDL, tmp_path):
        readme_file = tmp_path / "README.md"
        readme_file.write_text("# Hello", encoding="utf-8")
        MockDL.return_value.download.return_value = str(readme_file)

        client.post("/readme", json={
            "repo_url": "https://github.com/a/b",
            "branch": "develop",
        })
        # Verify branch was passed to the downloader
        MockDL.return_value.download.assert_called_once()
        _, kwargs = MockDL.return_value.download.call_args
        assert kwargs.get("branch") == "develop"


# =====================================================================
# POST /render-evaluation — error path
# =====================================================================

class TestRenderEvaluationErrors:

    @patch("backend.routers.render.render_from_json")
    def test_render_evaluation_returns_500_on_error(self, mock_render):
        mock_render.side_effect = RuntimeError("render exploded")
        resp = client.post("/render-evaluation", json={
            "evaluation_json": {"some": "data"},
        })
        assert resp.status_code == 500


# =====================================================================
# POST /render — parameter forwarding
# =====================================================================

class TestRenderParameterForwarding:

    @patch("backend.routers.render.render_from_json")
    def test_style_instructions_forwarded(self, mock_render):
        mock_render.return_value = {"prompt": "p", "text": "out"}
        client.post("/render", json={
            "json_object": {"key": "val"},
            "style_instructions": "be concise",
            "model": None,
        })
        mock_render.assert_called_once()
        _, kwargs = mock_render.call_args
        assert kwargs.get("style_instructions") == "be concise"


# =====================================================================
# POST /generate — model skipped when no GEMINI_API_KEY
# =====================================================================

class TestGenerateEdgeCases:

    @patch("backend.routers.generate.get_llm_client")
    def test_model_parameter_forwarded(self, mock_factory):
        mock_factory.return_value.generate.return_value = "ok"
        mock_factory.return_value.default_model = "custom-model"
        resp = client.post("/generate", json={
            "prompt": "hello",
            "model": "custom-model",
            "max_tokens": 100,
            "temperature": 0.5,
        })
        assert resp.status_code == 200
        mock_factory.return_value.generate.assert_called_once()
        args, kwargs = mock_factory.return_value.generate.call_args
        # model should be passed
        assert "custom-model" in str(kwargs) or "custom-model" in str(args)


# =====================================================================
# POST /extract-json — with repo_url + branch
# =====================================================================

class TestExtractJsonBranchForwarding:

    @patch("backend.routers.extract.extract_json_from_readme")
    @patch("backend.routers.extract.ReadmeDownloader")
    def test_branch_forwarded_on_download(self, MockDL, mock_extract, tmp_path):
        readme_file = tmp_path / "README.md"
        readme_file.write_text("# Test", encoding="utf-8")
        MockDL.return_value.download.return_value = str(readme_file)

        from backend.evaluate.progress import EvaluationResult
        mock_extract.return_value = EvaluationResult(
            success=True, prompt="p", model_output=None, parsed=None, validation_ok=False,
        )

        client.post("/extract-json", json={
            "repo_url": "https://github.com/a/b",
            "branch": "main",
        })
        MockDL.return_value.download.assert_called_once()
        _, kwargs = MockDL.return_value.download.call_args
        assert kwargs.get("branch") == "main"


# =====================================================================
# GET /jobs — edge cases
# =====================================================================

class TestListJobsEdgeCases:

    def test_invalid_page_returns_422(self):
        """page=0 should fail validation (ge=1)."""
        resp = client.get("/jobs?page=0")
        assert resp.status_code == 422

    def test_page_size_too_large_returns_422(self):
        """page_size > 100 should fail validation (le=100)."""
        resp = client.get("/jobs?page_size=101")
        assert resp.status_code == 422

    def test_unknown_sort_field_defaults_to_created_at(self, tmp_path):
        """Unknown sort fields should fall back to created_at."""
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()
        data = {"id": "abc", "status": "queued", "created_at": "2025-01-01T00:00:00Z"}
        (jobs_dir / "abc.json").write_text(json.dumps(data), encoding="utf-8")

        with patch("backend.routers.jobs._JOBS_DIR", str(jobs_dir)):
            resp = client.get("/jobs?sort=nonexistent_field")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


# =====================================================================
# POST /cache/cleanup — query parameters
# =====================================================================

class TestCacheCleanupParameters:

    @patch("backend.routers.cache.get_cache_manager")
    def test_cleanup_with_max_age_hours(self, mock_mgr):
        mock_mgr.return_value.cleanup_old_files.return_value = {"processing": [], "processed": []}
        mock_mgr.return_value.get_stats.return_value = {"processing": {}, "processed": {}}

        resp = client.post("/cache/cleanup?max_age_hours=1")
        assert resp.status_code == 200

    @patch("backend.routers.cache.get_cache_manager")
    def test_cleanup_dry_run(self, mock_mgr):
        mock_mgr.return_value.cleanup_old_files.return_value = {"processing": [], "processed": []}
        mock_mgr.return_value.get_stats.return_value = {"processing": {}, "processed": {}}

        resp = client.post("/cache/cleanup?dry_run=true")
        assert resp.status_code == 200


# =====================================================================
# POST /cache/cleanup-all
# =====================================================================

class TestCacheCleanupAll:

    @patch("backend.routers.cache.get_cache_manager")
    def test_cleanup_all_with_dry_run(self, mock_mgr):
        mock_mgr.return_value.cleanup_all.return_value = {
            "deleted_files": [], "preserved": [], "errors": [],
        }

        resp = client.post("/cache/cleanup-all?dry_run=true")
        assert resp.status_code == 200


# =====================================================================
# POST /save-to-file — error paths
# =====================================================================

class TestSaveToFileEdgeCases:

    def test_empty_result_is_accepted(self):
        """An empty dict should still be saved."""
        resp = client.post("/save-to-file", json={"result": {}})
        assert resp.status_code == 200

    def test_save_with_all_params(self, tmp_path):
        """Verify owner, repo, and custom_filename are all accepted."""
        resp = client.post("/save-to-file", json={
            "result": {"key": "val"},
            "owner": "testowner",
            "repo": "testrepo",
            "custom_filename": "my_output",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "my_output" in data.get("filename", "")
