"""CV location parsing, LLM anonymization, and post-LLM restoration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from jobfit.cv.contacts import looks_like_contact_line

_EXPERIENCE_SECTION_HEADERS = frozenset({
    "PROFESSIONAL EXPERIENCE",
    "WORK EXPERIENCE",
    "EXPERIENCE",
})
_EDUCATION_SECTION_HEADERS = frozenset({
    "EDUCATION",
    "EDUCATION & CERTIFICATIONS",
})
_EXPERIENCE_SECTION_END_HEADERS = frozenset({
    "EDUCATION",
    "EDUCATION & CERTIFICATIONS",
    "SKILLS",
    "SKILLS & TECHNOLOGIES",
    "CERTIFICATIONS",
    "LANGUAGES",
    "PROJECTS",
    "ADDITIONAL INFORMATION",
})
_EDUCATION_SECTION_END_HEADERS = frozenset({
    "SKILLS",
    "SKILLS & TECHNOLOGIES",
    "LANGUAGES",
    "PROJECTS",
    "ADDITIONAL INFORMATION",
})

_RE_LOCATION_BEFORE_DATE = re.compile(
    r"^(\s*)([\w][\w\s&./-]{0,50}?),\s*([\w][\w\s-]{0,30}?)"
    r"(\s{3,}((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|Present|\d{4}).+))$",
    re.IGNORECASE,
)
_RE_STANDALONE_LOCATION = re.compile(
    r"^(\s*)([\w][\w\s&./-]{0,50}?),\s*([\w][\w\s-]{0,30}?)\s*$",
)
_RE_TRAILING_LOCATION = re.compile(
    r"^(.+?)\s{3,}([\w][\w\s-]{0,50}?),\s*([\w][\w\s-]{0,30}?)\s*$",
)
_RE_TRAILING_PERIOD = re.compile(
    r"\s{3,}((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|\d{4}).+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExperienceLocation:
    """One work-experience location anchored by its date range."""

    period: str
    location: str


_EDU_CITY = "[EDU_CITY]"


@dataclass(frozen=True)
class EducationLocation:
    """One education location anchored by degree period and/or institution."""

    period: str
    location: str
    institution: str = ""

    @property
    def city(self) -> str:
        return _location_city(self.location)


def work_loc_token(index: int) -> str:
    return f"[WORK_LOC_{index}]"


def edu_loc_token(index: int) -> str:
    return f"[EDU_LOC_{index}]"


def normalize_period_key(period: str) -> str:
    s = period.strip().lower().replace("–", "-").replace("—", "-")
    s = re.sub(r"\s*-\s*", " - ", s)
    return re.sub(r"\s+", " ", s)


def period_fingerprint(period: str) -> str:
    """Stable key for matching source CV dates to LLM-normalized periods."""
    text = period.strip().lower().replace("–", "-").replace("—", "-")
    years = re.findall(r"\d{4}", text)
    if not years:
        return normalize_period_key(period)
    start = years[0]
    end = "present" if "present" in text else years[-1]
    return f"{start}-{end}"


def institution_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _is_section_header(line: str, headers: frozenset[str]) -> bool:
    return line.strip().upper().rstrip(":") in headers


def _location_label(city: str, country: str) -> str:
    return f"{city.strip()}, {country.strip()}"


_NON_GEO_COUNTRY_WORDS = frozenset({
    "optimized", "optimization", "deployment", "deployments", "easy",
    "strong", "focus", "using", "incl", "including", "based", "management",
    "for", "and", "with", "the", "to", "api", "apis", "processing",
})


def _looks_like_geo_location(city: str, country: str) -> bool:
    """Reject comma-separated prose that is not a City, Country pair."""
    city = city.strip()
    country = country.strip()
    if not city or not country:
        return False
    country_words = [w.lower() for w in country.split()]
    if len(country_words) > 4:
        return False
    if any(w in _NON_GEO_COUNTRY_WORDS for w in country_words):
        return False
    return True


def _replace_locations_in_line(line: str, token_map: dict[str, str]) -> str:
    for location, token in sorted(
        ((loc, tok) for tok, loc in token_map.items()),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if location in line:
            return line.replace(location, token)
    return line


def _is_certifications_subsection(line: str) -> bool:
    return line.strip().lower().startswith("certification")


def parse_experience_locations(text: str) -> list[ExperienceLocation]:
    """Extract experience locations from CV body text (frontmatter already stripped)."""
    entries: list[ExperienceLocation] = []
    in_experience = False
    pending_period: str | None = None

    for line in text.splitlines():
        if _is_section_header(line, _EXPERIENCE_SECTION_HEADERS):
            in_experience = True
            pending_period = None
            continue
        if in_experience and _is_section_header(line, _EXPERIENCE_SECTION_END_HEADERS):
            break
        if not in_experience or looks_like_contact_line(line):
            continue

        if m := _RE_LOCATION_BEFORE_DATE.match(line):
            if _looks_like_geo_location(m.group(2), m.group(3)):
                location = _location_label(m.group(2), m.group(3))
                period = m.group(5).strip()
                entries.append(ExperienceLocation(period=period, location=location))
            pending_period = None
            continue

        if m := _RE_STANDALONE_LOCATION.match(line):
            if (
                len(line.strip()) <= 60
                and _looks_like_geo_location(m.group(2), m.group(3))
            ):
                location = _location_label(m.group(2), m.group(3))
                entries.append(
                    ExperienceLocation(period=pending_period or "", location=location)
                )
                pending_period = None
            continue

        if m := _RE_TRAILING_PERIOD.search(line):
            pending_period = m.group(1).strip()

    return entries


def parse_education_locations(text: str) -> list[EducationLocation]:
    """Extract education locations from CV body text (frontmatter already stripped)."""
    entries: list[EducationLocation] = []
    in_education = False
    pending_period: str | None = None

    for line in text.splitlines():
        if _is_section_header(line, _EDUCATION_SECTION_HEADERS):
            in_education = True
            pending_period = None
            continue
        if in_education and _is_section_header(line, _EDUCATION_SECTION_END_HEADERS):
            break
        if not in_education or looks_like_contact_line(line) or _is_certifications_subsection(line):
            if in_education and _is_certifications_subsection(line):
                pending_period = None
            continue

        if m := _RE_TRAILING_LOCATION.match(line):
            if _looks_like_geo_location(m.group(2), m.group(3)):
                location = _location_label(m.group(2), m.group(3))
                entries.append(
                    EducationLocation(
                        period=pending_period or "",
                        location=location,
                        institution=m.group(1).strip(),
                    )
                )
            pending_period = None
            continue

        if m := _RE_STANDALONE_LOCATION.match(line):
            if (
                len(line.strip()) <= 60
                and _looks_like_geo_location(m.group(2), m.group(3))
            ):
                location = _location_label(m.group(2), m.group(3))
                entries.append(
                    EducationLocation(period=pending_period or "", location=location)
                )
                pending_period = None
            continue

        if m := _RE_TRAILING_PERIOD.search(line):
            pending_period = m.group(1).strip()

    return entries


def build_experience_location_index(text: str) -> dict[str, str]:
    """Map period fingerprints to original experience location strings."""
    index: dict[str, str] = {}
    for entry in parse_experience_locations(text):
        index[normalize_period_key(entry.period)] = entry.location
        index[period_fingerprint(entry.period)] = entry.location
    return index


def _location_city(location: str) -> str:
    return location.split(",", 1)[0].strip()


def _redact_city_in_text(text: str, city: str, *, placeholder: str = _EDU_CITY) -> str:
    if not city:
        return text
    return re.sub(rf"\b{re.escape(city)}\b", placeholder, text, flags=re.IGNORECASE)


def build_education_entry_index(text: str) -> dict[str, EducationLocation]:
    """Map period fingerprints to full education entries."""
    index: dict[str, EducationLocation] = {}
    for entry in parse_education_locations(text):
        if not entry.period:
            continue
        index[normalize_period_key(entry.period)] = entry
        index[period_fingerprint(entry.period)] = entry
    return index


def build_education_location_index(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Map period and institution keys to original education location strings."""
    by_period: dict[str, str] = {}
    by_institution: dict[str, str] = {}
    for entry in parse_education_locations(text):
        if entry.period:
            by_period[normalize_period_key(entry.period)] = entry.location
            by_period[period_fingerprint(entry.period)] = entry.location
        if entry.institution:
            by_institution[institution_key(entry.institution)] = entry.location
    return by_period, by_institution


