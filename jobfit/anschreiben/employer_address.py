"""Resolve employer address lines for Anschreiben recipient block."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jobfit.config import RAW_DIR
from jobfit.fetchers._cache import CACHE_DIR

_BA_DETAILS_DIR = RAW_DIR / "bundesagentur_details"
_BA_SEARCH_FILE = RAW_DIR / "bundesagentur.json"

_STREET_JOIN_RE = re.compile(r"\s+")
_PLZ_CITY_RE = re.compile(
    r"\b(\d{5})\s+([A-ZÄÖÜa-zäöüß][\wäöüÄÖÜß\-. ]+)",
)
_STREET_HINT_RE = re.compile(r"\b(?:straße|strasse|str\.)\b", re.IGNORECASE)
_COUNTRY_TOKENS = frozenset({"germany", "deutschland", "de", "deu"})


def _clean_part(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "null" else text


def _empty_address() -> dict[str, str]:
    return {"street": "", "city_line": ""}


def _city_line(plz: str, ort: str) -> str:
    plz = _clean_part(plz)
    ort = _clean_part(ort)
    if plz and ort:
        return f"{plz} {ort}"
    return plz or ort


def _street_line(strasse: str, hausnummer: str = "") -> str:
    parts = [_clean_part(strasse), _clean_part(hausnummer)]
    return _STREET_JOIN_RE.sub(" ", " ".join(p for p in parts if p)).strip()


def _from_adresse_dict(adresse: dict[str, Any]) -> dict[str, str]:
    street = _street_line(adresse.get("strasse", ""), adresse.get("hausnummer", ""))
    city_line = _city_line(adresse.get("plz", ""), adresse.get("ort", ""))
    return {"street": street, "city_line": city_line}


def _from_ba_detail(data: dict[str, Any]) -> dict[str, str]:
    locations = data.get("stellenlokationen") or []
    if not locations:
        return _empty_address()
    first = locations[0] if isinstance(locations[0], dict) else {}
    adresse = first.get("adresse")
    if not isinstance(adresse, dict):
        return _empty_address()
    return _from_adresse_dict(adresse)


def _from_ba_search_entry(entry: dict[str, Any]) -> dict[str, str]:
    arbeitsort = entry.get("arbeitsort")
    if not isinstance(arbeitsort, dict):
        return _empty_address()
    street = _clean_part(arbeitsort.get("strasse"))
    return {
        "street": street,
        "city_line": _city_line(arbeitsort.get("plz", ""), arbeitsort.get("ort", "")),
    }


def _load_ba_detail(refnr: str) -> dict[str, Any] | None:
    path = _BA_DETAILS_DIR / f"{refnr}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_ba_search_entry(refnr: str) -> dict[str, Any] | None:
    if not _BA_SEARCH_FILE.exists():
        return None
    try:
        data = json.loads(_BA_SEARCH_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for entry in data.get("stellenangebote", []):
        if isinstance(entry, dict) and entry.get("refnr") == refnr:
            return entry
    return None


def _resolve_bundesagentur(refnr: str) -> dict[str, str]:
    for loader, parser in (
        (_load_ba_detail, _from_ba_detail),
        (_load_ba_search_entry, _from_ba_search_entry),
    ):
        raw = loader(refnr)
        if not raw:
            continue
        parsed = parser(raw)
        if parsed["street"] or parsed["city_line"]:
            return parsed
    return _empty_address()


def _parse_jobhive_refnr(refnr: str) -> tuple[str, str] | None:
    """Parse ats-{source}-{id} refnrs from jobhive (not softgarden/everjobs)."""
    if not refnr.startswith("ats-"):
        return None
    if refnr.startswith("ats-softgarden-"):
        return None
    parts = refnr.split("-", 2)
    if len(parts) != 3:
        return None
    return parts[1], parts[2]


def _jobhive_row_location(ats: str, ats_id: str) -> str:
    cache_path = CACHE_DIR / f"{ats}.parquet"
    if not cache_path.exists():
        return ""
    try:
        import pandas as pd
    except ImportError:
        return ""

    try:
        df = pd.read_parquet(cache_path, columns=["ats_id", "location"])
    except Exception:
        return ""

    lookup_id: int | str
    try:
        lookup_id = int(ats_id)
    except ValueError:
        lookup_id = ats_id

    matches = df.loc[df["ats_id"] == lookup_id, "location"]
    if matches.empty:
        return ""
    return _clean_part(matches.iloc[0])


def _from_location_string(location: str) -> dict[str, str]:
    """Best-effort parse for ATS/feed location strings stored in jobs.ort_raw."""
    location = _clean_part(location)
    if not location:
        return _empty_address()

    if _STREET_HINT_RE.search(location):
        return {"street": location, "city_line": ""}

    if match := _PLZ_CITY_RE.search(location):
        return {
            "street": "",
            "city_line": f"{match.group(1)} {match.group(2).strip()}",
        }

    parts = [part.strip() for part in location.split(",") if part.strip()]
    if parts:
        filtered = [
            part for part in parts
            if part.lower() not in _COUNTRY_TOKENS
        ]
        city_line = filtered[0] if filtered else parts[0]
        return {"street": "", "city_line": city_line}

    return {"street": "", "city_line": location}


def resolve_employer_address(
    refnr: str,
    *,
    ats_source: str = "",
    via: str = "",
    ort_fallback: str = "",
) -> dict[str, str]:
    """Return recipient address lines for the employer block.

    Resolution order depends on job source:
    - Bundesagentur refnrs: structured address from raw detail/search JSON
    - jobhive ATS (ats-{source}-{id}): location from cached parquet, then DB ort
    - softgarden / everjobs / other feeds: parsed jobs.ort_raw / classification.ort

    Full street addresses are only available for Bundesagentur (and rarely when
    ort_raw already contains a street string). Most ATS listings provide city/region only.
    """
    parsed = _empty_address()

    if refnr.startswith("ats-"):
        if jobhive_ids := _parse_jobhive_refnr(refnr):
            ats, ats_id = jobhive_ids
            location = _jobhive_row_location(ats, ats_id) or ort_fallback
            parsed = _from_location_string(location)
    elif refnr.startswith("everjobs-"):
        parsed = _from_location_string(ort_fallback)
    else:
        parsed = _resolve_bundesagentur(refnr)

    if parsed["street"] or parsed["city_line"]:
        return parsed

    if ort_fallback:
        return _from_location_string(ort_fallback)

    _ = ats_source, via  # reserved for future per-source raw caches
    return _empty_address()


def enrich_letter_employer_address(
    letter_data: dict[str, Any],
    job_ctx: dict[str, Any],
) -> None:
    """Attach employer address fields used by the print template."""
    address = resolve_employer_address(
        job_ctx["refnr"],
        ats_source=job_ctx.get("ats_source", ""),
        via=job_ctx.get("via", ""),
        ort_fallback=job_ctx.get("ort", ""),
    )
    letter_data["employer_street"] = address["street"]
    letter_data["employer_city_line"] = address["city_line"]
