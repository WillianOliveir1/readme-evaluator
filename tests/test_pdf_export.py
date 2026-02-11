"""Tests for backend.routers.export_pdf — PDF export endpoint.

The xhtml2pdf library is mocked for unit tests to avoid heavy rendering;
one integration-level test exercises the real pipeline.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _disable_rate_limits():
    """Disable slowapi rate-limiting for the entire test module.

    slowapi stores hit counters in an in-memory dict keyed by
    (endpoint, client-IP).  We clear the underlying ``limits`` storage
    before every test so the 10-per-minute EXPENSIVE_LIMIT never fires.
    """
    from backend.rate_limit import limiter
    storage = getattr(limiter, "_storage", None)
    if storage is not None and hasattr(storage, "storage"):
        storage.storage.clear()          # MemoryStorage internal dict
    yield


# =====================================================================
# Helper data
# =====================================================================

_SAMPLE_MARKDOWN = "# Hello World\n\nSome **bold** text."

_SAMPLE_EVALUATION = {
    "metadata": {
        "repository_name": "test-repo",
        "evaluation_date": "2025-12-01",
        "evaluator": "gemini-2.5-flash",
    },
    "categories": {
        "what": {
            "score": 4,
            "justifications": ["Clear description", "Good examples"],
        },
        "how": {
            "score": 3,
            "justifications": "Single string justification",
        },
    },
}


# =====================================================================
# POST /export-pdf — with markdown_text
# =====================================================================

class TestExportPdfFromMarkdown:

    @patch("backend.routers.export_pdf._html_to_pdf")
    def test_returns_pdf_from_markdown(self, mock_pdf):
        mock_pdf.return_value = b"%PDF-1.4 fake content"

        resp = client.post("/export-pdf", json={
            "markdown_text": _SAMPLE_MARKDOWN,
            "repo_name": "my-repo",
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "my-repo" in resp.headers.get("content-disposition", "")
        assert resp.content == b"%PDF-1.4 fake content"

    @patch("backend.routers.export_pdf._html_to_pdf")
    def test_html_contains_markdown_content(self, mock_pdf):
        """The HTML passed to the converter should include the markdown."""
        mock_pdf.return_value = b"%PDF"

        client.post("/export-pdf", json={
            "markdown_text": _SAMPLE_MARKDOWN,
        })

        html_arg = mock_pdf.call_args[0][0]
        assert "<strong>bold</strong>" in html_arg or "bold" in html_arg
        assert "Hello World" in html_arg

    @patch("backend.routers.export_pdf._html_to_pdf")
    def test_title_includes_repo_name(self, mock_pdf):
        mock_pdf.return_value = b"%PDF"

        client.post("/export-pdf", json={
            "markdown_text": "# Test",
            "repo_name": "awesome-project",
        })

        html_arg = mock_pdf.call_args[0][0]
        assert "awesome-project" in html_arg

    @patch("backend.routers.export_pdf._html_to_pdf")
    def test_default_filename_when_no_repo(self, mock_pdf):
        mock_pdf.return_value = b"%PDF"

        resp = client.post("/export-pdf", json={
            "markdown_text": "# Test",
        })
        assert "report" in resp.headers.get("content-disposition", "")


# =====================================================================
# POST /export-pdf — with evaluation_json
# =====================================================================

class TestExportPdfFromJson:

    @patch("backend.routers.export_pdf._html_to_pdf")
    def test_json_to_markdown_conversion(self, mock_pdf):
        """evaluation_json should be converted to markdown first."""
        mock_pdf.return_value = b"%PDF"

        resp = client.post("/export-pdf", json={
            "evaluation_json": _SAMPLE_EVALUATION,
        })
        assert resp.status_code == 200

        html_arg = mock_pdf.call_args[0][0]
        assert "test-repo" in html_arg
        assert "What" in html_arg or "what" in html_arg
        assert "Score" in html_arg or "score" in html_arg

    @patch("backend.routers.export_pdf._html_to_pdf")
    def test_markdown_takes_priority_over_json(self, mock_pdf):
        """When both markdown_text and evaluation_json are provided,
        markdown_text takes priority."""
        mock_pdf.return_value = b"%PDF"

        client.post("/export-pdf", json={
            "markdown_text": "# Custom Markdown",
            "evaluation_json": _SAMPLE_EVALUATION,
        })

        html_arg = mock_pdf.call_args[0][0]
        assert "Custom Markdown" in html_arg


# =====================================================================
# Validation & error handling
# =====================================================================

class TestExportPdfErrors:

    def test_empty_body_returns_400(self):
        """Neither markdown_text nor evaluation_json → 400."""
        resp = client.post("/export-pdf", json={})
        assert resp.status_code == 400
        assert "Provide either" in resp.json()["detail"]

    def test_null_values_returns_400(self):
        resp = client.post("/export-pdf", json={
            "markdown_text": None,
            "evaluation_json": None,
        })
        assert resp.status_code == 400

    @patch("backend.routers.export_pdf._html_to_pdf")
    def test_pdf_conversion_failure_returns_500(self, mock_pdf):
        mock_pdf.side_effect = RuntimeError("xhtml2pdf crashed")

        resp = client.post("/export-pdf", json={
            "markdown_text": "# Test",
        })
        assert resp.status_code == 500
        assert "PDF generation failed" in resp.json()["detail"]


# =====================================================================
# Internal helpers
# =====================================================================

class TestJsonToMarkdown:
    """Test the _json_to_markdown helper directly."""

    def test_includes_metadata(self):
        from backend.routers.export_pdf import _json_to_markdown
        md = _json_to_markdown(_SAMPLE_EVALUATION)
        assert "test-repo" in md
        assert "2025-12-01" in md
        assert "gemini-2.5-flash" in md

    def test_includes_categories_and_scores(self):
        from backend.routers.export_pdf import _json_to_markdown
        md = _json_to_markdown(_SAMPLE_EVALUATION)
        assert "What" in md or "what" in md
        assert "4/5" in md
        assert "How" in md or "how" in md
        assert "3/5" in md

    def test_list_justifications(self):
        from backend.routers.export_pdf import _json_to_markdown
        md = _json_to_markdown(_SAMPLE_EVALUATION)
        assert "Clear description" in md
        assert "Good examples" in md

    def test_string_justification(self):
        from backend.routers.export_pdf import _json_to_markdown
        md = _json_to_markdown(_SAMPLE_EVALUATION)
        assert "Single string justification" in md

    def test_empty_evaluation(self):
        from backend.routers.export_pdf import _json_to_markdown
        md = _json_to_markdown({})
        assert "Unknown" in md


class TestMarkdownToHtml:
    """Test the _markdown_to_html helper directly."""

    def test_produces_valid_html(self):
        from backend.routers.export_pdf import _markdown_to_html
        html = _markdown_to_html("# Title\n\nParagraph", "my-repo")
        assert "<!DOCTYPE html>" in html
        assert "<h1>" in html
        assert "my-repo" in html

    def test_no_repo_name(self):
        from backend.routers.export_pdf import _markdown_to_html
        html = _markdown_to_html("text", None)
        assert "README Evaluation Report" in html

    def test_tables_rendered(self):
        from backend.routers.export_pdf import _markdown_to_html
        md_table = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = _markdown_to_html(md_table, None)
        assert "<table>" in html or "<table" in html


# =====================================================================
# Integration: real pipeline (no mocks)
# =====================================================================

class TestExportPdfIntegration:

    def test_real_pdf_from_markdown(self):
        """End-to-end: markdown → HTML → real PDF bytes."""
        resp = client.post("/export-pdf", json={
            "markdown_text": "# Integration Test\n\n- Item 1\n- Item 2",
            "repo_name": "integration-test",
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        # PDF magic bytes
        assert resp.content[:5] == b"%PDF-"

    def test_real_pdf_from_json(self):
        """End-to-end: evaluation JSON → markdown → HTML → PDF."""
        resp = client.post("/export-pdf", json={
            "evaluation_json": _SAMPLE_EVALUATION,
        })
        assert resp.status_code == 200
        assert resp.content[:5] == b"%PDF-"
