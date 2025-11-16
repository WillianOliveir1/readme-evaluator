"""Backend package init for readme-evaluator.

This package exposes small service modules grouped by responsibility:
- download: downloading README files from GitHub
- evaluate: functions to extract structured JSON from README using an LLM
- db: persistence helpers (MongoDB or file fallback)
- present: rendering JSON to human-readable text via an LLM
- gemini_client: Google Gemini (GenAI) client

The canonical README downloader implementation is available under
``backend.download.download.ReadmeDownloader``. Legacy module file was removed
to avoid duplication — developer utilities were moved to ``tools/``.
"""

from . import gemini_client  # expose the Gemini client as backend.gemini_client
from . import download  # expose the download package (canonical downloader)

__all__ = [
    "gemini_client",
    "download",
]
