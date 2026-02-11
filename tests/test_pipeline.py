"""Tests for backend.pipeline — PipelineRunner job lifecycle.

All I/O (ReadmeDownloader, extract_json_from_readme, MongoDBHandler,
get_cache_manager) is mocked so tests run offline and fast.
"""
from __future__ import annotations

import json
import os
import threading
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.pipeline import PipelineRunner, get_active_jobs
from backend.evaluate.progress import EvaluationResult


# =====================================================================
# Helpers
# =====================================================================

def _make_eval_result(success: bool = True, parsed: dict | None = None):
    """Return an EvaluationResult matching what extract_json_from_readme returns."""
    return EvaluationResult(
        success=success,
        prompt="test prompt",
        model_output="test output",
        parsed=parsed or {"metadata": {"repository_name": "test"}},
        validation_ok=success,
        validation_errors=None if success else {"errors": ["some error"]},
    )


# =====================================================================
# Job creation
# =====================================================================

class TestNewJob:
    def test_creates_job_file(self, tmp_path):
        runner = PipelineRunner(jobs_dir=str(tmp_path))
        job = runner.new_job({"repo_url": "https://github.com/a/b"})

        assert "id" in job
        assert job["status"] == "queued"
        assert (tmp_path / f"{job['id']}.json").exists()

    def test_job_has_required_fields(self, tmp_path):
        runner = PipelineRunner(jobs_dir=str(tmp_path))
        job = runner.new_job({"repo_url": "https://github.com/a/b"})

        for key in ("id", "status", "created_at", "params", "steps", "artifacts", "result", "error"):
            assert key in job, f"Missing field: {key}"

    def test_each_job_has_unique_id(self, tmp_path):
        runner = PipelineRunner(jobs_dir=str(tmp_path))
        j1 = runner.new_job({})
        j2 = runner.new_job({})
        assert j1["id"] != j2["id"]


# =====================================================================
# Full pipeline run — with repo_url
# =====================================================================

class TestRunWithRepoUrl:

    @patch("backend.pipeline.get_cache_manager")
    @patch("backend.pipeline.MongoDBHandler")
    @patch("backend.pipeline.extract_json_from_readme")
    @patch("backend.pipeline.ReadmeDownloader")
    def test_successful_run(self, MockDL, mock_extract, MockMongo, mock_cache, tmp_path):
        # Setup: downloader writes a README file
        readme_file = tmp_path / "processing" / "README.md"
        readme_file.parent.mkdir(parents=True, exist_ok=True)
        readme_file.write_text("# Hello World", encoding="utf-8")
        MockDL.return_value.download.return_value = str(readme_file)

        # Setup: extractor returns a result dict
        eval_result = _make_eval_result(success=True)
        # First call (prompt_only, model=None) — returns a dict
        # Second call (with model) — also returns a dict
        mock_extract.return_value = eval_result

        # Setup: MongoDB handler
        MockMongo.return_value.insert_one.return_value = "fake-mongo-id"

        # Setup: cache manager
        mock_cache.return_value.cleanup_job.return_value = {"deleted_files": [], "errors": []}

        # Create processed dir for the pipeline to write to
        processed_dir = tmp_path / "data" / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)

        # Run
        runner = PipelineRunner(jobs_dir=str(tmp_path / "jobs"))
        job = runner.new_job({"repo_url": "https://github.com/test/repo", "model": "gemini-2.5-flash"})
        job_id = job["id"]

        with patch("os.getcwd", return_value=str(tmp_path)):
            runner.run(job_id, {"repo_url": "https://github.com/test/repo", "model": "gemini-2.5-flash"})

        # Verify: job file updated
        with open(tmp_path / "jobs" / f"{job_id}.json", "r") as f:
            final = json.load(f)

        assert final["status"] == "succeeded"
        assert final.get("finished_at") is not None
        step_names = [s["name"] for s in final["steps"]]
        assert "download_readme" in step_names
        assert "build_prompt" in step_names
        assert "save_results" in step_names

    @patch("backend.pipeline.get_cache_manager")
    @patch("backend.pipeline.MongoDBHandler")
    @patch("backend.pipeline.extract_json_from_readme")
    @patch("backend.pipeline.ReadmeDownloader")
    def test_download_failure_marks_job_failed(self, MockDL, mock_extract, MockMongo, mock_cache, tmp_path):
        MockDL.return_value.download.side_effect = RuntimeError("network error")

        runner = PipelineRunner(jobs_dir=str(tmp_path / "jobs"))
        job = runner.new_job({"repo_url": "https://github.com/no/repo"})
        job_id = job["id"]

        runner.run(job_id, {"repo_url": "https://github.com/no/repo"})

        with open(tmp_path / "jobs" / f"{job_id}.json", "r") as f:
            final = json.load(f)

        assert final["status"] == "failed"
        assert "network error" in (final.get("error") or "")


