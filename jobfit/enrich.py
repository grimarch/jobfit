"""Enrich job classifications with work_mode, english_ok, german_level, on_call, salary."""

import json
import re
from collections import defaultdict
from datetime import datetime

import argparse

from jobfit.roles import DEFAULT_ROLE, ROLES, Role

from loguru import logger

# ── Work mode patterns ────────────────────────────────────────────────────────

REMOTE_RE = re.compile(
    r"100\s*%\s*(remote|homeoffice)"
    r"|\bremote.{0,20}(first|only|arbeiten|möglich|erlaubt|position)"
    r"|\bremote\s*first\b"
    r"|ortsunabhängig",
    re.IGNORECASE,
)

HYBRID_RE = re.compile(
    r"\bhybrid\b"
    r"|\d+\s*tage.{0,15}(homeoffice|remote|mobil)"
    r"|(homeoffice|remote).{0,15}\d+\s*tage"
    r"|teilweise.{0,25}(remote|homeoffice|mobil)"
    r"|anteilig.{0,25}(remote|homeoffice)"
    r"|(homeoffice|remote).{0,15}(möglich|option|anteil)"
    r"|mobiles?\s+arbeiten"
    r"|\bhomeoffice\b"
    r"|\bhome.?office\b"
    # English hybrid patterns
    r"|\bwork\s+from\s+home\b"
    r"|\bwfh\b"
    r"|\d+\s*days?\s*(in|at)\s*(the\s+)?office"
    r"|office\s*(days?|presence).{0,20}\d+"
    r"|(flexible|flexibility).{0,30}remote"
    r"|remote.{0,25}(rest|part|some).{0,10}(time|week|day)"
    r"|\bremote.friendly\b",
    re.IGNORECASE,
)

# ── Language patterns ─────────────────────────────────────────────────────────

ENGLISH_OK_RE = re.compile(
    r"english\s+(is\s+)?(ok|sufficient|enough|welcome|fine|accepted)"
    r"|no\s+german\s+(language\s+)?(required|needed|necessary)"
    r"|german\s+(is\s+)?not\s+required"
    r"|working\s+language\s+(is\s+)?english"
    r"|kommunikationssprache.{0,10}english"
    r"|english.{0,10}(only|first|primarily|speaking\s+team)"
    r"|you\s+don.t\s+(need|have)\s+to\s+speak\s+german"
    r"|we\s+work\s+in\s+english",
    re.IGNORECASE,
)

# Soft adjectives only — checked after explicit CEFR (see _explicit_cefr).
# Ordered from highest to lowest — first match wins.
GERMAN_LEVEL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "C2",
        re.compile(
            r"muttersprachlich(e[sn]?)?\s*(deutsch|kenntnisse)?"
            r"|verhandlungssicher(e[sn]?)?\s*deutsch"
            r"|deutsch\s+verhandlungssicher",
            re.IGNORECASE,
        ),
    ),
    (
        "C1",
        re.compile(
            r"fließend(e[sn]?)?\s+deutsch(kenntnisse)?"
            r"|deutsch\s+fließend"
            r"|sehr\s+gut(e[sn]?)?\s+deutsch(kenntnisse)?"
            r"|deutsch(kenntnisse)?.{0,20}sehr\s+gut",
            re.IGNORECASE,
        ),
    ),
    (
        "B2",
        re.compile(
            r"gut(e[sn]?)?\s+deutsch(kenntnisse)?"
            r"|deutsch(kenntnisse)?.{0,20}gut(e[sn])?",
            re.IGNORECASE,
        ),
    ),
    (
        "B1",
        re.compile(
            r"grundkenntnisse.{0,20}deutsch"
            r"|deutsch.{0,20}grundkenntnisse",
            re.IGNORECASE,
        ),
    ),
]

