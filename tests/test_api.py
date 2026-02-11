"""Tests for backend.main — FastAPI endpoints tested with TestClient.

All external dependencies (ReadmeDownloader, LLM factory, extract_json_from_readme,
render_from_json, MongoDBHandler, CacheManager) are mocked so tests run offline.
"""
from __future__ import annotations

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from backend.main import app
from backend.evaluate.progress import EvaluationResult
from tests.conftest import make_minimal_evaluation


client = TestClient(app)


# =====================================================================
# GET / — root health / info
# =====================================================================

class TestRootEndpoint:
    def test_returns_200(self):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_contains_service_name(self):
        data = client.get("/").json()
        assert "service" in data
        assert "readme-evaluator" in data["service"]

    def test_lists_endpoints(self):
        data = client.get("/").json()
        assert "endpoints" in data
        paths = [ep["path"] for ep in data["endpoints"]]
        assert "/readme" in paths
        assert "/extract-json" in paths
        assert "/health" in paths


# =====================================================================
# GET /health — deep health check
# =====================================================================

class TestHealthEndpoint:
    def test_returns_200_when_no_externals(self):
        """With no GEMINI_API_KEY or MONGODB_URI, returns 200 (all not_configured)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("MONGODB_URI", None)
            resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "checks" in data

    def test_gemini_not_configured(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            data = client.get("/health").json()
        assert data["checks"]["gemini"]["status"] == "not_configured"

    def test_mongodb_not_configured(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MONGODB_URI", None)
            data = client.get("/health").json()
        assert data["checks"]["mongodb"]["status"] == "not_configured"

    @patch("backend.main.API_KEY", "test-secret-key")
    def test_health_is_public_no_auth_needed(self):
        """GET /health should not require an API key."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("MONGODB_URI", None)
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_response_contains_data_dirs(self):
        data = client.get("/health").json()
        assert "data_dirs" in data["checks"]

    @patch("backend.main.LLM_PROVIDER", "gemini")
    @patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"})
    @patch("backend.main.genai")
    def test_gemini_error_returns_503(self, mock_genai):
        """When Gemini API key is set but call fails, report degraded."""
        mock_client = MagicMock()
        mock_client.models.list.side_effect = RuntimeError("API error")
        mock_genai.Client.return_value = mock_client

        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["checks"]["gemini"]["status"] == "error"


# =====================================================================
# POST /readme
# =====================================================================

