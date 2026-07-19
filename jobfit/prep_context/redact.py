"""Redact PII from job description excerpts for prep context export."""

from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)


def redact_excerpt(text: str, firma: str, max_chars: int) -> str:
    """Return a truncated, anonymized JD excerpt.

    Replaces: company name → [COMPANY], http(s) URLs → [URL], emails → [EMAIL].
    Returns empty string when max_chars == 0.
    """
    if max_chars == 0:
        return ""
    excerpt = text[:max_chars] if max_chars > 0 else text
    if firma:
        excerpt = re.sub(re.escape(firma), "[COMPANY]", excerpt, flags=re.IGNORECASE)
    excerpt = _URL_RE.sub("[URL]", excerpt)
    excerpt = _EMAIL_RE.sub("[EMAIL]", excerpt)
    # Normalize whitespace for single-line embedding
    excerpt = " ".join(excerpt.split())
    return excerpt
