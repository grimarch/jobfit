"""Education institution parsing, LLM anonymization, and post-LLM restoration."""

from __future__ import annotations

from dataclasses import dataclass

from jobfit.cv.contacts import looks_like_contact_line
from jobfit.cv.locations import (
    _EDUCATION_SECTION_END_HEADERS,
    _EDUCATION_SECTION_HEADERS,
    _RE_TRAILING_LOCATION,
    _is_certifications_subsection,
    _is_section_header,
    normalize_period_key,
    parse_education_locations,
    period_fingerprint,
)


@dataclass(frozen=True)
class EducationInstitution:
    """One education institution anchored by its degree period."""

    period: str
    institution: str


def edu_inst_token(index: int) -> str:
    return f"[EDU_INST_{index}]"


def parse_education_institutions(text: str) -> list[EducationInstitution]:
    """Extract institution names from CV body text (frontmatter already stripped)."""
    return [
        EducationInstitution(period=entry.period, institution=entry.institution)
        for entry in parse_education_locations(text)
        if entry.institution.strip()
    ]


def build_education_institution_index(text: str) -> dict[str, str]:
    """Map period fingerprints to original institution names."""
    index: dict[str, str] = {}
    for entry in parse_education_institutions(text):
        if not entry.period:
            continue
        index[normalize_period_key(entry.period)] = entry.institution
        index[period_fingerprint(entry.period)] = entry.institution
    return index


def build_edu_inst_token_map(text: str) -> dict[str, str]:
    """Map [EDU_INST_N] tokens to original institution names."""
    token_map: dict[str, str] = {}
    token_by_institution: dict[str, str] = {}
    next_index = 1

    for entry in parse_education_institutions(text):
        if entry.institution not in token_by_institution:
            token = edu_inst_token(next_index)
            next_index += 1
            token_by_institution[entry.institution] = token
            token_map[token] = entry.institution

    return token_map


def _replace_institutions_in_line(
    line: str, institution_to_token: dict[str, str]
) -> str:
    for institution, token in sorted(
        institution_to_token.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if institution in line:
            return line.replace(institution, token)
    return line


def _redact_structured_institution_line(
    line: str, institution_to_token: dict[str, str]
) -> str:
    if m := _RE_TRAILING_LOCATION.match(line):
        institution = m.group(1).strip()
        token = institution_to_token.get(institution)
        if not token:
            return line
        location = f"{m.group(2).strip()}, {m.group(3).strip()}"
        gap = max(3, len(line) - len(token) - len(location))
        return f"{token}{' ' * gap}{location}"

    return line


def redact_education_institutions(text: str) -> str:
    """Replace education institution names with [EDU_INST_N] placeholders for LLM prompts."""
    token_map = build_edu_inst_token_map(text)
    if not token_map:
        return text

    institution_to_token = {
        institution: token for token, institution in token_map.items()
    }

    lines: list[str] = []
    in_education = False

    for line in text.splitlines():
        if _is_section_header(line, _EDUCATION_SECTION_HEADERS):
            in_education = True
            lines.append(line)
            continue
        if in_education and _is_section_header(line, _EDUCATION_SECTION_END_HEADERS):
            in_education = False
        if in_education and _is_certifications_subsection(line):
            in_education = False

        if in_education and not looks_like_contact_line(line):
            line = _redact_structured_institution_line(line, institution_to_token)
            line = _replace_institutions_in_line(line, institution_to_token)

        lines.append(line)

    return "\n".join(lines)