# =====================================================================
# Full pipeline run — with readme_text
# =====================================================================

class TestRunWithReadmeText:

    @patch("backend.pipeline.get_cache_manager")
    @patch("backend.pipeline.MongoDBHandler")
    @patch("backend.pipeline.extract_json_from_readme")
    def test_writes_readme_text_to_file(self, mock_extract, MockMongo, mock_cache, tmp_path):
        eval_result = _make_eval_result(success=True)
        mock_extract.return_value = eval_result
        MockMongo.return_value.insert_one.return_value = None
        mock_cache.return_value.cleanup_job.return_value = {"deleted_files": [], "errors": []}

        runner = PipelineRunner(jobs_dir=str(tmp_path / "jobs"))
        job = runner.new_job({"readme_text": "# Inline README"})
        job_id = job["id"]

        with patch("os.getcwd", return_value=str(tmp_path)):
            runner.run(job_id, {"readme_text": "# Inline README"})

        with open(tmp_path / "jobs" / f"{job_id}.json", "r") as f:
            final = json.load(f)

        assert final["status"] == "succeeded"


# =====================================================================
# Missing params
# =====================================================================

class TestRunValidation:

    def test_missing_job_file_is_noop(self, tmp_path):
        runner = PipelineRunner(jobs_dir=str(tmp_path / "jobs"))
        # Running a nonexistent job should not raise
        runner.run("nonexistent-id", {})

    @patch("backend.pipeline.ReadmeDownloader")
    def test_no_url_or_text_fails(self, MockDL, tmp_path):
        runner = PipelineRunner(jobs_dir=str(tmp_path / "jobs"))
        job = runner.new_job({})
        job_id = job["id"]

        runner.run(job_id, {})

        with open(tmp_path / "jobs" / f"{job_id}.json", "r") as f:
            final = json.load(f)

        assert final["status"] == "failed"
        assert "repo_url or readme_text" in (final.get("error") or "").lower()


# =====================================================================
# Step tracking
# =====================================================================

class TestStepTracking:

    @patch("backend.pipeline.get_cache_manager")
    @patch("backend.pipeline.MongoDBHandler")
    @patch("backend.pipeline.extract_json_from_readme")
    @patch("backend.pipeline.ReadmeDownloader")
    def test_all_steps_recorded(self, MockDL, mock_extract, MockMongo, mock_cache, tmp_path):
        readme_file = tmp_path / "README.md"
        readme_file.write_text("# Test", encoding="utf-8")
        MockDL.return_value.download.return_value = str(readme_file)
        mock_extract.return_value = _make_eval_result()
        MockMongo.return_value.insert_one.return_value = "id"
        mock_cache.return_value.cleanup_job.return_value = {"deleted_files": [], "errors": []}

        runner = PipelineRunner(jobs_dir=str(tmp_path / "jobs"))
        job = runner.new_job({"repo_url": "https://github.com/a/b"})

        with patch("os.getcwd", return_value=str(tmp_path)):
            runner.run(job["id"], {"repo_url": "https://github.com/a/b"})

        with open(tmp_path / "jobs" / f"{job['id']}.json", "r") as f:
            final = json.load(f)

        step_names = [s["name"] for s in final["steps"]]
        expected = ["download_readme", "build_prompt", "call_model", "validate_schema",
                     "save_results", "save_to_database", "cleanup_cache"]
        for name in expected:
            assert name in step_names, f"Missing step: {name}"

        # Every step should have started_at
        for step in final["steps"]:
            assert step["started_at"] is not None


