"""Shared regex patterns and extraction helpers for CV contact fields."""

from __future__ import annotations

import re

RE_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
RE_PHONE = re.compile(r"\+\d[\d\s()./-]{8,}")
RE_GITHUB = re.compile(r"github\.com/[\w-]+(?:/[\w-]+)*", re.IGNORECASE)
RE_POSTAL = re.compile(r"\b\d{5}\b")

# Optional scheme/subdomain; slug is ASCII word chars and hyphens (LinkedIn custom URLs).
RE_LINKEDIN = re.compile(
    r"(?:https?://)?(?:[\w-]+\.)*linkedin\.com/in/[\w-]+",
    re.IGNORECASE,
)

# Optional scheme/www; XING profile slugs commonly use underscores.
RE_XING = re.compile(
    r"(?:https?://)?(?:www\.)?xing\.com/profile/[\w]+",
    re.IGNORECASE,
)

CONTACT_KEYS = ("city", "email", "phone", "linkedin", "xing", "github")
RESIDENCE_KEYS = ("city", "postal_code", "country")

_CONTACT_EXTRACTORS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", RE_EMAIL),
    ("github", RE_GITHUB),
    ("linkedin", RE_LINKEDIN),
    ("xing", RE_XING),
    ("phone", RE_PHONE),
)


def contact_header_line(text: str) -> str | None:
    """Return the CV contact header line (city/email row), if present."""
    for line in text.splitlines():
        if "@" in line and "|" in line:
            return line
    return None


def extract_residence_from_text(text: str) -> dict[str, str | None]:
    """Parse place of residence from the contact header: City, PLZ, Country."""
    result: dict[str, str | None] = {k: None for k in RESIDENCE_KEYS}
    line = contact_header_line(text)
    if not line:
        return result

    header = line.split("|")[0].strip()
    parts = [part.strip() for part in header.split(",") if part.strip()]
    if not parts:
        return result

    result["city"] = parts[0]
    for part in parts[1:]:
        if m := RE_POSTAL.search(part):
            result["postal_code"] = m.group()
        elif result["country"] is None:
            result["country"] = part
    return result


def extract_contacts_from_text(text: str) -> dict[str, str | None]:
    """Regex fallback: extract contact fields from CV body text."""
    result: dict[str, str | None] = {k: None for k in CONTACT_KEYS}
    residence = extract_residence_from_text(text)
    result["city"] = residence["city"]

    for key, pattern in _CONTACT_EXTRACTORS:
        if m := pattern.search(text):
            result[key] = m.group().strip() if key == "phone" else m.group()

    return result


def looks_like_contact_line(line: str) -> bool:
    """Return True if line looks like a CV header contact row."""
    lower = line.lower()
    if "@" in line or "|" in line or "http://" in lower or "https://" in lower:
        return True
    return any(pattern.search(line) for _, pattern in _CONTACT_EXTRACTORS)


def redact_residence(
    text: str,
    residence: dict[str, str | None],
    *,
    city: str = "[CITY]",
    postal_code: str = "[POSTAL_CODE]",
    country: str = "[COUNTRY]",
) -> str:
    """Replace residence parts in text. City and country are redacted on contact lines only."""
    if residence.get("postal_code"):
        text = RE_POSTAL.sub(postal_code, text)

    lines = text.splitlines()
    city_value = residence.get("city")
    country_value = residence.get("country")
    if city_value or country_value:
        redacted: list[str] = []
        for line in lines:
            if looks_like_contact_line(line):
                if city_value:
                    line = re.sub(re.escape(city_value), city, line, flags=re.IGNORECASE)
                if country_value:
                    line = re.sub(re.escape(country_value), country, line, flags=re.IGNORECASE)
            redacted.append(line)
        text = "\n".join(redacted)

    return text
