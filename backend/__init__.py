"""Backend package init for readme-evaluator.

This package exposes small service modules grouped by responsibility:
- download: downloading README files from GitHub
- evaluate: functions to extract structured JSON from README using an LLM
- db: persistence helpers (MongoDB or file fallback)
- present: rendering JSON to human-readable text via an LLM
- hf_client: Hugging Face inference client

The canonical README downloader implementation is available under
``backend.download.download.ReadmeDownloader``. Legacy module file was removed
to avoid duplication — developer utilities were moved to ``tools/``.
"""

from . import hf_client  # keep hf_client importable as backend.hf_client
from . import download  # expose the download package (canonical downloader)

__all__ = [
    "hf_client",
    "download",
]
