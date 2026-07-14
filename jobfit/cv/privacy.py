"""Strip PII from CV text before sending to external LLM providers."""

from __future__ import annotations

import os
import re
from typing import Any

from loguru import logger

from jobfit.cv.io import parse_frontmatter
from jobfit.cv.contacts import (
    RE_EMAIL,
    RE_GITHUB,
    RE_LINKEDIN,
    RE_PHONE,
    RE_XING,
    extract_residence_from_text,
    looks_like_contact_line,
    redact_residence,
)
from jobfit.cv.companies import redact_experience_companies
from jobfit.cv.institutions import redact_education_institutions
from jobfit.cv.locations import (
    redact_education_locations,
    redact_experience_locations,
)
from jobfit.cv.text import _SECTION_HEADERS, looks_like_name, strip_frontmatter

_EMAIL = "[EMAIL]"
_PHONE = "[PHONE]"
_GITHUB = "[GITHUB]"
_LINKEDIN = "[LINKEDIN]"
_XING = "[XING]"
_POSTAL = "[POSTAL_CODE]"
_CITY = "[CITY]"
_COUNTRY = "[COUNTRY]"
_NAME = "[CANDIDATE_NAME]"


def anonymize_enabled() -> bool:
    """Return True unless CV_ANONYMIZE_LLM is explicitly disabled."""
    return os.environ.get("CV_ANONYMIZE_LLM", "1").lower() not in ("0", "false", "no", "off")


def extract_location_city(cv_text: str) -> str | None:
    """Return current city from frontmatter or contact header line."""
    fm = parse_frontmatter(cv_text)
    city = fm.get("contact_city") or fm.get("location_city")
    if isinstance(city, str) and city.strip():
        return city.strip()
    return extract_residence_from_text(cv_text).get("city")


def extract_candidate_name(cv_text: str) -> str | None:
    """Return candidate name from frontmatter or CV header (first non-contact line)."""
    fm = parse_frontmatter(cv_text)
    if isinstance(fm.get("contact_name"), str) and (name := fm["contact_name"].strip()):
        return name

    body = strip_frontmatter(cv_text)
    first_candidate: str | None = None
    for ln in body.splitlines():
        line = ln.strip().lstrip("﻿")  # strip BOM if present
        if not line:
            continue
        if looks_like_contact_line(line):
            continue
        upper = line.upper().rstrip(":")
        if upper in _SECTION_HEADERS:
            continue
        if looks_like_name(line):
            return line
        if first_candidate is None:
            first_candidate = line
    return first_candidate


def _body_name_for_redaction(body: str) -> str | None:
    """Return first NAME SURNAME line from already-stripped CV body.

    Stops at the first non-contact non-header candidate: if it passes the
    NAME SURNAME pattern (≥2 words, looks_like_name), return it; otherwise
    give up — further lines are even less likely to be a name.
    """
    for ln in body.splitlines():
        line = ln.strip().lstrip("﻿")
        if not line:
            continue
        if looks_like_contact_line(line):
            continue
        if line.upper().rstrip(":") in _SECTION_HEADERS:
            continue
        if len(line.split()) >= 2 and looks_like_name(line):
            return line
        return None
    return None


def profile_for_llm(profile: dict[str, Any]) -> dict[str, Any]:
    """Return profile fields safe to include in an LLM prompt."""
    exclude = {"skills"}
    if anonymize_enabled():
        exclude.update({"location_city", "contact_name"})
    return {k: v for k, v in profile.items() if k not in exclude}


def anonymize_for_llm(cv_text: str) -> str:
    """Return CV text with contact details and identity markers replaced by placeholders."""
    if not anonymize_enabled():
        return cv_text

    city = extract_location_city(cv_text)
    name = extract_candidate_name(cv_text)
    residence = extract_residence_from_text(cv_text)
    if city and not residence.get("city"):
        residence = {**residence, "city": city}
    text = strip_frontmatter(cv_text)

    body_name = _body_name_for_redaction(text)
    names_to_redact = {n for n in (name, body_name) if n}
    if names_to_redact:
        for n in sorted(names_to_redact, key=len, reverse=True):
            text = re.sub(re.escape(n), _NAME, text, flags=re.IGNORECASE)
    else:
        logger.warning("Could not extract candidate name from CV — name may leak to LLM")

    text = RE_EMAIL.sub(_EMAIL, text)
    text = RE_PHONE.sub(_PHONE, text)
    text = RE_GITHUB.sub(_GITHUB, text)
    text = RE_LINKEDIN.sub(_LINKEDIN, text)
    text = RE_XING.sub(_XING, text)
    text = redact_residence(
        text,
        residence,
        city=_CITY,
        postal_code=_POSTAL,
        country=_COUNTRY,
    )
    text = redact_experience_locations(text)
    text = redact_experience_companies(text)
    text = redact_education_institutions(text)
    text = redact_education_locations(text)

    return text
