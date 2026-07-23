"""Shared LLM prompt utilities for prep pipeline."""

from __future__ import annotations

import re
from pathlib import Path

_SYSTEM_MARKER = "## System / user prompt"


def load_system_prompt(prompt_path: Path) -> str:
    """Extract system instructions between '## System / user prompt' and '## After LLM'."""
    text = prompt_path.read_text(encoding="utf-8")
    if _SYSTEM_MARKER not in text:
        raise ValueError(f"{prompt_path}: missing {_SYSTEM_MARKER!r} section")
    rest = text.split(_SYSTEM_MARKER, 1)[1]
    start_match = re.search(r"^---\s*$", rest, re.MULTILINE)
    if not start_match:
        raise ValueError(f"{prompt_path}: expected --- after system marker")
    body_start = start_match.end()
    end_match = re.search(r"^---\s*\n## After LLM", rest[body_start:], re.MULTILINE)
    body = rest[body_start : body_start + end_match.start()] if end_match else rest[body_start:]
    body = body.strip()
    if not body:
        raise ValueError(f"{prompt_path}: empty system prompt body")
    return body


def strip_markdown_fences(text: str) -> str:
    """Remove surrounding ```markdown or ```md fences from LLM output."""
    text = text.strip()
    text = re.sub(r"^```(?:markdown|md)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()