# =====================================================================
# Concurrency control
# =====================================================================

class TestConcurrency:

    def test_duplicate_job_is_rejected(self, tmp_path):
        """Running the same job_id twice concurrently should skip the duplicate."""
        from backend import pipeline as _mod

        runner = PipelineRunner(jobs_dir=str(tmp_path / "jobs"))
        job = runner.new_job({"readme_text": "# Test"})
        job_id = job["id"]

        # Simulate job already in the active set
        with _mod._active_jobs_lock:
            _mod._active_jobs.add(job_id)

        try:
            # Second invocation should bail out immediately (no error)
            runner.run(job_id, {"readme_text": "# Test"})

            # Job file should still be "queued" — the duplicate was a no-op
            with open(tmp_path / "jobs" / f"{job_id}.json", "r") as f:
                data = json.load(f)
            assert data["status"] == "queued"
        finally:
            with _mod._active_jobs_lock:
                _mod._active_jobs.discard(job_id)

    def test_get_active_jobs_returns_snapshot(self):
        """get_active_jobs() returns a copy, not the live set."""
        from backend import pipeline as _mod

        with _mod._active_jobs_lock:
            _mod._active_jobs.add("fake-1")
        try:
            snap = get_active_jobs()
            assert "fake-1" in snap
            # Modifying snapshot should not affect the real set
            snap.discard("fake-1")
            assert "fake-1" in get_active_jobs()
        finally:
            with _mod._active_jobs_lock:
                _mod._active_jobs.discard("fake-1")

    @patch("backend.pipeline.get_cache_manager")
    @patch("backend.pipeline.MongoDBHandler")
    @patch("backend.pipeline.extract_json_from_readme")
    @patch("backend.pipeline.ReadmeDownloader")
    def test_active_jobs_cleaned_after_run(self, MockDL, mock_extract, MockMongo, mock_cache, tmp_path):
        """After run() finishes, the job_id should no longer be in active_jobs."""
        readme_file = tmp_path / "README.md"
        readme_file.write_text("# Hello", encoding="utf-8")
        MockDL.return_value.download.return_value = str(readme_file)
        mock_extract.return_value = _make_eval_result()
        MockMongo.return_value.insert_one.return_value = "id"
        mock_cache.return_value.cleanup_job.return_value = {"deleted_files": [], "errors": []}

        runner = PipelineRunner(jobs_dir=str(tmp_path / "jobs"))
        job = runner.new_job({"repo_url": "https://github.com/a/b"})

        with patch("os.getcwd", return_value=str(tmp_path)):
            runner.run(job["id"], {"repo_url": "https://github.com/a/b"})

        assert job["id"] not in get_active_jobs()

    @patch("backend.pipeline.get_cache_manager")
    @patch("backend.pipeline.MongoDBHandler")
    @patch("backend.pipeline.extract_json_from_readme")
    @patch("backend.pipeline.ReadmeDownloader")
    def test_active_jobs_cleaned_after_failure(self, MockDL, mock_extract, MockMongo, mock_cache, tmp_path):
        """Even when the pipeline fails, active_jobs is cleaned up."""
        MockDL.return_value.download.side_effect = RuntimeError("boom")

        runner = PipelineRunner(jobs_dir=str(tmp_path / "jobs"))
        job = runner.new_job({"repo_url": "https://github.com/x/y"})

        runner.run(job["id"], {"repo_url": "https://github.com/x/y"})

        assert job["id"] not in get_active_jobs()