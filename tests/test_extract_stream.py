"""Tests for the /extract-json-stream SSE endpoint.

The streaming endpoint is tested by consuming the full response body and
parsing the individual ``data: ...`` lines as JSON.  All external deps
are mocked.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient

from backend.main import app
from backend.evaluate.progress import EvaluationResult, ProgressUpdate


client = TestClient(app)


# =====================================================================
# Helpers
# =====================================================================

def _parse_sse(body: str) -> list[dict]:
    """Parse SSE text into a list of JSON payloads."""
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def _fake_eval_result(parsed: dict | None = None, validation_ok: bool = True):
    return EvaluationResult(
        success=True,
        prompt="test prompt",
        model_output="raw output",
        parsed=parsed or {"metadata": {"repository_name": "test-repo"}},
        validation_ok=validation_ok,
    )


# =====================================================================
# SSE with readme_text (no download step)
# =====================================================================

class TestExtractStreamWithText:

    @patch("backend.routers.extract.MongoDBHandler")
    @patch("backend.routers.extract.extract_json_from_readme")
    def test_returns_sse_content_type(self, mock_extract, MockMongo):
        mock_extract.return_value = _fake_eval_result(validation_ok=False)
        MockMongo.side_effect = ValueError("no mongo")

        resp = client.post("/extract-json-stream", json={
            "readme_text": "# Hello",
        })
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    @patch("backend.routers.extract.MongoDBHandler")
    @patch("backend.routers.extract.extract_json_from_readme")
    def test_emits_result_event(self, mock_extract, MockMongo):
        mock_extract.return_value = _fake_eval_result(validation_ok=False)
        MockMongo.side_effect = ValueError("no mongo")

        resp = client.post("/extract-json-stream", json={
            "readme_text": "# Hello",
        })
        events = _parse_sse(resp.text)
        types = [e.get("type") for e in events]
        assert "result" in types

        result_event = next(e for e in events if e["type"] == "result")
        assert result_event["result"]["success"] is True

    @patch("backend.routers.extract.render_from_json")
    @patch("backend.routers.extract.MongoDBHandler")
    @patch("backend.routers.extract.extract_json_from_readme")
    def test_auto_render_when_validation_ok(self, mock_extract, MockMongo, mock_render):
        mock_extract.return_value = _fake_eval_result(
            parsed={"metadata": {"repository_name": "test"}},
            validation_ok=True,
        )
        MockMongo.side_effect = ValueError("no mongo")
        mock_render.return_value = {"text": "Rendered report"}

        resp = client.post("/extract-json-stream", json={
            "readme_text": "# Hello",
        })
        events = _parse_sse(resp.text)
        types = [e.get("type") for e in events]
        assert "rendered" in types

    @patch("backend.routers.extract.MongoDBHandler")
    @patch("backend.routers.extract.extract_json_from_readme")
    def test_no_render_when_validation_fails(self, mock_extract, MockMongo):
        mock_extract.return_value = _fake_eval_result(validation_ok=False)
        MockMongo.side_effect = ValueError("no mongo")

        resp = client.post("/extract-json-stream", json={
            "readme_text": "# Hello",
        })
        events = _parse_sse(resp.text)
        types = [e.get("type") for e in events]
        assert "rendered" not in types


# =====================================================================
# SSE with repo_url (includes download step)
# =====================================================================

class TestExtractStreamWithUrl:

    @patch("backend.routers.extract.MongoDBHandler")
    @patch("backend.routers.extract.extract_json_from_readme")
    @patch("backend.routers.extract.ReadmeDownloader")
    def test_download_progress_events(self, MockDL, mock_extract, MockMongo, tmp_path):
        readme_file = tmp_path / "README.md"
        readme_file.write_text("# Test README", encoding="utf-8")
        MockDL.return_value.download.return_value = str(readme_file)
        MockDL.return_value.readme_url = None
        mock_extract.return_value = _fake_eval_result(validation_ok=False)
        MockMongo.side_effect = ValueError("no mongo")

        resp = client.post("/extract-json-stream", json={
            "repo_url": "https://github.com/test/repo",
        })
        events = _parse_sse(resp.text)
        stages = [e.get("stage") for e in events if e.get("type") == "progress"]
        assert "downloading" in stages

    @patch("backend.routers.extract.MongoDBHandler")
    @patch("backend.routers.extract.extract_json_from_readme")
    @patch("backend.routers.extract.ReadmeDownloader")
    def test_download_failure_emits_error(self, MockDL, mock_extract, MockMongo):
        MockDL.return_value.download.side_effect = RuntimeError("network down")

        resp = client.post("/extract-json-stream", json={
            "repo_url": "https://github.com/test/repo",
        })
        events = _parse_sse(resp.text)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) >= 1
        assert "network down" in error_events[0].get("error", "")


# =====================================================================
# SSE — missing input
# =====================================================================

class TestExtractStreamValidation:

    def test_missing_both_fields_emits_error(self):
        resp = client.post("/extract-json-stream", json={})
        events = _parse_sse(resp.text)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) >= 1


# =====================================================================
# SSE — MongoDB save events
# =====================================================================

class TestExtractStreamPersistence:

    @patch("backend.routers.extract.MongoDBHandler")
    @patch("backend.routers.extract.extract_json_from_readme")
    def test_mongo_save_success_event(self, mock_extract, MockMongo):
        mock_extract.return_value = _fake_eval_result(validation_ok=False)
        MockMongo.return_value.insert_one.return_value = "fake-id-123"

        resp = client.post("/extract-json-stream", json={
            "readme_text": "# Hello",
        })
        events = _parse_sse(resp.text)
        db_events = [e for e in events if e.get("type") == "database"]
        assert len(db_events) >= 1
        assert db_events[0]["status"] == "saved"
        assert db_events[0]["mongo_id"] == "fake-id-123"

    @patch("backend.routers.extract.MongoDBHandler")
    @patch("backend.routers.extract.extract_json_from_readme")
    def test_mongo_not_configured_emits_skipped(self, mock_extract, MockMongo):
        mock_extract.return_value = _fake_eval_result(validation_ok=False)
        MockMongo.side_effect = ValueError("MONGODB_URI not set")

        resp = client.post("/extract-json-stream", json={
            "readme_text": "# Hello",
        })
        events = _parse_sse(resp.text)
        db_events = [e for e in events if e.get("type") == "database"]
        assert len(db_events) >= 1
        assert db_events[0]["status"] == "skipped"

    @patch("backend.routers.extract.MongoDBHandler")
    @patch("backend.routers.extract.extract_json_from_readme")
    def test_file_backup_event(self, mock_extract, MockMongo, tmp_path, monkeypatch):
        mock_extract.return_value = _fake_eval_result(validation_ok=False)
        MockMongo.side_effect = ValueError("no mongo")
        monkeypatch.chdir(tmp_path)

        resp = client.post("/extract-json-stream", json={
            "readme_text": "# Hello",
        })
        events = _parse_sse(resp.text)
        file_events = [e for e in events if e.get("type") == "file_backup"]
        assert len(file_events) >= 1
        assert file_events[0]["status"] == "saved"