# CEFR tokens near Deutsch/German. Window must cover phrases like
# "Deutsch verhandlungssicher … (mindestens B1)".
_CEFR_NEAR = 80
_CEFR_ORDER = ("A1", "A2", "B1", "B2", "C1", "C2")
_CEFR_MIN_RE = re.compile(
    r"(?:mindestens|mind\.?|min\.?|at\s+least)\s*\(?\s*(A1|A2|B1|B2|C1|C2)\b",
    re.IGNORECASE,
)
_CEFR_NEAR_DE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        level,
        re.compile(
            rf"\b{level}\b.{{0,{_CEFR_NEAR}}}(deutsch|german)"
            rf"|(deutsch|german).{{0,{_CEFR_NEAR}}}\b{level}\b",
            re.IGNORECASE,
        ),
    )
    for level in _CEFR_ORDER
]


def _explicit_cefr(text: str) -> str | None:
    """Return an explicit CEFR level when Deutsch/German is required.

    Explicit tokens beat soft adjectives (e.g. verhandlungssicher → C2).
    A stated minimum (mindestens B1) wins over nearby higher soft/CEFR noise.
    When several CEFR levels appear as alternatives (C1 oder C2), take the
    lowest — that is the requirement floor.
    """
    if not re.search(r"deutsch|german", text, re.IGNORECASE):
        return None

    mins = [m.group(1).upper() for m in _CEFR_MIN_RE.finditer(text)]
    if mins:
        return min(mins, key=_CEFR_ORDER.index)

    found = [level for level, pat in _CEFR_NEAR_DE_PATTERNS if pat.search(text)]
    if found:
        return min(found, key=_CEFR_ORDER.index)
    return None

# German stop-word density — used to detect English-language descriptions.
# German text: ~15-30 hits per 1000 chars; English text: <4.
_DE_DENSITY_RE = re.compile(
    r"\b(und|mit|für|die|der|das|wir|sie|sich|ist|sind|werden|haben|suchen|sowie)\b",
    re.IGNORECASE,
)


def _is_english_description(text: str) -> bool:
    if len(text) < 200:
        return False
    density = len(_DE_DENSITY_RE.findall(text)) / len(text) * 1000
    return density < 4


# Fallback: any mention of German as a requirement (without explicit level)
GERMAN_MENTIONED_RE = re.compile(
    r"deutsch(kenntnisse|e?\s+kenntnisse)"
    r"|deutsch.{0,20}(voraussetzung|zwingend|erforderlich)"
    r"|german.{0,20}(fluent|proficient|required|mandatory)"
    r"|kommunikationssprache.{0,10}deutsch",
    re.IGNORECASE,
)


# ── Experience years patterns ─────────────────────────────────────────────────

_EXP_EXACT_RE = re.compile(
    r"mindestens\s+(\d+)\s+jahre"
    r"|mind\.?\s+(\d+)\s+jahre"
    r"|(\d+)\+\s*jahre[n]?\s+(?:berufserfahrung|erfahrung|praxiserfahrung)"
    r"|(\d+)\s+jahre[n]?\s+(?:berufserfahrung|erfahrung|praxiserfahrung)"
    r"|(\d+)[–\-]\d+\s+jahre[n]?\s+(?:berufserfahrung|erfahrung)"
    r"|(\d+)\+?\s+years?\s+(?:of\s+)?(?:professional\s+)?experience",
    re.IGNORECASE,
)
_MEHRJAEHRIG_RE = re.compile(r"\bmehrj[aä]hrige[nr]?\b", re.IGNORECASE)
_LANGJAEHRIG_RE = re.compile(r"\blangj[aä]hrige[nr]?\b", re.IGNORECASE)


def detect_experience_years(text: str) -> int | None:
    """Return minimum years of experience required, or None if not stated."""
    m = _EXP_EXACT_RE.search(text)
    if m:
        val = next(int(g) for g in m.groups() if g is not None)
        return val if 1 <= val <= 20 else None
    if _LANGJAEHRIG_RE.search(text):
        return 5
    if _MEHRJAEHRIG_RE.search(text):
        return 3
    return None


# ── Seniority patterns ────────────────────────────────────────────────────────

