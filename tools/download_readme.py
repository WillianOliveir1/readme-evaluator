"""CLI script moved to tools/ to be a developer helper for downloading READMEs.

This is the same as the former `examples/download_readme.py` but relocated to
`tools/` so it's clearly a developer utility instead of an example used by the
library. The import is updated to use the canonical `backend.download.download`
implementation.
"""
import argparse
import sys
import os
import logging
import requests

# Ensure project root (parent of this tools/ dir) is on sys.path so
# `import backend.download.download` works when running this file directly.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.download.download import ReadmeDownloader


def main(argv=None):
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(description="Download README from GitHub repo")
    parser.add_argument("repo_url", help="Repository URL (e.g. https://github.com/owner/repo)")
    parser.add_argument("-o", "--out", dest="out", help="Output path for README (optional)")
    parser.add_argument("--branch", dest="branch", help="Explicit branch to use (overrides URL/default)")
    args = parser.parse_args(argv)

    # Always run in verbose/debug mode for developer tooling
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    logging.debug("Starting ReadmeDownloader with repo_url=%s branch=%s", args.repo_url, args.branch)
    dl = ReadmeDownloader()
    try:
        path = dl.download(args.repo_url, dest_path=args.out, branch=args.branch)
        logging.info("Saved README to: %s", path)
    except (FileNotFoundError, RuntimeError, requests.RequestException) as e:
        logging.error("Failed to download README: %s", e)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
