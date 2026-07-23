"""Redact PII from job description excerpts for prep context export."""

from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)

# Trailing legal-entity suffixes only (not marketing words like "Digital" / "Group").
_LEGAL_TRAILING_RE = re.compile(
    r"(?i)[\s,.\-]*"
    r"(?:"
    r"gmbh\s*&\s*co\.?\s*k?g|"
    r"g\.?m\.?b\.?h\.?|"
    r"ug(?:\s*\([^)]*\))?|"
    r"a\.?g\.?|"
    r"se|"
    r"inc\.?|"
    r"ltd\.?|"
    r"llc\.?|"
    r"plc\.?|"
    r"b\.?v\.?|"
    r"s\.?a\.?r?\.?l?\.?|"
    r"kg|"
    r"ohg|"
    r"e\.?\s*v\.?"
    r")"
    r"\.?\s*$"
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
# firma "Contosoai" + JD word "Contoso" → remainder "ai" (short product/brand glue).
_SHORT_FIRM_REST_RE = re.compile(r"^[a-z0-9]{1,3}$", re.IGNORECASE)

_MIN_CORE_LEN = 3
_MIN_TEXT_PREFIX_LEN = 4


def firma_variants(*firmas: str) -> list[str]:
    """Return unique company-name variants from legal-suffix stripping, longest first.

    Example: ``Acme GmbH`` → ``Acme GmbH``, ``Acme``.
    """
    seen: set[str] = set()
    variants: list[str] = []

    def _add(name: str, *, allow_short: bool) -> None:
        cleaned = name.strip().strip(" ,.-")
        if not cleaned:
            return
        if not allow_short and len(cleaned) < _MIN_CORE_LEN:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        seen.add(key)
        variants.append(cleaned)

    for raw in firmas:
        if not raw or not str(raw).strip():
            continue
        current = str(raw).strip()
        _add(current, allow_short=True)
        while True:
            stripped = _LEGAL_TRAILING_RE.sub("", current).strip().strip(" ,.-")
            if not stripped or stripped.casefold() == current.casefold():
                break
            _add(stripped, allow_short=False)
            current = stripped

    variants.sort(key=len, reverse=True)
    return variants


def text_prefix_stems(firma: str, text: str) -> list[str]:
    """JD brand tokens that are a proper prefix of *firma* with a short remainder.

    Covers DB ``Contosoai`` vs JD ``Contoso`` (remainder ``ai``). Does **not**
    strip long leftovers (``DeutscheBahn`` / ``Deutsche`` → remainder ``Bahn``).
    """
    core = firma.strip()
    if not core or " " in core or "-" in core:
        return []
    core_cf = core.casefold()
    found: list[str] = []
    seen: set[str] = set()
    for match in _WORD_RE.finditer(text):
        word = match.group(0)
        word_cf = word.casefold()
        if len(word_cf) < _MIN_TEXT_PREFIX_LEN or word_cf == core_cf:
            continue
        if not core_cf.startswith(word_cf):
            continue
        rest = core_cf[len(word_cf) :]
        if not _SHORT_FIRM_REST_RE.match(rest):
            continue
        if word_cf in seen:
            continue
        seen.add(word_cf)
        found.append(word)
    found.sort(key=len, reverse=True)
    return found


def _redact_names(excerpt: str, names: list[str]) -> str:
    for name in names:
        excerpt = re.sub(
            rf"(?<!\w){re.escape(name)}(?!\w)",
            "[COMPANY]",
            excerpt,
            flags=re.IGNORECASE,
        )
    return excerpt


def _all_redact_names(firmas: tuple[str, ...], text: str) -> list[str]:
    names = list(firma_variants(*firmas))
    seen = {n.casefold() for n in names}
    for firma in firmas:
        if not firma or not str(firma).strip():
            continue
        for stem in text_prefix_stems(str(firma).strip(), text):
            key = stem.casefold()
            if key not in seen:
                seen.add(key)
                names.append(stem)
        # Also stem against legal-stripped cores
        for core in firma_variants(str(firma)):
            if " " in core:
                continue
            for stem in text_prefix_stems(core, text):
                key = stem.casefold()
                if key not in seen:
                    seen.add(key)
                    names.append(stem)
    names.sort(key=len, reverse=True)
    return names


def redact_excerpt(
    text: str,
    firma: str,
    max_chars: int,
    *extra_firmas: str,
) -> str:
    """Return a truncated, anonymized JD excerpt.

    Replaces company-name variants → [COMPANY], http(s) URLs → [URL], emails → [EMAIL].

    Name variants come from:
    - raw ``firma`` / ``extra_firmas`` (e.g. classification vs job row);
    - legal-suffix stripping (``Acme GmbH`` also redacts ``Acme``);
    - short brand prefixes found in the JD when DB name is glued
      (``Contosoai`` in DB, ``Contoso`` in text).

    Returns empty string when max_chars == 0.
    """
    if max_chars == 0:
        return ""
    excerpt = text[:max_chars] if max_chars > 0 else text
    # URLs/emails first — brand-core redaction must not break local-parts like hr@acme.de
    excerpt = _URL_RE.sub("[URL]", excerpt)
    excerpt = _EMAIL_RE.sub("[EMAIL]", excerpt)
    names = _all_redact_names((firma, *extra_firmas), excerpt)
    excerpt = _redact_names(excerpt, names)
    # Normalize whitespace for single-line embedding
    excerpt = " ".join(excerpt.split())
    return excerpt
