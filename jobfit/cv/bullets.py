"""Experience bullet parsing and trailing-suffix restoration from source CV."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from jobfit.cv.companies import _RE_PIPE_ENTRY, _RE_ROLE_COMPANY_PERIOD
from jobfit.cv.contacts import looks_like_contact_line
from jobfit.cv.locations import (
    _EXPERIENCE_SECTION_END_HEADERS,
    _EXPERIENCE_SECTION_HEADERS,
    _RE_LOCATION_BEFORE_DATE,
    _RE_STANDALONE_LOCATION,
    _RE_TRAILING_PERIOD,
    _is_section_header,
    _looks_like_geo_location,
    normalize_period_key,
    period_fingerprint,
)

_RE_TRAILING_LABEL = re.compile(r"\s+\(([^)]+)\)\s*$")
_RE_BULLET_PREFIX = re.compile(r"^[\s]*[-•]\s*")
_MATCH_THRESHOLD = 0.55


def extract_trailing_suffix(bullet: str) -> str | None:
    """Return text inside the final parenthetical at the end of a bullet, if any."""
    if m := _RE_TRAILING_LABEL.search(bullet):
        return m.group(1).strip() or None
    return None


def strip_trailing_suffix(bullet: str) -> str:
    if extract_trailing_suffix(bullet) is None:
        return bullet.strip()
    return _RE_TRAILING_LABEL.sub("", bullet).strip()


# Backward-compatible aliases used by tests and restore.py
extract_trailing_project_label = extract_trailing_suffix
strip_trailing_project_label = strip_trailing_suffix


def _normalize_for_match(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _match_score(source_body: str, output_body: str) -> float:
    a = _normalize_for_match(source_body)
    b = _normalize_for_match(output_body)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _is_bullet_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("-") or stripped.startswith("•"):
        return True
    indent = len(line) - len(line.lstrip())
    return indent >= 3 and len(stripped) > 30


def _extract_period_from_entry_line(line: str) -> str | None:
    if m := _RE_PIPE_ENTRY.match(line):
        return m.group(5).strip()
    if m := _RE_ROLE_COMPANY_PERIOD.match(line):
        return m.group(4).strip()
    if m := _RE_TRAILING_PERIOD.search(line):
        return m.group(1).strip()
    return None


def _is_location_line(line: str) -> bool:
    if m := _RE_LOCATION_BEFORE_DATE.match(line):
        return _looks_like_geo_location(m.group(2), m.group(3))
    if m := _RE_STANDALONE_LOCATION.match(line):
        return len(line.strip()) <= 60 and _looks_like_geo_location(
            m.group(2), m.group(3)
        )
    return False


def parse_experience_bullets_by_period(
    text: str,
) -> dict[str, list[tuple[str, str | None]]]:
    """Map period fingerprints to source bullets as (body, trailing_suffix) pairs."""
    result: dict[str, list[tuple[str, str | None]]] = {}
    in_experience = False
    current_period: str | None = None
    current_bullets: list[tuple[str, str | None]] = []

    def flush() -> None:
        nonlocal current_bullets
        if current_period and current_bullets:
            for key in (
                normalize_period_key(current_period),
                period_fingerprint(current_period),
            ):
                result[key] = list(current_bullets)
        current_bullets = []

    for line in text.splitlines():
        if _is_section_header(line, _EXPERIENCE_SECTION_HEADERS):
            flush()
            in_experience = True
            current_period = None
            continue
        if in_experience and _is_section_header(line, _EXPERIENCE_SECTION_END_HEADERS):
            flush()
            break
        if not in_experience or looks_like_contact_line(line):
            continue

        if period := _extract_period_from_entry_line(line):
            flush()
            current_period = period
            continue

        if _is_location_line(line):
            continue

        if _is_bullet_line(line):
            raw = _RE_BULLET_PREFIX.sub("", line.strip())
            suffix = extract_trailing_suffix(raw)
            body = strip_trailing_suffix(raw)
            current_bullets.append((body, suffix))

    flush()
    return result


def restore_experience_project_labels(cv_data: dict[str, Any], cv_text: str) -> None:
    """Re-append trailing parenthetical suffixes from the source CV when the LLM drops them."""
    from jobfit.cv.text import strip_frontmatter

    by_period = parse_experience_bullets_by_period(strip_frontmatter(cv_text))

    for entry in cv_data.get("experience", []):
        if not isinstance(entry, dict):
            continue
        period = entry.get("period")
        if not isinstance(period, str):
            continue

        source_bullets: list[tuple[str, str | None]] | None = None
        for key in (normalize_period_key(period), period_fingerprint(period)):
            if key in by_period:
                source_bullets = by_period[key]
                break
        if not source_bullets:
            continue

        bullets = entry.get("bullets")
        if not isinstance(bullets, list):
            continue

        used_indices: set[int] = set()
        for index, bullet in enumerate(bullets):
            if not isinstance(bullet, str) or extract_trailing_suffix(bullet):
                continue

            output_body = bullet.strip()
            best_idx = -1
            best_score = _MATCH_THRESHOLD

            for src_idx, (src_body, suffix) in enumerate(source_bullets):
                if src_idx in used_indices or not suffix:
                    continue
                score = _match_score(src_body, output_body)
                if score > best_score:
                    best_score = score
                    best_idx = src_idx

            if best_idx >= 0:
                suffix = source_bullets[best_idx][1]
                bullets[index] = f"{output_body.rstrip()} ({suffix})"
                used_indices.add(best_idx)
