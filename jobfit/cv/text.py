"""Shared CV text helpers."""

from __future__ import annotations

import re

_SECTION_HEADERS = frozenset({
    "SUMMARY", "PROFILE", "PROFESSIONAL EXPERIENCE", "WORK EXPERIENCE",
    "EXPERIENCE", "SKILLS", "SKILLS & TECHNOLOGIES", "EDUCATION",
    "CERTIFICATIONS", "LANGUAGES", "PROJECTS",
})


def strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter block if present."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4 :].lstrip("\n")


def looks_like_name(line: str) -> bool:
    if len(line) > 80 or len(line.split()) > 6:
        return False
    if not re.match(r"^[\w\s\-–—'.()/]+$", line, re.UNICODE):
        return False
    if line.endswith(".") and not line.endswith("..."):
        return False
    words = line.split()
    if line.isupper():
        return True
    if any(word[:1].isupper() for word in words if word):
        return not line.islower()
    return False
