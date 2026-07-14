"""Restore PII and locations in LLM-generated CV JSON from local CV source."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jobfit.cv.io import load_cv_contact
from jobfit.cv.companies import (
    build_experience_company_index,
    build_work_comp_token_map,
)
from jobfit.cv.institutions import (
    build_edu_inst_token_map,
    build_education_institution_index,
)
from jobfit.cv.locations import (
    build_edu_loc_token_map,
    build_education_entry_index,
    build_experience_location_index,
    build_work_loc_token_map,
    institution_key,
    normalize_period_key,
    parse_education_locations,
    period_fingerprint,
)
from jobfit.cv.bullets import restore_experience_project_labels
from jobfit.cv.privacy import extract_candidate_name
from jobfit.cv.text import strip_frontmatter


def _lookup_location(period: str | None, index: dict[str, str]) -> str | None:
    if not period:
        return None
    for key in (normalize_period_key(period), period_fingerprint(period)):
        if key in index:
            return index[key]
    return None


def _lookup_education_entry(
    period: str | None,
    index: dict[str, Any],
) -> Any | None:
    if not period:
        return None
    for key in (normalize_period_key(period), period_fingerprint(period)):
        if key in index:
            return index[key]
    return None


def override_experience_locations(cv_data: dict[str, Any], cv_text: str) -> None:
    """Restore experience locations from CV source text, ignoring LLM output."""
    body = strip_frontmatter(cv_text)
    index = build_experience_location_index(body)
    token_map = build_work_loc_token_map(body)

    for entry in cv_data.get("experience", []):
        if not isinstance(entry, dict):
            continue

        period = entry.get("period")
        if isinstance(period, str):
            if restored := _lookup_location(period, index):
                entry["location"] = restored
                continue

        location = entry.get("location")
        if isinstance(location, str) and location in token_map:
            entry["location"] = token_map[location]


def override_education_locations(cv_data: dict[str, Any], cv_text: str) -> None:
    """Restore education institutions and locations from CV source text."""
    body = strip_frontmatter(cv_text)
    entry_index = build_education_entry_index(body)
    token_map = build_edu_loc_token_map(body)
    inst_index = build_education_institution_index(body)
    inst_token_map = build_edu_inst_token_map(body)
    sources = parse_education_locations(body)

    for entry in cv_data.get("education", []):
        if not isinstance(entry, dict):
            continue

        period = entry.get("period")
        if isinstance(period, str) and (src := _lookup_education_entry(period, entry_index)):
            entry["location"] = src.location
            if src.institution:
                entry["institution"] = src.institution
            continue

        if isinstance(period, str):
            for key in (normalize_period_key(period), period_fingerprint(period)):
                if key in inst_index:
                    entry["institution"] = inst_index[key]
                    break

        institution = entry.get("institution")
        if isinstance(institution, str):
            if institution in inst_token_map:
                entry["institution"] = inst_token_map[institution]
            else:
                for src in sources:
                    if src.institution and institution_key(src.institution) == institution_key(institution):
                        entry["institution"] = src.institution
                        if src.location:
                            entry["location"] = src.location
                        break

        location = entry.get("location")
        if isinstance(location, str) and location in token_map:
            entry["location"] = token_map[location]


def override_experience_companies(cv_data: dict[str, Any], cv_text: str) -> None:
    """Restore employer names from CV source text, ignoring LLM output."""
    body = strip_frontmatter(cv_text)
    index = build_experience_company_index(body)
    token_map = build_work_comp_token_map(body)

    for entry in cv_data.get("experience", []):
        if not isinstance(entry, dict):
            continue

        period = entry.get("period")
        if isinstance(period, str):
            for key in (normalize_period_key(period), period_fingerprint(period)):
                if key in index:
                    entry["company"] = index[key]
                    break
            else:
                company = entry.get("company")
                if isinstance(company, str) and company in token_map:
                    entry["company"] = token_map[company]


def override_cv_locations(cv_data: dict[str, Any], cv_text: str) -> None:
    """Restore all work and education locations from CV source text."""
    override_experience_locations(cv_data, cv_text)
    override_education_locations(cv_data, cv_text)


def override_contact(
    cv_data: dict[str, Any],
    role_slug: str,
    *,
    load_cv_contact_fn: Callable[[str], dict[str, Any]] | None = None,
) -> None:
    """Replace LLM-generated contact block with data from the role CV source file."""
    contact_fn = load_cv_contact_fn or load_cv_contact
    contact = contact_fn(role_slug)
    if any(v is not None for v in contact.values()):
        cv_data["contact"] = contact


def override_identity(
    cv_data: dict[str, Any],
    cv_text: str,
    role_slug: str,
    *,
    load_cv_contact_fn: Callable[[str], dict[str, Any]] | None = None,
) -> None:
    """Restore candidate name, contacts, and locations from local CV source."""
    if name := extract_candidate_name(cv_text):
        cv_data["name"] = name
    override_contact(cv_data, role_slug, load_cv_contact_fn=load_cv_contact_fn)
    override_cv_locations(cv_data, cv_text)
    override_experience_companies(cv_data, cv_text)
    restore_experience_project_labels(cv_data, cv_text)
