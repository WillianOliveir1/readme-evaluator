"""Centralized logging configuration for the backend.

Call ``setup_logging()`` once at application startup (from ``main.py``) to
configure the root logger with a consistent JSON-like format.

Individual modules should obtain their own logger with::

    import logging
    log = logging.getLogger(__name__)
"""
from __future__ import annotations

import logging
import os
import sys


def setup_logging() -> None:
    """Configure the root logger.

    • **LOG_FORMAT=json** (default in production): each record is a single
      JSON-like line suited for log aggregation tools.
    • **LOG_FORMAT=text**: human-friendly format for local development.

    The log level is controlled by the ``LOG_LEVEL`` env-var (default: INFO).
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log_format = os.getenv("LOG_FORMAT", "json").lower()

    if log_format == "json":
        fmt = (
            '{"time":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","message":"%(message)s"}'
        )
    else:
        fmt = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))

    root = logging.getLogger()
    # Remove any existing handlers to avoid duplicates on reload
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet noisy third-party loggers
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
