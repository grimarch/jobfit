"""Employer name parsing, LLM anonymization, and post-LLM restoration."""

from __future__ import annotations

import re
from dataclasses import dataclass

from jobfit.cv.contacts import looks_like_contact_line
from jobfit.cv.locations import (
    _EXPERIENCE_SECTION_END_HEADERS,
    _EXPERIENCE_SECTION_HEADERS,
    _RE_LOCATION_BEFORE_DATE,
    _RE_STANDALONE_LOCATION,
    _is_section_header,
    _looks_like_geo_location,
    normalize_period_key,
    period_fingerprint,
)

_RE_ROLE_COMPANY_PERIOD = re.compile(
    r"^(\s*)(.+?)\s*[-–—]\s*(.+?)\s{2,}"
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|Present|\d{4}).+)$",
    re.IGNORECASE,
)
_RE_PIPE_ENTRY = re.compile(
    r"^(\s*)(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)\s*$",
)


@dataclass(frozen=True)
class ExperienceCompany:
    """One employer name anchored by its date range."""

    period: str
    company: str


def work_comp_token(index: int) -> str:
    return f"[WORK_COMP_{index}]"


def _is_standalone_location_line(line: str) -> bool:
    if m := _RE_LOCATION_BEFORE_DATE.match(line):
        return _looks_like_geo_location(m.group(2), m.group(3))
    if m := _RE_STANDALONE_LOCATION.match(line):
        return len(line.strip()) <= 60 and _looks_like_geo_location(m.group(2), m.group(3))
    return False


def _append_standalone_company(
    entries: list[ExperienceCompany],
    pending_period: str | None,
    standalone_lines: list[str],
) -> None:
    if pending_period and standalone_lines:
        company = standalone_lines[-1].strip()
        if company:
            entries.append(ExperienceCompany(period=pending_period, company=company))


def parse_experience_companies(text: str) -> list[ExperienceCompany]:
    """Extract employer names from CV body text (frontmatter already stripped)."""
    entries: list[ExperienceCompany] = []
    in_experience = False
    pending_period: str | None = None
    standalone_lines: list[str] = []

    def flush_standalone() -> None:
        nonlocal standalone_lines
        _append_standalone_company(entries, pending_period, standalone_lines)
        standalone_lines = []

    for line in text.splitlines():
        if _is_section_header(line, _EXPERIENCE_SECTION_HEADERS):
            in_experience = True
            pending_period = None
            standalone_lines = []
            continue
        if in_experience and _is_section_header(line, _EXPERIENCE_SECTION_END_HEADERS):
            flush_standalone()
            break
        if not in_experience:
            continue
        if (
            looks_like_contact_line(line)
            and not _RE_PIPE_ENTRY.match(line)
            and not _RE_ROLE_COMPANY_PERIOD.match(line)
        ):
            continue

        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("-") or stripped.startswith("•"):
            flush_standalone()
            pending_period = None
            continue

        if m := _RE_PIPE_ENTRY.match(line):
            flush_standalone()
            pending_period = None
            company = m.group(3).strip()
            period = m.group(5).strip()
            if company and period:
                entries.append(ExperienceCompany(period=period, company=company))
            continue

        if m := _RE_ROLE_COMPANY_PERIOD.match(line):
            flush_standalone()
            company = m.group(3).strip()
            period = m.group(4).strip()
            pending_period = None
            if company and period:
                entries.append(ExperienceCompany(period=period, company=company))
            continue

        if m := _RE_LOCATION_BEFORE_DATE.match(line):
            flush_standalone()
            if _looks_like_geo_location(m.group(2), m.group(3)):
                pending_period = m.group(5).strip()
                standalone_lines = []
            else:
                pending_period = None
            continue

        if _is_standalone_location_line(line):
            flush_standalone()
            pending_period = None
            continue

        if pending_period is not None:
            if len(standalone_lines) >= 2:
                flush_standalone()
            standalone_lines.append(stripped)

    flush_standalone()
    return entries


def build_experience_company_index(text: str) -> dict[str, str]:
    """Map period fingerprints to original employer names."""
    index: dict[str, str] = {}
    for entry in parse_experience_companies(text):
        index[normalize_period_key(entry.period)] = entry.company
        index[period_fingerprint(entry.period)] = entry.company
    return index


def build_work_comp_token_map(text: str) -> dict[str, str]:
    """Map [WORK_COMP_N] tokens to original employer names."""
    token_map: dict[str, str] = {}
    token_by_company: dict[str, str] = {}
    next_index = 1

    for entry in parse_experience_companies(text):
        if entry.company not in token_by_company:
            token = work_comp_token(next_index)
            next_index += 1
            token_by_company[entry.company] = token
            token_map[token] = entry.company

    return token_map


def _replace_companies_in_line(line: str, company_to_token: dict[str, str]) -> str:
    for company, token in sorted(company_to_token.items(), key=lambda item: len(item[0]), reverse=True):
        if company in line:
            return line.replace(company, token)
    return line


def _redact_structured_company_line(line: str, company_to_token: dict[str, str]) -> str:
    if m := _RE_PIPE_ENTRY.match(line):
        company = m.group(3).strip()
        token = company_to_token.get(company)
        if not token:
            return line
        return (
            f"{m.group(1)}{m.group(2).strip()} | {token} | "
            f"{m.group(4).strip()} | {m.group(5).strip()}"
        )

    if m := _RE_ROLE_COMPANY_PERIOD.match(line):
        company = m.group(3).strip()
        token = company_to_token.get(company)
        if not token:
            return line
        gap = max(2, len(line) - len(m.group(1)) - len(m.group(2)) - len(token) - len(m.group(4)) - 3)
        return f"{m.group(1)}{m.group(2).strip()} – {token}{' ' * gap}{m.group(4).strip()}"

    return line


def redact_experience_companies(text: str) -> str:
    """Replace employer names with [WORK_COMP_N] placeholders for LLM prompts."""
    token_map = build_work_comp_token_map(text)
    if not token_map:
        return text

    company_to_token = {company: token for token, company in token_map.items()}

    lines: list[str] = []
    in_experience = False

    for line in text.splitlines():
        if _is_section_header(line, _EXPERIENCE_SECTION_HEADERS):
            in_experience = True
            lines.append(line)
            continue
        if in_experience and _is_section_header(line, _EXPERIENCE_SECTION_END_HEADERS):
            in_experience = False

        if in_experience and (
            not looks_like_contact_line(line)
            or _RE_PIPE_ENTRY.match(line)
            or _RE_ROLE_COMPANY_PERIOD.match(line)
        ):
            line = _redact_structured_company_line(line, company_to_token)
            line = _replace_companies_in_line(line, company_to_token)

        lines.append(line)

    return "\n".join(lines)
