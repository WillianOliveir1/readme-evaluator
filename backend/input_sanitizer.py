"""Input sanitization to mitigate prompt injection attacks.

This module provides utilities to sanitize user-supplied text before it
is embedded into LLM prompts.  The goal is defence-in-depth: we do NOT
rely solely on the system prompt to resist injection.  Instead we strip
or neutralise common injection patterns before the text reaches the
prompt builder.

Strategies used:
1. **Delimiter enforcement** – wrap the untrusted content in clear delimiters
   so the model treats it as data, not instructions.
2. **Instruction-stripping** – remove or escape common injection phrases
   (e.g. "ignore previous instructions", "you are now…").
3. **Length limiting** – truncate excessively long inputs that may be trying
   to exhaust the context window and push out the real instructions.
4. **Control character removal** – strip invisible Unicode that could be
   used to hide payloads.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


# ---------------------------------------------------------------------------
# Known injection patterns (case-insensitive)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        # Direct instruction overrides
        r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?|context)",
        r"disregard\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)",
        r"forget\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)",
        r"override\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)",
        # Role reassignment
        r"you\s+are\s+now\s+",
        r"act\s+as\s+(if\s+you\s+are|a)\s+",
        r"pretend\s+(you\s+are|to\s+be)\s+",
        r"your\s+new\s+(role|instructions?|task|purpose)\s+",
        # System prompt leaking
        r"(show|reveal|print|output|display|repeat)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions?|rules?|configuration)",
        r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions?|rules?)",
        # Delimiter escape
        r"<\s*/?\s*(system|instruction|user|assistant)\s*>",
        r"\[/?INST\]",
        r"###\s*(system|instruction|user|assistant)",
        # Output manipulation
        r"(return|output|print)\s+only\s+",
        r"do\s+not\s+(follow|obey|listen)",
    ]
]


# Characters that should be stripped (invisible/control characters)
_CONTROL_CHAR_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f"
    r"\u200b-\u200f"           # Zero-width chars
    r"\u202a-\u202e"           # Bidi overrides
    r"\u2060-\u2064"           # Invisible formatters
    r"\ufeff"                  # BOM
    r"\ufff9-\ufffb"          # Interlinear annotation
    r"]"
)


# Maximum length for user-supplied README text (≈ 500 KB is generous for any README)
MAX_README_LENGTH = 500_000
MAX_SYSTEM_PROMPT_LENGTH = 10_000


def _strip_control_chars(text: str) -> str:
    """Remove invisible control / formatting characters."""
    return _CONTROL_CHAR_RE.sub("", text)


def _normalise_unicode(text: str) -> str:
    """Normalise to NFC form to collapse sneaky homoglyph variants."""
    return unicodedata.normalize("NFC", text)


def _neutralise_injections(text: str) -> str:
    """Replace known injection patterns with a harmless marker.

    The replacement makes it clear to a human reviewer what happened,
    and prevents the model from interpreting the payload.
    """
    for pattern in _INJECTION_PATTERNS:
        text = pattern.sub("[FILTERED]", text)
    return text


def sanitize_readme(text: str, max_length: int = MAX_README_LENGTH) -> str:
    """Sanitise a user-supplied README body before embedding in a prompt.

    Returns the cleaned text.  The function is idempotent.
    """
    if not text:
        return text

    text = _strip_control_chars(text)
    text = _normalise_unicode(text)
    text = _neutralise_injections(text)

    # Truncate if excessively long
    if len(text) > max_length:
        text = text[:max_length] + "\n\n[... content truncated for safety ...]"

    return text


def sanitize_system_prompt(text: Optional[str], max_length: int = MAX_SYSTEM_PROMPT_LENGTH) -> Optional[str]:
    """Sanitise a user-supplied system prompt override.

    This is stricter than README sanitisation because a custom system prompt
    can directly alter model behaviour.
    """
    if not text:
        return text

    text = _strip_control_chars(text)
    text = _normalise_unicode(text)
    # For system prompts we still neutralise injections but keep the
    # patterns less aggressive since the user *is* expected to give
    # instructions.  We mainly strip role-reassignment and prompt-leak
    # attempts.
    text = _neutralise_injections(text)

    if len(text) > max_length:
        text = text[:max_length]

    return text


def wrap_in_delimiters(text: str, label: str = "USER_CONTENT") -> str:
    """Wrap text in clear XML-style delimiters for the LLM.

    This makes it explicit that the content between delimiters is data and
    should not be interpreted as instructions.
    """
    return f"<{label}>\n{text}\n</{label}>"