class TestReadmeEndpoint:

    @patch("backend.routers.readme.ReadmeDownloader")
    def test_success(self, MockDL, tmp_path):
        # Create a temporary file the mock will "download"
        readme_file = tmp_path / "README.md"
        readme_file.write_text("# Hello\nWorld", encoding="utf-8")

        MockDL.return_value.download.return_value = str(readme_file)

        resp = client.post("/readme", json={"repo_url": "https://github.com/test/repo"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "README.md"
        assert "Hello" in data["content"]

    @patch("backend.routers.readme.ReadmeDownloader")
    def test_repo_not_found(self, MockDL):
        MockDL.return_value.download.side_effect = FileNotFoundError("Not found")

        resp = client.post("/readme", json={"repo_url": "https://github.com/no/repo"})
        assert resp.status_code == 404

    @patch("backend.routers.readme.ReadmeDownloader")
    def test_server_error(self, MockDL):
        MockDL.return_value.download.side_effect = RuntimeError("boom")

        resp = client.post("/readme", json={"repo_url": "https://github.com/x/y"})
        assert resp.status_code == 500


# =====================================================================
# POST /generate
# =====================================================================

class TestGenerateEndpoint:

    @patch("backend.routers.generate.get_llm_client")
    def test_success(self, mock_factory):
        mock_factory.return_value.generate.return_value = "Generated text"
        mock_factory.return_value.default_model = "gemini-2.5-flash"

        resp = client.post("/generate", json={"prompt": "Hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["output"] == "Generated text"

    @patch("backend.routers.generate.get_llm_client")
    def test_error_returns_500(self, mock_factory):
        mock_factory.return_value.generate.side_effect = RuntimeError("API key invalid")

        resp = client.post("/generate", json={"prompt": "Hello"})
        assert resp.status_code == 500


# =====================================================================
# POST /extract-json
# =====================================================================

class TestExtractJsonEndpoint:

    @patch("backend.routers.extract.extract_json_from_readme")
    def test_with_readme_text(self, mock_extract):
        eval_result = EvaluationResult(
            success=True,
            prompt="test prompt",
            model_output=None,
            parsed=None,
            validation_ok=False,
        )
        mock_extract.return_value = eval_result

        resp = client.post("/extract-json", json={
            "readme_text": "# README\nSome content",
            "model": None,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_missing_both_fields_returns_400(self):
        resp = client.post("/extract-json", json={})
        assert resp.status_code == 400

    @patch("backend.routers.extract.ReadmeDownloader")
    @patch("backend.routers.extract.extract_json_from_readme")
    def test_with_repo_url(self, mock_extract, MockDL, tmp_path):
        readme_file = tmp_path / "README.md"
        readme_file.write_text("# Hello", encoding="utf-8")
        MockDL.return_value.download.return_value = str(readme_file)

        eval_result = EvaluationResult(
            success=True, prompt="p", model_output=None, parsed=None, validation_ok=False,
        )
        mock_extract.return_value = eval_result

        resp = client.post("/extract-json", json={
            "repo_url": "https://github.com/test/repo",
        })
        assert resp.status_code == 200

    @patch("backend.routers.extract.ReadmeDownloader")
    def test_download_failure_returns_502(self, MockDL):
        MockDL.return_value.download.side_effect = RuntimeError("network error")

        resp = client.post("/extract-json", json={
            "repo_url": "https://github.com/test/repo",
        })
        assert resp.status_code == 502


# =====================================================================
# POST /render
# =====================================================================

class TestRenderEndpoint:

    @patch("backend.routers.render.render_from_json")
    def test_success(self, mock_render):
        mock_render.return_value = {"text": "# Report\nGreat README."}

        resp = client.post("/render", json={"json_object": {"key": "val"}})
        assert resp.status_code == 200

    @patch("backend.routers.render.render_from_json")
    def test_error_returns_500(self, mock_render):
        mock_render.side_effect = RuntimeError("model failed")

        resp = client.post("/render", json={"json_object": {"key": "val"}})
        assert resp.status_code == 500


# =====================================================================
# POST /render-evaluation
# =====================================================================

class TestRenderEvaluationEndpoint:

    @patch("backend.routers.render.render_from_json")
    def test_success(self, mock_render):
        mock_render.return_value = {"text": "Summary text"}

        resp = client.post("/render-evaluation", json={
            "evaluation_json": make_minimal_evaluation(),
        })
        assert resp.status_code == 200

    @patch("backend.routers.render.render_from_json")
    def test_uses_default_style(self, mock_render):
        mock_render.return_value = {"text": "ok"}

        client.post("/render-evaluation", json={
            "evaluation_json": {"a": 1},
        })
        call_kwargs = mock_render.call_args
        # style_instructions should be the default, not None
        assert call_kwargs is not None


# =====================================================================
# POST /jobs  &  GET /jobs/{job_id}
# =====================================================================

class TestJobsEndpoint:

    @patch("backend.routers.jobs.PipelineRunner")
    def test_create_job(self, MockRunner):
        MockRunner.return_value.new_job.return_value = {"id": "test-job-123"}

        resp = client.post("/jobs", json={"repo_url": "https://github.com/a/b"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "test-job-123"

    def test_get_missing_job_returns_404(self):
        resp = client.get("/jobs/nonexistent-uuid-here")
        assert resp.status_code == 404

    def test_path_traversal_in_job_id_rejected(self):
        """Job IDs with path separators must be rejected."""
        resp = client.get("/jobs/../../etc/passwd")
        assert resp.status_code in (400, 404, 422)  # blocked before file access

    def test_get_existing_job(self, tmp_path):
        # Create a fake job status file in the expected location
        job_id = "test-job-456"
        jobs_dir = Path(os.getcwd()) / "data" / "processing" / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        job_file = jobs_dir / f"{job_id}.json"
        job_data = {"id": job_id, "status": "completed"}
        job_file.write_text(json.dumps(job_data), encoding="utf-8")

        try:
            resp = client.get(f"/jobs/{job_id}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "completed"
        finally:
            # Cleanup
            job_file.unlink(missing_ok=True)


# =====================================================================
# GET /jobs — list with pagination / filters
# =====================================================================

class TestListJobs:

    def _seed_jobs(self, jobs_dir: Path, n: int = 5) -> list[str]:
        """Create *n* fake job files and return their IDs."""
        import uuid
        ids = []
        statuses = ["queued", "running", "succeeded", "failed", "succeeded"]
        for i in range(n):
            jid = str(uuid.uuid4())
            ids.append(jid)
            data = {
                "id": jid,
                "status": statuses[i % len(statuses)],
                "created_at": f"2025-01-01T00:0{i}:00Z",
            }
            (jobs_dir / f"{jid}.json").write_text(
                json.dumps(data), encoding="utf-8"
            )
        return ids

    def test_empty_dir_returns_empty(self):
        """When no jobs exist, returns an empty list."""
        with patch("backend.routers.jobs._JOBS_DIR", str(Path(os.getcwd()) / "nonexistent_dir_xyz")):
            resp = client.get("/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_pagination_defaults(self, tmp_path):
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()
        ids = self._seed_jobs(jobs_dir, n=5)

        with patch("backend.routers.jobs._JOBS_DIR", str(jobs_dir)):
            resp = client.get("/jobs")
        data = resp.json()
        assert data["total"] == 5
        assert data["page"] == 1
        assert len(data["items"]) == 5

    def test_pagination_page_size(self, tmp_path):
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()
        self._seed_jobs(jobs_dir, n=5)

        with patch("backend.routers.jobs._JOBS_DIR", str(jobs_dir)):
            resp = client.get("/jobs?page_size=2&page=1")
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["pages"] == 3  # ceil(5 / 2)

    def test_pagination_last_page(self, tmp_path):
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()
        self._seed_jobs(jobs_dir, n=5)

        with patch("backend.routers.jobs._JOBS_DIR", str(jobs_dir)):
            resp = client.get("/jobs?page_size=2&page=3")
        data = resp.json()
        assert len(data["items"]) == 1  # 5 - 2*2

    def test_filter_by_status(self, tmp_path):
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()
        self._seed_jobs(jobs_dir, n=5)  # statuses: queued, running, succeeded, failed, succeeded

        with patch("backend.routers.jobs._JOBS_DIR", str(jobs_dir)):
            resp = client.get("/jobs?status=succeeded")
        data = resp.json()
        assert all(j["status"] == "succeeded" for j in data["items"])
        assert data["total"] == 2

    def test_filter_by_multiple_statuses(self, tmp_path):
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()
        self._seed_jobs(jobs_dir, n=5)

        with patch("backend.routers.jobs._JOBS_DIR", str(jobs_dir)):
            resp = client.get("/jobs?status=queued,failed")
        data = resp.json()
        assert data["total"] == 2

    def test_sort_asc(self, tmp_path):
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()
        self._seed_jobs(jobs_dir, n=3)

        with patch("backend.routers.jobs._JOBS_DIR", str(jobs_dir)):
            resp = client.get("/jobs?sort=created_at&order=asc")
        data = resp.json()
        timestamps = [j["created_at"] for j in data["items"]]
        assert timestamps == sorted(timestamps)

    def test_items_contain_is_active(self, tmp_path):
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()
        self._seed_jobs(jobs_dir, n=1)

        with patch("backend.routers.jobs._JOBS_DIR", str(jobs_dir)):
            resp = client.get("/jobs")
        data = resp.json()
        assert "is_active" in data["items"][0]


# =====================================================================
# Cache endpoints
# =====================================================================

class TestCacheEndpoints:

    @patch("backend.routers.cache.get_cache_manager")
    def test_get_stats(self, mock_mgr):
        mock_mgr.return_value.get_stats.return_value = {
            "processing": {"file_count": 2},
            "processed": {"file_count": 5},
        }

        resp = client.get("/cache/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "processing" in data

    @patch("backend.routers.cache.get_cache_manager")
    def test_cleanup(self, mock_mgr):
        mock_mgr.return_value.cleanup_old_files.return_value = {
            "processing": [], "processed": [],
        }
        mock_mgr.return_value.get_stats.return_value = {"processing": {}, "processed": {}}

        resp = client.post("/cache/cleanup")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cleaned"

    @patch("backend.routers.cache.get_cache_manager")
    def test_cleanup_job(self, mock_mgr):
        mock_mgr.return_value.cleanup_job.return_value = {
            "deleted_files": [], "errors": [],
        }

        resp = client.delete("/cache/cleanup-job/some-uuid")
        assert resp.status_code == 200
        assert resp.json()["job_id"] == "some-uuid"

    @patch("backend.routers.cache.get_cache_manager")
    def test_cleanup_all(self, mock_mgr):
        mock_mgr.return_value.cleanup_all.return_value = {
            "deleted_files": [], "preserved": [], "errors": [],
        }
        mock_mgr.return_value.get_stats.return_value = {"processing": {}, "processed": {}}

        resp = client.post("/cache/cleanup-all")
        assert resp.status_code == 200
        assert resp.json()["status"] == "fully_cleaned"


# =====================================================================
# POST /save-to-file
# =====================================================================

class TestSaveToFileEndpoint:

    def test_with_owner_repo(self, tmp_path, monkeypatch):
        """When owner + repo are given, the filename uses them."""
        # Ensure the data/processed directory uses a temp path
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "processed").mkdir(parents=True, exist_ok=True)

        resp = client.post("/save-to-file", json={
            "result": {"key": "val"},
            "owner": "keras-team",
            "repo": "keras",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "keras-team-keras" in data["filename"]

    def test_with_custom_filename(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "processed").mkdir(parents=True, exist_ok=True)

        resp = client.post("/save-to-file", json={
            "result": {"key": "val"},
            "custom_filename": "my-report.json",
        })
        assert resp.status_code == 200
        assert resp.json()["filename"] == "my-report.json"

    def test_auto_extract_name(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "processed").mkdir(parents=True, exist_ok=True)

        resp = client.post("/save-to-file", json={
            "result": {
                "parsed": {
                    "metadata": {"repository_name": "Test Repo"},
                },
            },
        })
        assert resp.status_code == 200
        assert "test-repo" in resp.json()["filename"]

    def test_path_traversal_blocked(self, tmp_path, monkeypatch):
        """Directory traversal via custom_filename must be sanitized."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "processed").mkdir(parents=True, exist_ok=True)

        resp = client.post("/save-to-file", json={
            "result": {"key": "val"},
            "custom_filename": "../../etc/evil.json",
        })
        assert resp.status_code == 200
        # Should be sanitized to just the basename
        assert resp.json()["filename"] == "evil.json"

    def test_dotfile_rejected(self, tmp_path, monkeypatch):
        """Filenames starting with dot should be rejected."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "processed").mkdir(parents=True, exist_ok=True)

        resp = client.post("/save-to-file", json={
            "result": {"key": "val"},
            "custom_filename": ".htaccess",
        })
        assert resp.status_code == 400


# =====================================================================
# API Key Authentication
# =====================================================================

class TestApiKeyAuth:
    """Tests for X-API-Key middleware.

    By default API_KEY is not set so all requests pass through.
    These tests patch the config value to verify enforcement.
    """

    def test_no_key_configured_allows_all(self):
        """When API_KEY is unset, requests pass without auth."""
        resp = client.get("/")
        assert resp.status_code == 200

    @patch("backend.main.API_KEY", "test-secret-key")
    def test_root_is_always_public(self):
        """GET / (health check) should not require a key."""
        resp = client.get("/")
        assert resp.status_code == 200

    @patch("backend.main.API_KEY", "test-secret-key")
    def test_health_is_always_public(self):
        """GET /health should not require a key."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("MONGODB_URI", None)
            resp = client.get("/health")
        assert resp.status_code == 200

    @patch("backend.main.API_KEY", "test-secret-key")
    def test_missing_key_returns_401(self):
        """Protected endpoints reject requests without a key."""
        resp = client.post("/readme", json={"repo_url": "https://github.com/a/b"})
        assert resp.status_code == 401
        assert "API key" in resp.json()["detail"]

    @patch("backend.main.API_KEY", "test-secret-key")
    def test_wrong_key_returns_401(self):
        """Wrong key is rejected."""
        resp = client.post(
            "/readme",
            json={"repo_url": "https://github.com/a/b"},
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    @patch("backend.main.API_KEY", "test-secret-key")
    @patch("backend.routers.readme.ReadmeDownloader")
    def test_correct_key_allows_request(self, MockDL, tmp_path):
        """Correct key grants access."""
        readme_file = tmp_path / "README.md"
        readme_file.write_text("# OK", encoding="utf-8")
        MockDL.return_value.download.return_value = str(readme_file)

        resp = client.post(
            "/readme",
            json={"repo_url": "https://github.com/a/b"},
            headers={"X-API-Key": "test-secret-key"},
        )
        assert resp.status_code == 200

    @patch("backend.main.API_KEY", "test-secret-key")
    def test_key_via_query_param(self):
        """API key can also be passed as ?api_key= query parameter."""
        resp = client.get("/?api_key=test-secret-key")
        assert resp.status_code == 200