def build_work_loc_token_map(text: str) -> dict[str, str]:
    """Map [WORK_LOC_N] tokens to original experience location strings."""
    return _build_token_map(parse_experience_locations(text), work_loc_token)


def build_edu_loc_token_map(text: str) -> dict[str, str]:
    """Map [EDU_LOC_N] tokens to original education location strings."""
    return _build_token_map(parse_education_locations(text), edu_loc_token)


def _build_token_map(entries: list[Any], token_fn: Any) -> dict[str, str]:
    token_map: dict[str, str] = {}
    token_by_location: dict[str, str] = {}
    next_index = 1

    for entry in entries:
        if entry.location not in token_by_location:
            token = token_fn(next_index)
            next_index += 1
            token_by_location[entry.location] = token
            token_map[token] = entry.location

    return token_map


def redact_experience_locations(text: str) -> str:
    """Replace experience locations with [WORK_LOC_N] placeholders for LLM prompts."""
    return _redact_section_locations(
        text,
        build_work_loc_token_map(text),
        _EXPERIENCE_SECTION_HEADERS,
        _EXPERIENCE_SECTION_END_HEADERS,
    )


def redact_education_locations(text: str) -> str:
    """Replace education locations and institution city names with privacy placeholders."""
    entries = parse_education_locations(text)
    token_map = build_edu_loc_token_map(text)
    if not entries and not token_map:
        return text

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
            line = _replace_locations_in_line(line, token_map)
            for entry in entries:
                if entry.institution and entry.institution in line and entry.city:
                    line = _redact_city_in_text(line, entry.city)
                    break

        lines.append(line)

    return "\n".join(lines)


def redact_location_placeholders(text: str) -> str:
    """Replace work and education locations with privacy placeholders."""
    return redact_education_locations(redact_experience_locations(text))


def _redact_section_locations(
    text: str,
    token_map: dict[str, str],
    start_headers: frozenset[str],
    end_headers: frozenset[str],
    *,
    stop_at_certifications: bool = False,
) -> str:
    if not token_map:
        return text

    lines: list[str] = []
    in_section = False

    for line in text.splitlines():
        if _is_section_header(line, start_headers):
            in_section = True
            lines.append(line)
            continue
        if in_section and _is_section_header(line, end_headers):
            in_section = False
        if in_section and stop_at_certifications and _is_certifications_subsection(line):
            in_section = False

        if in_section and not looks_like_contact_line(line):
            line = _replace_locations_in_line(line, token_map)
        lines.append(line)

    return "\n".join(lines)


_RESTORE_EXPORTS = frozenset({
    "override_cv_locations",
    "override_education_locations",
    "override_experience_locations",
})


def __getattr__(name: str) -> Any:
    if name in _RESTORE_EXPORTS:
        from jobfit.cv import restore

        return getattr(restore, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
