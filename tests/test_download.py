"""Tests for backend.download.download.ReadmeDownloader — mocked HTTP."""
from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch

from backend.download.download import ReadmeDownloader


# =====================================================================
# URL Parsing
# =====================================================================

class TestParseRepo:
    """Test _parse_repo with different URL formats."""

    def _parse(self, url: str):
        dl = ReadmeDownloader(session=MagicMock())
        return dl._parse_repo(url)

    def test_https_url(self):
        owner, repo, branch = self._parse("https://github.com/keras-team/keras")
        assert owner == "keras-team"
        assert repo == "keras"
        assert branch is None

    def test_https_url_with_git(self):
        owner, repo, branch = self._parse("https://github.com/keras-team/keras.git")
        assert owner == "keras-team"
        assert repo == "keras"

    def test_https_url_with_branch(self):
        owner, repo, branch = self._parse("https://github.com/owner/repo/tree/develop")
        assert owner == "owner"
        assert repo == "repo"
        assert branch == "develop"

    def test_ssh_url(self):
        owner, repo, branch = self._parse("git@github.com:owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"
        assert branch is None

    def test_ssh_url_no_git_suffix(self):
        owner, repo, branch = self._parse("git@github.com:owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Could not parse"):
            self._parse("https://gitlab.com/owner/repo")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Could not parse"):
            self._parse("not a url at all")


# =====================================================================
# find_readme_in_tree
# =====================================================================

class TestFindReadmeInTree:
    """Test the tree-based README finder."""

    def _finder(self):
        return ReadmeDownloader(session=MagicMock())

    def test_finds_root_readme_md(self):
        tree = [
            {"path": "README.md", "type": "blob"},
            {"path": "src/main.py", "type": "blob"},
        ]
        dl = self._finder()
        assert dl._find_readme_in_tree(tree) == "README.md"

    def test_prefers_root_over_nested(self):
        tree = [
            {"path": "docs/README.md", "type": "blob"},
            {"path": "README.md", "type": "blob"},
        ]
        dl = self._finder()
        assert dl._find_readme_in_tree(tree) == "README.md"

    def test_finds_nested_if_no_root(self):
        tree = [
            {"path": "docs/README.md", "type": "blob"},
            {"path": "src/main.py", "type": "blob"},
        ]
        dl = self._finder()
        assert dl._find_readme_in_tree(tree) == "docs/README.md"

    def test_case_insensitive(self):
        tree = [
            {"path": "readme.md", "type": "blob"},
        ]
        dl = self._finder()
        assert dl._find_readme_in_tree(tree) == "readme.md"

    def test_readme_without_extension(self):
        tree = [
            {"path": "README", "type": "blob"},
        ]
        dl = self._finder()
        assert dl._find_readme_in_tree(tree) == "README"

    def test_readme_rst(self):
        tree = [
            {"path": "README.rst", "type": "blob"},
        ]
        dl = self._finder()
        assert dl._find_readme_in_tree(tree) == "README.rst"

    def test_ignores_directories(self):
        tree = [
            {"path": "README.md", "type": "tree"},  # directory, not blob
        ]
        dl = self._finder()
        assert dl._find_readme_in_tree(tree) is None

    def test_empty_tree(self):
        dl = self._finder()
        assert dl._find_readme_in_tree([]) is None

    def test_no_readme_at_all(self):
        tree = [
            {"path": "main.py", "type": "blob"},
            {"path": "setup.py", "type": "blob"},
        ]
        dl = self._finder()
        assert dl._find_readme_in_tree(tree) is None


# =====================================================================
# Download flow (mocked HTTP)
# =====================================================================

class TestDownloadFlow:
    """Test the download() method with mocked HTTP responses."""

    def _mock_session(self):
        return MagicMock()

    def test_download_via_tree(self, tmp_path):
        """Simulate: get_default_branch -> get_tree -> get_content_by_path."""
        import base64

        session = self._mock_session()
        readme_content = b"# Hello World\n\nThis is a test."
        b64_content = base64.b64encode(readme_content).decode()

        # Mock responses in order
        branch_resp = MagicMock()
        branch_resp.status_code = 200
        branch_resp.json.return_value = {"default_branch": "main"}

        tree_resp = MagicMock()
        tree_resp.status_code = 200
        tree_resp.json.return_value = {
            "tree": [
                {"path": "README.md", "type": "blob"},
                {"path": "src/app.py", "type": "blob"},
            ]
        }

        content_resp = MagicMock()
        content_resp.status_code = 200
        content_resp.json.return_value = {
            "content": b64_content,
            "encoding": "base64",
            "name": "README.md",
            "download_url": "https://raw.githubusercontent.com/owner/repo/main/README.md",
        }

        session.get.side_effect = [branch_resp, tree_resp, content_resp]

        dl = ReadmeDownloader(session=session)
        path = dl.download("https://github.com/owner/repo")

        assert os.path.exists(path)
        with open(path, "rb") as f:
            assert f.read() == readme_content

    def test_download_raw_fallback(self, tmp_path):
        """If tree and API fail, fall back to raw URL."""
        session = self._mock_session()

        # Branch lookup succeeds
        branch_resp = MagicMock()
        branch_resp.status_code = 200
        branch_resp.json.return_value = {"default_branch": "main"}

        # Tree fails
        tree_resp = MagicMock()
        tree_resp.status_code = 404

        # API fails
        api_resp = MagicMock()
        api_resp.status_code = 404

        # Raw fallback: first candidate succeeds
        raw_resp = MagicMock()
        raw_resp.status_code = 200
        raw_resp.content = b"# Fallback README"

        session.get.side_effect = [branch_resp, tree_resp, api_resp, raw_resp]

        dl = ReadmeDownloader(session=session)
        path = dl.download("https://github.com/owner/repo")

        assert os.path.exists(path)
        with open(path, "rb") as f:
            assert b"Fallback README" in f.read()

    def test_download_raises_when_nothing_found(self):
        """If all strategies fail, raise FileNotFoundError."""
        session = self._mock_session()

        branch_resp = MagicMock()
        branch_resp.status_code = 200
        branch_resp.json.return_value = {"default_branch": "main"}

        fail_resp = MagicMock()
        fail_resp.status_code = 404

        # All calls after branch return 404
        session.get.side_effect = [branch_resp] + [fail_resp] * 20

        dl = ReadmeDownloader(session=session)
        with pytest.raises(FileNotFoundError, match="README not found"):
            dl.download("https://github.com/owner/repo")


# =====================================================================
# Cleanup
# =====================================================================

class TestDownloaderCleanup:
    """Test temp directory management."""

    def test_cleanup_temp_removes_dir(self):
        dl = ReadmeDownloader(session=MagicMock())
        temp = dl.get_temp_dir()
        assert os.path.isdir(temp)
        dl.cleanup_temp()
        assert not os.path.exists(temp)

    def test_cleanup_temp_idempotent(self):
        dl = ReadmeDownloader(session=MagicMock())
        dl.cleanup_temp()
        # Second call should not raise
        dl.cleanup_temp()
