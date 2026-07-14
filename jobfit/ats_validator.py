"""ATS compatibility scoring for generated CVs.

Entry point: validate(pdf_path, cv_data, job_description, role_skills) -> ATSReport
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

_SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "experience": re.compile(
        r"\b(berufserfahrung|work\s+experience|experience|professional\s+experience|erfahrung)\b",
        re.IGNORECASE,
    ),
    "education": re.compile(
        r"\b(ausbildung|bildung|studium|education|academic)\b",
        re.IGNORECASE,
    ),
    "skills": re.compile(
        r"\b(kenntnisse|f[äa]higkeiten|skills|kompetenzen|technical\s+skills)\b",
        re.IGNORECASE,
    ),
    "languages": re.compile(
        r"\b(sprachen|sprachkenntnisse|languages)\b",
        re.IGNORECASE,
    ),
    "certifications": re.compile(
        r"\b(zertifizierungen|zertifikate|certifications|certificates)\b",
        re.IGNORECASE,
    ),
    "summary": re.compile(
        r"\b(profil|zusammenfassung|summary|profile|[üu]ber\s+mich)\b",
        re.IGNORECASE,
    ),
}

_DATE_OK = re.compile(r"\b\d{2}\.\d{4}\b")
_DATE_BAD = [
    re.compile(r"\b(seit|since)\s+\d{4}\b", re.IGNORECASE),
    re.compile(r"\b\d{4}\s*[–-]\s*\d{4}\b"),  # YYYY–YYYY without months
]

_CURRENT_MARKERS = frozenset(("heute", "present", "current", "dato", "now", "laufend"))


@dataclass
class PlatformOutlook:
    name: str
    status: str  # "pass" | "warn" | "fail"
    note: str


@dataclass
class ATSReport:
    keyword_score: int
    section_score: int
    parsability_score: int
    date_score: int
    contact_score: int
    overall_score: int      # ATS technical parse score
    completeness_score: int  # CV data completeness score
    matched_keywords: list[str]
    missing_keywords: list[str]
    detected_sections: list[str]
    missing_sections: list[str]
    red_flags: list[str]
    market_notes: list[str]
    platform_outlooks: list[PlatformOutlook]
    extracted_chars: int


def _extract_text(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        # Collapse mid-word spaces inserted by pypdf kerning artifacts
        # e.g. "T erraform" → "Terraform", "Hash iCorp" → "HashiCorp"
        return re.sub(r"(?<=[A-Za-z]) (?=[a-z])", "", text)
    except Exception:
        return ""


def _score_keywords(
    pdf_text: str,
    job_description: str,
    role_skills: list[tuple[str, str]],
) -> tuple[int, list[str], list[str]]:
    from jobfit.dashboards.scoring import skills_from_text

    in_job = skills_from_text(job_description, role_skills)
    if not in_job:
        return 100, [], []
    in_pdf = skills_from_text(pdf_text, role_skills)
    matched = sorted(in_job & in_pdf)
    missing = sorted(in_job - in_pdf)
    score = round(len(matched) / len(in_job) * 100)
    return score, matched, missing


def _score_sections(pdf_text: str) -> tuple[int, list[str], list[str]]:
    required = ["experience", "education", "skills"]
    detected = [k for k, p in _SECTION_PATTERNS.items() if p.search(pdf_text)]
    missing = [s for s in required if s not in detected]
    score = round((len(required) - len(missing)) / len(required) * 100)
    return score, detected, missing


def _score_parsability(pdf_text: str) -> int:
    chars = len(pdf_text)
    if chars < 200:
        return 0
    if chars < 500:
        return 40
    printable = sum(1 for c in pdf_text if c.isprintable() or c in "\n\t")
    return min(100, round(printable / chars * 100))


def _score_dates(cv_data: dict[str, Any]) -> tuple[int, list[str]]:
    periods: list[str] = []
    for exp in cv_data.get("experience", []):
        if p := exp.get("period", ""):
            periods.append(p)
    for edu in cv_data.get("education", []):
        if p := edu.get("period", ""):
            periods.append(p)

    if not periods:
        return 100, []

    bad: list[str] = []
    for p in periods:
        has_ok = _DATE_OK.search(p) or any(w in p.lower() for w in _CURRENT_MARKERS)
        has_bad = any(pat.search(p) for pat in _DATE_BAD)
        if has_bad or not has_ok:
            bad.append(p)

    score = round((len(periods) - len(bad)) / len(periods) * 100)
    return score, bad


def _score_contact(cv_data: dict[str, Any]) -> tuple[int, list[str]]:
    contact = cv_data.get("contact", {})
    issues: list[str] = []
    for f in ("email", "phone", "city"):
        if not contact.get(f):
            issues.append(f"Missing contact.{f}")
    if not cv_data.get("name"):
        issues.append("Missing name")
    total = 4
    score = round((total - len(issues)) / total * 100)
    return score, issues


def _parse_period_dates(period: str) -> tuple[date | None, date | None]:
    """Parse 'MM.YYYY – MM.YYYY' or 'MM.YYYY – heute' → (start, end). None on failure."""
    normalized = re.sub(r"\s*[–—\-]+\s*", "§", period.strip())
    parts = normalized.split("§")
    if len(parts) != 2:
        return None, None

    def _to_date(s: str) -> date | None:
        s = s.strip().lower()
        if s in _CURRENT_MARKERS:
            return date.today()
        m = re.match(r"^(\d{1,2})\.(\d{4})$", s)
        if m:
            month, year = int(m.group(1)), int(m.group(2))
            if 1 <= month <= 12:
                return date(year, month, 1)
        return None

    return _to_date(parts[0]), _to_date(parts[1])


def _check_timeline(cv_data: dict[str, Any]) -> list[str]:
    """Detect overlapping jobs and unexplained gaps > 6 months."""
    entries: list[tuple[date, date, str]] = []
    for exp in cv_data.get("experience", []):
        p = exp.get("period", "")
        if not p:
            continue
        start, end = _parse_period_dates(p)
        if start and end and end >= start:
            label = f"{exp.get('title', '?')} @ {exp.get('company', '?')}"
            entries.append((start, end, label))

    if len(entries) < 2:
        return []

    entries.sort(key=lambda x: x[0])
    today = date.today()
    issues: list[str] = []

    # Overlaps: consecutive pair where next starts before previous ends
    # Skip if either entry is current (legitimate parallel roles are common)
    for i in range(len(entries) - 1):
        s1, e1, l1 = entries[i]
        s2, e2, l2 = entries[i + 1]
        if e1 == today or e2 == today:
            continue
        if s2 < e1:
            months = max(1, round((e1 - s2).days / 30))
            issues.append(f"Overlapping dates (~{months} mo): \"{l1}\" and \"{l2}\"")

    # Gaps > 6 months between consecutive jobs
    for i in range(len(entries) - 1):
        _, e1, l1 = entries[i]
        s2, _, l2 = entries[i + 1]
        if e1 == today:
            continue
        gap = (s2 - e1).days
        if gap > 180:
            months = round(gap / 30)
            issues.append(f"Employment gap of ~{months} months between \"{l1}\" and \"{l2}\"")

    return issues


def _score_completeness(cv_data: dict[str, Any], timeline_issues: list[str]) -> int:
    """Score CV data completeness (not technical parsability).

    Checks: phone, LinkedIn, summary, per-experience (company + bullets),
    per-education (institution), timeline integrity.
    """
    passed = 0
    total = 0

    contact = cv_data.get("contact", {})

    # Contact: phone and LinkedIn
    for field in ("phone", "linkedin"):
        total += 1
        if contact.get(field):
            passed += 1

    # Summary non-empty
    total += 1
    if cv_data.get("summary", "").strip():
        passed += 1

    # Experience entries
    for exp in cv_data.get("experience", []):
        total += 1
        if exp.get("company"):
            passed += 1
        total += 1
        if exp.get("bullets"):
            passed += 1

    # Education entries
    for edu in cv_data.get("education", []):
        total += 1
        if edu.get("institution"):
            passed += 1

    # Timeline integrity (gaps + overlaps count as one check)
    total += 1
    if not timeline_issues:
        passed += 1

    return round(passed / total * 100) if total else 100


def _platform_outlooks(
    kw: int,
    sec: int,
    parse: int,
    date_issues: list[str],
) -> list[PlatformOutlook]:
    def st(ok: bool, warn: bool) -> str:
        return "pass" if ok else ("warn" if warn else "fail")

    kw_note = f"Coverage {kw}%." + (" Missing skills detected." if kw < 70 else "")
    parse_note = "PDF text clean." if parse >= 90 else f"Parsability {parse}%."
    sec_note = "All sections detected." if sec == 100 else f"Section score {sec}%."
    date_note = "Dates clean." if not date_issues else f"Date issues: {'; '.join(date_issues[:2])}."

    return [
        PlatformOutlook(
            "Workday",
            st(kw >= 70 and parse >= 90, kw >= 55),
            f"Keyword-heavy parser (Siemens, BMW, Bosch, large corps). {kw_note} {parse_note}",
        ),
        PlatformOutlook(
            "SAP SuccessFactors",
            st(parse >= 90 and not date_issues and sec >= 80, parse >= 80),
            f"German enterprise standard. Known date parsing bugs. {date_note} {sec_note}",
        ),
        PlatformOutlook(
            "Softgarden",
            st(parse >= 85 and sec >= 66, parse >= 70),
            f"PDF-first, built for German market (Textkernel parser). {parse_note} {sec_note}",
        ),
        PlatformOutlook(
            "Personio",
            st(parse >= 80, parse >= 60),
            f"Common at German SMB/startups. Simple parser. {parse_note}",
        ),
        PlatformOutlook(
            "d.vinci",
            st(sec >= 80 and parse >= 85, sec >= 66),
            f"Section headers critical for workflow routing. {sec_note} {parse_note}",
        ),
        PlatformOutlook(
            "rexx systems",
            st(parse >= 85 and sec >= 66, parse >= 70),
            f"Larger Mittelstand HR suite. Standard PDF parser. {parse_note}",
        ),
        PlatformOutlook(
            "Greenhouse",
            st(kw >= 65 and parse >= 90, kw >= 50),
            f"International tech companies in Germany. {kw_note} {parse_note}",
        ),
        PlatformOutlook(
            "Lever",
            st(kw >= 60 and parse >= 85, kw >= 45),
            f"Tech scale-ups and VC-backed companies. {kw_note} {parse_note}",
        ),
        PlatformOutlook(
            "Taleo (Oracle)",
            st(kw >= 65 and parse >= 90 and not date_issues, kw >= 50 and parse >= 80),
            f"Strict legacy parser, common at large corporations. {kw_note} {parse_note} {date_note}",
        ),
        PlatformOutlook(
            "iCIMS",
            st(parse >= 90 and sec >= 80, parse >= 75),
            f"Sensitive to formatting irregularities. {parse_note} {sec_note}",
        ),
    ]


def validate(
    pdf_path: Path,
    cv_data: dict[str, Any],
    job_description: str,
    role_skills: list[tuple[str, str]],
    has_photo: bool = False,
) -> ATSReport:
    """Run ATS compatibility checks. Returns ATSReport with scores and platform outlooks."""
    pdf_text = _extract_text(pdf_path)

    parse_score = _score_parsability(pdf_text)
    kw_score, matched_kw, missing_kw = _score_keywords(pdf_text, job_description, role_skills)
    sec_score, detected_secs, missing_secs = _score_sections(pdf_text)
    date_score, date_issues = _score_dates(cv_data)
    contact_score, contact_issues = _score_contact(cv_data)

    overall = round(
        kw_score * 0.40
        + sec_score * 0.25
        + parse_score * 0.20
        + date_score * 0.10
        + contact_score * 0.05
    )

    red_flags: list[str] = []

    # Keywords
    for kw in missing_kw[:5]:
        red_flags.append(f'"{kw}" in job description but absent from CV text')

    # Date format
    for p in date_issues[:2]:
        red_flags.append(f"Date format issue: {p!r}")

    # Contact completeness (name, email, phone, city)
    red_flags.extend(contact_issues)

    # LinkedIn — not scored but expected in IT roles (source: theinterviewguys.com)
    if not cv_data.get("contact", {}).get("linkedin"):
        red_flags.append("LinkedIn URL missing — expected by most IT recruiters and ATS profiles")

    # PDF parsability
    if parse_score < 80:
        red_flags.append(f"Low PDF parsability ({parse_score}%) — ATS may fail to extract text")

    # Missing sections
    for s in missing_secs:
        red_flags.append(f'Required section "{s}" not detected in PDF')

    # Experience / education field completeness
    for i, exp in enumerate(cv_data.get("experience", []), 1):
        if not exp.get("company"):
            red_flags.append(f"Experience #{i} ({exp.get('title', '?')}): missing company name")
        if not exp.get("title"):
            red_flags.append(f"Experience #{i}: missing job title")
        if not exp.get("bullets"):
            red_flags.append(f"Experience #{i} ({exp.get('title', '?')} @ {exp.get('company', '?')}): no description bullets — ATS has nothing to index")
    for i, edu in enumerate(cv_data.get("education", []), 1):
        if not edu.get("institution"):
            red_flags.append(f"Education #{i} ({edu.get('degree', '?')}): missing institution")

    # Summary
    if not cv_data.get("summary", "").strip():
        red_flags.append("Professional summary is empty — ATS uses it for initial candidate scoring")

    # Timeline: overlaps and gaps
    timeline_issues = _check_timeline(cv_data)
    red_flags.extend(timeline_issues)

    completeness = _score_completeness(cv_data, timeline_issues)

    market_notes: list[str] = []

    if not has_photo:
        market_notes.append(
            "Bewerbungsfoto: ~82% of German recruiters expect a professional photo "
            "in the top-right corner. Add one manually before applying "
            "to traditional German companies and Mittelstand. "
            "International startups and US/UK offices in Germany usually do not require a photo."
        )

    market_notes.extend([
        "Anschreiben: traditional German companies and Mittelstand expect "
        "a cover letter. International startups typically do not.",
        "Gehaltsvorstellung: salary expectations are usually stated "
        "in the Anschreiben, not in the resume.",
        "XING: more active than LinkedIn on the German market, especially among Mittelstand companies. "
        "An up-to-date XING profile improves visibility when recruiters search directly.",
    ])

    return ATSReport(
        keyword_score=kw_score,
        section_score=sec_score,
        parsability_score=parse_score,
        date_score=date_score,
        contact_score=contact_score,
        overall_score=overall,
        completeness_score=completeness,
        matched_keywords=matched_kw,
        missing_keywords=missing_kw,
        detected_sections=detected_secs,
        missing_sections=missing_secs,
        red_flags=red_flags,
        market_notes=market_notes,
        platform_outlooks=_platform_outlooks(kw_score, sec_score, parse_score, date_issues),
        extracted_chars=len(pdf_text),
    )
