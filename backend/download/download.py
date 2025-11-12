"""Readme downloader module moved under backend.download.

This is largely a copy of the previous `backend/readme_downloader.py` but
kept here to provide a clearer package layout.
"""
from __future__ import annotations

import base64
import os
import re
from typing import Optional, Tuple
import logging

import requests


class ReadmeDownloader:
    """Download README from a GitHub repository.

    Supports unauthenticated requests. Optionally pass a GitHub token via
    the GITHUB_TOKEN environment variable or the `github_token` constructor arg
    to increase rate limits.
    """

    GITHUB_API = "https://api.github.com"
    RAW_BASE = "https://raw.githubusercontent.com"

    def __init__(self, github_token: Optional[str] = None, session: Optional[requests.Session] = None):
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")
        self.session = session or requests.Session()
        if self.github_token:
            self.session.headers.update({"Authorization": f"token {self.github_token}"})

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

    def _get_readme_api(self, owner: str, repo: str) -> Optional[Tuple[str, bytes]]:
        url = f"{self.GITHUB_API}/repos/{owner}/{repo}/readme"
        r = self.session.get(url, headers={"Accept": "application/vnd.github.v3+json"})
        if r.status_code == 200:
            data = r.json()
            content = data.get("content")
            encoding = data.get("encoding")
            name = data.get("name") or "README"
            if content and encoding == "base64":
                raw = base64.b64decode(content)
                return name, raw
        return None

    def _get_tree(self, owner: str, repo: str, branch: str) -> Optional[list]:
        url = f"{self.GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}"
        r = self.session.get(url, params={"recursive": "1"}, headers={"Accept": "application/vnd.github.v3+json"})
        if r.status_code == 200:
            data = r.json()
            return data.get("tree", [])
        return None

    def _find_readme_in_tree(self, tree: list) -> Optional[str]:
        for entry in tree:
            if entry.get("type") != "blob":
                continue
            path = entry.get("path", "")
            name = os.path.basename(path)
            if re.match(r"(?i)^readme(?:\.|$)", name):
                return path
        return None

    def _get_content_by_path(self, owner: str, repo: str, path: str, ref: Optional[str]) -> Optional[Tuple[str, bytes]]:
        params = {"ref": ref} if ref else None
        url = f"{self.GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
        r = self.session.get(url, params=params, headers={"Accept": "application/vnd.github.v3+json"})
        if r.status_code == 200:
            data = r.json()
            content = data.get("content")
            encoding = data.get("encoding")
            name = data.get("name") or os.path.basename(path)
            if content and encoding == "base64":
                return name, base64.b64decode(content)
        return None

    def _try_raw_fallback(self, owner: str, repo: str, branch: Optional[str]) -> Optional[Tuple[str, bytes]]:
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
                return name, r.content
        return None

    def download(self, repo_url: str, dest_path: Optional[str] = None, prefer_api: bool = True, branch: Optional[str] = None) -> str:
        owner, repo, parsed_branch = self._parse_repo(repo_url)
        logging.debug("Parsed repo_url=%s -> owner=%s repo=%s parsed_branch=%s", repo_url, owner, repo, parsed_branch)

        filename = None
        content = None

        branch_to_use = branch or parsed_branch
        if branch_to_use is None:
            try:
                branch_to_use = self._get_default_branch(owner, repo)
            except requests.RequestException:
                branch_to_use = None

        if branch_to_use:
            try:
                tree = self._get_tree(owner, repo, branch_to_use)
            except requests.RequestException:
                tree = None

            if tree:
                readme_path = self._find_readme_in_tree(tree)
                if readme_path:
                    try:
                        res = self._get_content_by_path(owner, repo, readme_path, ref=branch_to_use)
                        if res:
                            filename, content = res
                    except requests.RequestException:
                        filename = None
                        content = None

        if not content and prefer_api:
            try:
                res = self._get_readme_api(owner, repo)
                if res:
                    filename, content = res
            except requests.RequestException:
                filename = None
                content = None

        if not content:
            try:
                result = self._try_raw_fallback(owner, repo, branch_to_use)
            except requests.RequestException as exc:
                raise RuntimeError(f"Network error while trying raw fallback: {exc}") from exc
            if result:
                filename, content = result

        if not content:
            raise FileNotFoundError(f"README not found for repository {owner}/{repo}")

        if dest_path is None:
            safe_name = f"{owner}-{repo}-{filename}"
            dest_path = os.path.join(os.getcwd(), safe_name)

        with open(dest_path, "wb") as f:
            f.write(content)

        return dest_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download README from a GitHub repo")
    parser.add_argument("repo_url", help="URL of the GitHub repository")
    parser.add_argument("--out", "-o", dest="out", help="Destination path to save README")
    args = parser.parse_args()

    dl = ReadmeDownloader()
    path = dl.download(args.repo_url, dest_path=args.out)
    print(f"Saved README to: {path}")
