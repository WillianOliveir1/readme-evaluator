"""Readme downloader module moved under backend.download.

This is largely a copy of the previous `backend/readme_downloader.py` but
kept here to provide a clearer package layout.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import tempfile
from typing import Optional, Tuple
import logging

import requests

from backend.config import GITHUB_TOKEN


class ReadmeDownloader:
    """Download README from a GitHub repository.

    Supports unauthenticated requests. Optionally pass a GitHub token via
    the GITHUB_TOKEN environment variable or the `github_token` constructor arg
    to increase rate limits.
    """

    GITHUB_API = "https://api.github.com"
    RAW_BASE = "https://raw.githubusercontent.com"

    def __init__(self, github_token: Optional[str] = None, session: Optional[requests.Session] = None):
        self.github_token = github_token or GITHUB_TOKEN
        self.session = session or requests.Session()
        if self.github_token:
            self.session.headers.update({"Authorization": f"token {self.github_token}"})
        
        # Automatically create temporary directory for all downloads
        self.temp_dir = tempfile.mkdtemp(prefix="readme_download_")
        self.readme_url = None  # Store the URL of the downloaded README
        logging.debug("Using temp directory: %s", self.temp_dir)

    def _parse_repo(self, url: str) -> Tuple[str, str, Optional[str]]:
        m = re.match(r"git@github.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$", url)
        if m:
            return m.group("owner"), m.group("repo"), None

        m = re.match(
            r"https?://github.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)(?:\.git)?(?:/(?:tree|blob)/(?P<branch>[^/]+))?",
            url,
        )
        if m:
            repo = m.group("repo")
            branch = m.group("branch")
            return m.group("owner"), repo, branch

        raise ValueError(f"Could not parse GitHub repository from URL: {url}")

    def _get_default_branch(self, owner: str, repo: str) -> Optional[str]:
        url = f"{self.GITHUB_API}/repos/{owner}/{repo}"
        r = self.session.get(url, headers={"Accept": "application/vnd.github.v3+json"})
        if r.status_code == 200:
            data = r.json()
            return data.get("default_branch")
        return None

    def _get_readme_api(self, owner: str, repo: str) -> Optional[Tuple[str, bytes, str]]:
        url = f"{self.GITHUB_API}/repos/{owner}/{repo}/readme"
        r = self.session.get(url, headers={"Accept": "application/vnd.github.v3+json"})
        if r.status_code == 200:
            data = r.json()
            content = data.get("content")
            encoding = data.get("encoding")
            name = data.get("name") or "README"
            download_url = data.get("download_url")
            if content and encoding == "base64":
                raw = base64.b64decode(content)
                return name, raw, download_url
        return None

    def _get_tree(self, owner: str, repo: str, branch: str) -> Optional[list]:
        url = f"{self.GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}"
        r = self.session.get(url, params={"recursive": "1"}, headers={"Accept": "application/vnd.github.v3+json"})
        if r.status_code == 200:
            data = r.json()
            return data.get("tree", [])
        return None

    def _find_readme_in_tree(self, tree: list) -> Optional[str]:
        """Find README file in repository tree, prioritizing files closest to root.
        
        Returns the README file with the fewest directory levels (slashes in path).
        This ensures preference for root-level READMEs over nested ones.
        """
        readme_files = []
        
        for entry in tree:
            if entry.get("type") != "blob":
                continue
            path = entry.get("path", "")
            name = os.path.basename(path)
            if re.match(r"(?i)^readme(?:\.|$)", name):
                readme_files.append(path)
        
        if not readme_files:
            return None
        
        # Sort by depth (number of slashes) to prioritize root-level READMEs
        # e.g., "README.md" (0 slashes) before "docs/README.md" (1 slash)
        readme_files.sort(key=lambda p: p.count('/'))
        return readme_files[0]

    def _get_content_by_path(self, owner: str, repo: str, path: str, ref: Optional[str]) -> Optional[Tuple[str, bytes, str]]:
        params = {"ref": ref} if ref else None
        url = f"{self.GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
        r = self.session.get(url, params=params, headers={"Accept": "application/vnd.github.v3+json"})
        if r.status_code == 200:
            data = r.json()
            content = data.get("content")
            encoding = data.get("encoding")
            name = data.get("name") or os.path.basename(path)
            download_url = data.get("download_url")
            if content and encoding == "base64":
                return name, base64.b64decode(content), download_url
        return None

    def _try_raw_fallback(self, owner: str, repo: str, branch: Optional[str]) -> Optional[Tuple[str, bytes, str]]:
        if branch is None:
            branch = "main"
        candidates = [
            "README.md",
            "Readme.md",
            "readme.md",
            "README.MD",
            "README.rst",
            "README.txt",
            "README",
        ]
        for name in candidates:
            url = f"{self.RAW_BASE}/{owner}/{repo}/{branch}/{name}"
            r = self.session.get(url)
            if r.status_code == 200:
                return name, r.content, url
        return None

    def download(self, repo_url: str, prefer_api: bool = True, branch: Optional[str] = None) -> str:
        """Download README and save to temporary directory.
        
        All downloads are automatically saved to the temporary directory.
        Use move_to_final() to move to permanent storage when ready.
        
        Args:
            repo_url: GitHub repository URL
            prefer_api: Whether to prefer GitHub API method
            branch: Optional explicit branch to use
        
        Returns:
            Path to the downloaded README file in temp directory
        """
        owner, repo, parsed_branch = self._parse_repo(repo_url)
        logging.info("Downloading README from %s/%s", owner, repo)
        logging.debug("Parsed repo_url=%s -> owner=%s repo=%s parsed_branch=%s", repo_url, owner, repo, parsed_branch)

        filename = None
        content = None

        branch_to_use = branch or parsed_branch
        if branch_to_use is None:
            try:
                logging.debug("Fetching default branch...")
                branch_to_use = self._get_default_branch(owner, repo)
                logging.debug("Default branch: %s", branch_to_use)
            except requests.RequestException as e:
                logging.warning("Failed to get default branch: %s", e)
                branch_to_use = None

        if branch_to_use:
            try:
                logging.debug("Fetching repository tree for branch %s...", branch_to_use)
                tree = self._get_tree(owner, repo, branch_to_use)
            except requests.RequestException as e:
                logging.warning("Failed to get repository tree: %s", e)
                tree = None

            if tree:
                logging.debug("Searching for README in tree...")
                readme_path = self._find_readme_in_tree(tree)
                if readme_path:
                    try:
                        logging.debug("Found README at: %s", readme_path)
                        res = self._get_content_by_path(owner, repo, readme_path, ref=branch_to_use)
                        if res:
                            filename, content, url = res
                            self.readme_url = url
                            logging.info("README downloaded via tree method: %s", filename)
                    except requests.RequestException as e:
                        logging.warning("Failed to fetch content by path: %s", e)
                        filename = None
                        content = None
                else:
                    logging.debug("README not found in tree")

        if not content and prefer_api:
            try:
                logging.debug("Trying GitHub API endpoint...")
                res = self._get_readme_api(owner, repo)
                if res:
                    filename, content, url = res
                    self.readme_url = url
                    logging.info("README downloaded via API method: %s", filename)
            except requests.RequestException as e:
                logging.warning("Failed to fetch via API: %s", e)
                filename = None
                content = None

        # Fallback to raw content if API methods failed
        if not content:
            try:
                logging.debug("Trying raw content fallback...")
                res = self._try_raw_fallback(owner, repo, branch_to_use)
                if res:
                    filename, content, url = res
                    self.readme_url = url
                    logging.info("README downloaded via raw fallback: %s", filename)
            except requests.RequestException as e:
                logging.warning("Failed to fetch via raw fallback: %s", e)
                filename = None
                content = None

        if not content:
            raise FileNotFoundError(f"README not found for repository {owner}/{repo}")

        # Always save to temp directory
        safe_name = f"{owner}-{repo}-{filename}"
        temp_path = os.path.join(self.temp_dir, safe_name)
        
        logging.debug("Saving to temp: %s", temp_path)
        with open(temp_path, "wb") as f:
            f.write(content)

        logging.info("README successfully saved to: %s", temp_path)
        return temp_path
    
    def move_to_final(self, source_path: str, final_dir: str) -> str:
        """Move a downloaded README from temp directory to final destination.
        
        Args:
            source_path: Path to file in temp directory
            final_dir: Destination directory for final storage
        
        Returns:
            Path to the file in final directory
        """
        os.makedirs(final_dir, exist_ok=True)
        filename = os.path.basename(source_path)
        final_path = os.path.join(final_dir, filename)
        
        logging.debug("Moving from temp to final: %s -> %s", source_path, final_path)
        shutil.move(source_path, final_path)
        logging.info("File moved to final destination: %s", final_path)
        
        return final_path
    
    def cleanup_temp(self) -> None:
        """Remove temporary directory and all downloaded files."""
        if os.path.exists(self.temp_dir):
            logging.debug("Cleaning up temp directory: %s", self.temp_dir)
            shutil.rmtree(self.temp_dir)
            logging.info("Temp directory cleaned up")
    
    def get_temp_dir(self) -> str:
        """Get the temporary directory path."""
        return self.temp_dir
