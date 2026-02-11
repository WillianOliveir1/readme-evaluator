"""Centralized rate-limiting configuration.

Uses `slowapi` (which wraps `limits`) to enforce per-IP request quotas.
The limiter instance is imported by each router that needs protection.

Env vars
--------
RATE_LIMIT_DEFAULT : str
    Default limit applied to *all* routes (e.g. ``"60/minute"``).
RATE_LIMIT_EXPENSIVE : str
    Stricter limit for Gemini / extraction endpoints (e.g. ``"10/minute"``).
"""
from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# Read limits from environment; sensible defaults for production.
DEFAULT_LIMIT: str = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")
EXPENSIVE_LIMIT: str = os.getenv("RATE_LIMIT_EXPENSIVE", "10/minute")

# Single limiter instance shared across the app
limiter = Limiter(key_func=get_remote_address, default_limits=[DEFAULT_LIMIT])

__all__ = ["limiter", "DEFAULT_LIMIT", "EXPENSIVE_LIMIT"]