_SENIORITY_LEAD_RE = re.compile(
    r"\b(?:lead|principal|manager|head\s+of|teamlead|teamleiter|chapter\s+lead)\b|\bstaff[\s/]\w+",
    re.IGNORECASE,
)
_SENIORITY_SENIOR_RE = re.compile(r"\b(senior|sr\.|founding)\b", re.IGNORECASE)
_SENIORITY_JUNIOR_RE = re.compile(
    r"\b(junior|jr\.?|entry.level|einsteiger|berufsanf[aä]nger|werkstudent|working\s+student)\b",
    re.IGNORECASE,
)


def detect_seniority(titel: str, experience_years: int | None) -> str:
    """Derive seniority from job title (primary) or required years (fallback)."""
    if _SENIORITY_LEAD_RE.search(titel):
        return "lead"
    if _SENIORITY_SENIOR_RE.search(titel):
        return "senior"
    if _SENIORITY_JUNIOR_RE.search(titel):
        return "junior"
    if experience_years is not None:
        if experience_years >= 5:
            return "senior"
        if experience_years <= 1:
            return "junior"
    return "mid"


# ── Certification patterns ────────────────────────────────────────────────────

_CERT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("CKA",       re.compile(r"\bCKA\b")),
    ("CKAD",      re.compile(r"\bCKAD\b")),
    ("CKS",       re.compile(r"\bCKS\b")),
    ("AWS-SAA",   re.compile(r"\bAWS.{0,25}(SAA|Solutions\s+Architect\s+Associate)\b", re.IGNORECASE)),
    ("AWS-SAP",   re.compile(r"\bAWS.{0,25}(SAP|Solutions\s+Architect\s+Professional)\b", re.IGNORECASE)),
    ("AWS-DVA",   re.compile(r"\bAWS.{0,25}(DVA|Developer\s+Associate)\b", re.IGNORECASE)),
    ("AWS-SOA",   re.compile(r"\bAWS.{0,25}(SOA|SysOps\s+Administrator)\b", re.IGNORECASE)),
    ("GCP-ACE",   re.compile(r"\bGCP.{0,5}(ACE|Associate\s+Cloud\s+Engineer)\b|\bGoogle\s+Cloud\s+Associate\b", re.IGNORECASE)),
    ("GCP-Pro",   re.compile(r"\bGCP.{0,5}Professional|\bGoogle\s+Cloud\s+Professional\b", re.IGNORECASE)),
    ("AZ-104",    re.compile(r"\bAZ-104\b")),
    ("AZ-400",    re.compile(r"\bAZ-400\b")),
    ("AZ-500",    re.compile(r"\bAZ-500\b")),
    ("AZ-900",    re.compile(r"\bAZ-900\b")),
    ("Terraform", re.compile(r"\bHashiCorp\s+Certified\b|\bTerraform\s+Associate\b", re.IGNORECASE)),
    ("RHCE",      re.compile(r"\bRHCE\b")),
    ("RHCSA",     re.compile(r"\bRHCSA\b")),
    ("CISSP",     re.compile(r"\bCISSP\b")),
    ("Sec+",      re.compile(r"\bCompTIA\s+Security\+\b", re.IGNORECASE)),
]


def detect_certifications(text: str) -> list[str]:
    """Return list of certifications explicitly mentioned in job posting."""
    return [name for name, pat in _CERT_PATTERNS if pat.search(text)]


# ── Education patterns ────────────────────────────────────────────────────────

_EDU_PHD_RE = re.compile(r"\b(ph\.?d\.?|doktorat|doktortitel|promotion)\b", re.IGNORECASE)
_EDU_MASTER_RE = re.compile(
    r"\b(master|m\.sc\.?|m\.eng\.?|diplom(-ingenieur)?|magisterstudium)\b",
    re.IGNORECASE,
)
_EDU_BACHELOR_RE = re.compile(
    r"\b(bachelor|b\.sc\.?|b\.eng\.?|hochschulabschluss|hochschulstudium"
    r"|universitätsabschluss|abgeschlossenes\s+studium|fachhochschule)\b",
    re.IGNORECASE,
)
_EDU_AUSBILDUNG_RE = re.compile(
    r"\b(ausbildung|berufsausbildung|ihk-abschluss|berufsschule|fachausbildung)\b",
    re.IGNORECASE,
)


