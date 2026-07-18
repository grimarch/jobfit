"""CV file paths, reading, and structured profile/contact loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jobfit.cv.contacts import CONTACT_KEYS, extract_contacts_from_text
from jobfit.config import role_input_dir, role_output_dir
from jobfit.roles import DEFAULT_ROLE

_CV_EXTENSIONS = (".md", ".txt", ".pdf")
_CONTACT_KEYS = CONTACT_KEYS


def cv_text_path(role_slug: str = DEFAULT_ROLE) -> Path:
    """Path to extracted CV plain text: data/{role}/output/cv.txt"""
    return role_output_dir(role_slug) / "cv.txt"


def cv_profile_path(role_slug: str = DEFAULT_ROLE) -> Path:
    """Path to structured CV profile JSON: data/{role}/output/cv_profile.json"""
    return role_output_dir(role_slug) / "cv_profile.json"


def cv_file(role_slug: str = DEFAULT_ROLE) -> Path:
    """Return CV source from data/{role}/input/CV_{role}.{ext} or CV.{ext}."""
    input_dir = role_input_dir(role_slug)
    for ext in _CV_EXTENSIONS:
        path = input_dir / f"CV_{role_slug}{ext}"
        if path.exists():
            return path
    for ext in _CV_EXTENSIONS:
        path = input_dir / f"CV{ext}"
        if path.exists():
            return path
    raise FileNotFoundError(
        f"No CV found: expected {input_dir}/CV_{role_slug}.md/.txt/.pdf "
        f"or {input_dir}/CV.md/.txt/.pdf"
    )


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse simple YAML frontmatter (between leading --- delimiters)."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    result: dict[str, Any] = {}
    for line in text[3:end].splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            result[key] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        elif value.isdigit():
            result[key] = int(value)
        else:
            result[key] = value
    return result


def cv_read(role_slug: str = DEFAULT_ROLE) -> str:
    """Return plain text of the CV, extracting PDF if needed."""
    from jobfit.cv.extract import extract_text

    return extract_text(cv_file(role_slug))


def load_cv_profile(role_slug: str = DEFAULT_ROLE) -> dict[str, Any]:
    """Load structured CV profile. Reads JSON first, falls back to YAML frontmatter."""
    json_path = cv_profile_path(role_slug)
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))
    try:
        path = cv_file(role_slug)
    except FileNotFoundError:
        return {}
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def load_cv_contact(role_slug: str = DEFAULT_ROLE) -> dict[str, str | None]:
    """Load contact fields from the role CV source file.

    Primary: frontmatter contact_* keys.
    Fallback per field: regex extraction from CV body text.
    """
    try:
        cv_text = cv_file(role_slug).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {k: None for k in _CONTACT_KEYS}

    fm = parse_frontmatter(cv_text)

    def _fm_val(key: str) -> str | None:
        v = fm.get(f"contact_{key}", "")
        return v if v else None

    fm_contact = {k: _fm_val(k) for k in _CONTACT_KEYS}

    if all(v is None for v in fm_contact.values()):
        return extract_contacts_from_text(cv_text)

    if any(v is None for v in fm_contact.values()):
        regex_contact = extract_contacts_from_text(cv_text)
        return {
            k: fm_contact[k] if fm_contact[k] is not None else regex_contact[k]
            for k in _CONTACT_KEYS
        }

    return fm_contact
