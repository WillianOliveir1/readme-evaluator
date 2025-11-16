"""CLI script for downloading READMEs from GitHub repositories.

Downloads are automatically saved to a temporary directory, then moved to
the final destination directory when specified.
"""
import argparse
import sys
import os
import logging
import requests

# Ensure project root (parent of this tools/ dir) is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.download.download import ReadmeDownloader


def main(argv=None):
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(description="Download README from GitHub repo")
    parser.add_argument("repo_url", help="Repository URL (e.g. https://github.com/owner/repo)")
    parser.add_argument("-d", "--dest", dest="dest", help="Final destination directory (optional)")
    parser.add_argument("--branch", dest="branch", help="Explicit branch to use (overrides URL/default)")
    args = parser.parse_args(argv)

    # Run in debug mode for visibility
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    logging.debug("Starting ReadmeDownloader with repo_url=%s branch=%s", args.repo_url, args.branch)
    
    dl = ReadmeDownloader()
    try:
        # Download to temp directory
        temp_path = dl.download(args.repo_url, branch=args.branch)
        
        # If destination specified, move there
        if args.dest:
            final_path = dl.move_to_final(temp_path, args.dest)
            logging.info("File available at: %s", final_path)
        else:
            logging.info("File available at: %s", temp_path)
            logging.info("Temp directory: %s", dl.get_temp_dir())
        
    except (FileNotFoundError, RuntimeError, requests.RequestException) as e:
        logging.error("Failed to download README: %s", e)
        dl.cleanup_temp()
        return 2
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