def detect_education(text: str) -> str:
    """Return highest education required: phd|master|bachelor|ausbildung|unknown."""
    if _EDU_PHD_RE.search(text):
        return "phd"
    if _EDU_MASTER_RE.search(text):
        return "master"
    if _EDU_BACHELOR_RE.search(text):
        return "bachelor"
    if _EDU_AUSBILDUNG_RE.search(text):
        return "ausbildung"
    return "unknown"


# ── On-call patterns ─────────────────────────────────────────────────────────

ON_CALL_RE = re.compile(
    r"\brufbereitschaft\b"
    r"|\bbereitschaftsdienst\b"
    r"|\bon[- ]call\b"
    r"|pager.?duty"
    r"|notfall.{0,15}bereitschaft"
    r"|24/7.{0,20}bereitschaft"
    r"|\bincident.{0,20}(response|rotation|rufbereitschaft)",
    re.IGNORECASE,
)

# ── Salary patterns ───────────────────────────────────────────────────────────
# German uses "." as thousands separator: 70.000 = 70 000 EUR

_SALARY_RANGE_RE = re.compile(
    r"(\d{2,3})[.,](\d{3})\s*(?:€|eur)?\s*(?:[-–]|bis(?:\s+zu)?)\s*(\d{2,3})[.,](\d{3})",
    re.IGNORECASE,
)
_SALARY_SINGLE_RE = re.compile(
    # Optional ",–" suffix handles "50.000,–" / "50.000,-" German notation for round numbers
    r"(\d{2,3})[.,](\d{3})[,–\-]*\s*(?:€|eur|brutto|jahres(?:gehalt)?|p\.?\s*a\.?)",
    re.IGNORECASE,
)
_SALARY_CONTEXT_RE = re.compile(
    r"(?:gehalt|salary|vergütung|verdienst|brutto|jahresgehalt|compensation)"
    r"[^\d]{0,40}(\d{2,3})[.,](\d{3})",
    re.IGNORECASE,
)
# Monthly salary: "€4.415 bis €6.900 brutto im Monat" — multiply by 12
_SALARY_MONTHLY_RE = re.compile(
    r"(?:€\s*)?(\d{1,2})[.,](\d{3})[.,\d]*\s*(?:€\s*)?"
    r"(?:bis\s+(?:€\s*)?(\d{1,2})[.,](\d{3})[.,\d]*\s*(?:€\s*)?)?"
    r"brutto\s+im\s+Monat",
    re.IGNORECASE,
)


def detect_work_mode(text: str) -> str:
    if REMOTE_RE.search(text):
        return "remote"
    if HYBRID_RE.search(text):
        return "hybrid"
    return "onsite"


def detect_language(text: str) -> tuple[bool, str | None]:
    """Returns (english_ok, german_level).
    german_level: 'A1'|'A2'|'B1'|'B2'|'C1'|'C2'|'required'|None
    'required' means German is needed but level not specified.
    Explicit CEFR tokens beat soft adjectives (verhandlungssicher, fließend, …).
    """
    if ENGLISH_OK_RE.search(text):
        return True, None

    # Description written in English → team works in English
    if _is_english_description(text):
        return True, None

    # Explicit CEFR (e.g. mindestens B1) beats soft adjectives like verhandlungssicher
    cefr = _explicit_cefr(text)
    if cefr is not None:
        return False, cefr

    for level, pat in GERMAN_LEVEL_PATTERNS:
        if pat.search(text):
            return False, level

    if GERMAN_MENTIONED_RE.search(text):
        return False, "required"

    return False, None


def detect_on_call(text: str) -> bool:
    return bool(ON_CALL_RE.search(text))


def detect_salary(text: str) -> tuple[int | None, int | None]:
    """Returns (salary_min, salary_max) in EUR/year. None if not detected."""

    def parse(a: str, b: str) -> int:
        return int(a) * 1000 + int(b)

    m = _SALARY_RANGE_RE.search(text)
    if m:
        lo, hi = parse(m.group(1), m.group(2)), parse(m.group(3), m.group(4))
        if 20_000 <= lo <= 300_000 and 20_000 <= hi <= 300_000:
            return min(lo, hi), max(lo, hi)

    m = _SALARY_SINGLE_RE.search(text)
    if m:
        val = parse(m.group(1), m.group(2))
        if 20_000 <= val <= 300_000:
            return val, None

    m = _SALARY_CONTEXT_RE.search(text)
    if m:
        val = parse(m.group(1), m.group(2))
        if 20_000 <= val <= 300_000:
            return val, None

    m = _SALARY_MONTHLY_RE.search(text)
    if m:
        lo = parse(m.group(1), m.group(2)) * 12
        hi = parse(m.group(3), m.group(4)) * 12 if m.group(3) else None
        if 20_000 <= lo <= 300_000:
            if hi and 20_000 <= hi <= 300_000:
                return min(lo, hi), max(lo, hi)
            return lo, None

    return None, None


_HOURS_PER_YEAR = 1760  # 220 working days × 8 h (German standard with ~30 vacation days)


def _ats_to_eur_year(raw_val, currency: str | None, period: str | None) -> int | None:
    """Convert a structured ATS salary field to EUR/year. Returns None if not convertible."""
    if currency not in ("EUR", None):
        return None
    try:
        val = float(raw_val)
        if not (val > 0):  # also rejects NaN (NaN > 0 is False)
            return None
    except (TypeError, ValueError):
        return None
    if period == "YEAR":
        result = int(val)
    elif period == "MONTH":
        result = int(val * 12)
    elif period == "HOUR":
        result = int(val * _HOURS_PER_YEAR)
    elif period is None:
        # No period info: infer from magnitude
        if val >= 20_000:
            result = int(val)   # likely annual
        elif val >= 1_000:
            result = int(val * 12)  # likely monthly
        else:
            return None
    else:
        return None
    return result if 20_000 <= result <= 300_000 else None


def _ba_salary(job: dict) -> tuple[int | None, int | None]:
    """Extract salary from Bundesagentur structured fields (gehaltsspanneVon/Bis)."""
    vergtype = job.get("verguetungsangabe")
    try:
        von = float(job["gehaltsspanneVon"])
        bis = float(job.get("gehaltsspanneBis") or 0) or None
    except (KeyError, TypeError, ValueError):
        return None, None
    multiplier = _HOURS_PER_YEAR if vergtype == "STUNDENLOHN" else 1
    lo = int(von * multiplier)
    hi = int(bis * multiplier) if bis else None
    if not (20_000 <= lo <= 300_000):
        return None, None
    if hi and not (20_000 <= hi <= 300_000):
        hi = None
    return lo, hi


def audit(role: "Role | None" = None) -> None:
    """Print current enrich stats from DB without running detection."""
    if role is None:
        role = ROLES[DEFAULT_ROLE]

    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel, Job as JobModel

    with get_session() as session:
        rows = (
            session.query(ClsModel)
            .join(JobModel)
            .filter(JobModel.role == role.slug, JobModel.closed_at.is_(None))
            .all()
        )

    total = len(rows)
    if not total:
        logger.info("No classified open jobs found.")
        return

    no_mode = sum(1 for r in rows if not r.work_mode)
    no_sen  = sum(1 for r in rows if not r.seniority)
    no_sal  = sum(1 for r in rows if r.salary_min is None and r.salary_max is None)
    no_lang = sum(1 for r in rows if not r.english_ok and not r.german_level)
    not_enriched = sum(1 for r in rows if r.enriched_at is None)

    logger.info(f"── enrich audit ({total} open jobs) ─────────────────────────")
    if not_enriched:
        logger.warning(f"  Not yet enriched:   {not_enriched} jobs — run: jobfit enrich")
    else:
        logger.info(f"  All jobs enriched.")

    logger.info(f"  work_mode=NULL:     {no_mode}")
    logger.info(f"  seniority=NULL:     {no_sen}")
    logger.info(f"  salary=NULL:        {no_sal}  ({round(no_sal / total * 100)}%)")
    logger.info(f"  lang unknown:       {no_lang}  ({round(no_lang / total * 100)}%)")

    from collections import Counter
    logger.info("  work_mode breakdown:")
    for k, v in Counter(r.work_mode or "—" for r in rows).most_common():
        logger.info(f"    {k:<12} {v:>4}  ({round(v / total * 100)}%)")
    logger.info("  seniority breakdown:")
    for k, v in Counter(r.seniority or "—" for r in rows).most_common():
        logger.info(f"    {k:<12} {v:>4}  ({round(v / total * 100)}%)")


def run(role: "Role | None" = None, *, dry_run: bool = False) -> None:
    if role is None:
        role = ROLES[DEFAULT_ROLE]

    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel, Job as JobModel

    work_mode_counts: dict[str, int] = defaultdict(int)
    lang_counts: dict[str, int] = defaultdict(int)
    on_call_count = 0
    salary_found = 0
    enriched = 0

    with get_session() as session:
        rows = (
            session.query(ClsModel, JobModel)
            .join(JobModel)
            .filter(JobModel.role == role.slug, JobModel.closed_at.is_(None))
            .all()
        )

        if not rows:
            logger.info(
                f"Enriched 0 jobs — no classified open jobs for role '{role.slug}' "
                f"(run: jobfit classify --role {role.slug})"
            )
            return

        for cls_row, job_row in rows:
            text: str = job_row.beschreibung or ""

            work_mode = detect_work_mode(text)
            english_ok, german_level = detect_language(text)
            on_call = detect_on_call(text)

            # Prefer structured salary fields (ATS or pre-converted BA salary from migration)
            ats_sal_min = _ats_to_eur_year(
                job_row.salary_min_raw, job_row.salary_currency, job_row.salary_period
            )
            ats_sal_max = _ats_to_eur_year(
                job_row.salary_max_raw, job_row.salary_currency, job_row.salary_period
            )
            if ats_sal_min is not None or ats_sal_max is not None:
                salary_min, salary_max = ats_sal_min, ats_sal_max
            else:
                summary = job_row.salary_summary or ""
                salary_min, salary_max = detect_salary(summary) if summary else detect_salary(text)
                if salary_min is None and summary:
                    salary_min, salary_max = detect_salary(text)

            experience_years_min = detect_experience_years(text)
            seniority = detect_seniority(cls_row.titel or "", experience_years_min)
            certifications_required = detect_certifications(text)
            education_required = detect_education(text)

            if not dry_run:
                cls_row.work_mode = work_mode
                cls_row.english_ok = english_ok
                cls_row.german_level = german_level
                cls_row.on_call = on_call
                cls_row.salary_min = salary_min
                cls_row.salary_max = salary_max
                cls_row.experience_years_min = experience_years_min
                cls_row.seniority = seniority
                cls_row.certifications_required = json.dumps(certifications_required)
                cls_row.education_required = education_required
                cls_row.enriched_at = datetime.now()

            work_mode_counts[work_mode] += 1
            lang_key = "english_ok" if english_ok else (german_level or "unknown")
            lang_counts[lang_key] += 1
            if on_call:
                on_call_count += 1
            if salary_min is not None:
                salary_found += 1
            enriched += 1

    total = sum(work_mode_counts.values())
    suffix = " (dry-run)" if dry_run else ""
    logger.info(f"Enriched {enriched} jobs{suffix}")

    if total == 0:
        return

    for k, v in sorted(work_mode_counts.items(), key=lambda x: -x[1]):
        logger.debug(f"  work_mode {k:<12} {v:>4}  ({round(v / total * 100)}%)")

    level_order = ["C2", "C1", "B2", "B1", "required", "unknown", "english_ok"]
    for k in level_order:
        v = lang_counts.get(k, 0)
        if v:
            logger.debug(f"  german    {k:<12} {v:>4}  ({round(v / total * 100)}%)")

    logger.debug(f"  on_call             {on_call_count:>4}  ({round(on_call_count / total * 100)}%)")
    logger.debug(f"  salary_detected     {salary_found:>4}  ({round(salary_found / total * 100)}%)")
