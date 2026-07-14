"""LLM prompt templates and prompt assembly for tailored Anschreiben generation."""

from __future__ import annotations

import json
import re
from typing import Any

from jobfit.config import role_input_dir
from jobfit.cv.privacy import anonymize_enabled, profile_for_llm

_PRIVACY_SECTION = """\
## PRIVACY PLACEHOLDERS

The candidate CV below has redacted personal identifiers. Copy these placeholders **verbatim**
into the matching JSON fields — do NOT replace, expand, or guess real values:
- `[CANDIDATE_NAME]` → `candidate_name`
- `[EMAIL]`, `[PHONE]`, `[LINKEDIN]`, `[XING]`, `[GITHUB]` → matching `contact` fields
- `[CITY]` → `contact.city`

Employer and education redactions in CV text — NEVER copy into `body_paragraphs`:
- `[WORK_COMP_1]`, `[WORK_COMP_2]`, … are redacted past employer names
- `[EDU_INST_1]`, `[EDU_INST_2]`, … are redacted school/university names
- ❌ NEVER write `[WORK_COMP_N]` or `[EDU_INST_N]` anywhere in the letter body
- ❌ NEVER guess or invent real employer/institution names
- ✅ Refer to past roles generically instead:
  - EN: "in my most recent role", "at a previous employer", "in a recent project"
  - DE: "in meiner letzten Position", "bei einem früheren Arbeitgeber", "in einem aktuellen Projekt"

Real name and contacts are restored locally after generation.
"""

_SYSTEM_PROMPT = """\
You are a professional cover letter (Anschreiben) writer for the German IT job market (2025–2026).

Your task: write a tailored, compelling Anschreiben for the candidate based on their CV and a specific job posting.

STRICT RULES — never violate these:
1. SKILLS AND EXPERIENCE: never invent — every technical claim must be traceable to the CV.
   PERSONAL CONTEXT: when a ## CANDIDATE CONTEXT section is present, treat it as an
   authorized source for career goals, relocation needs, work-format preferences,
   availability, and company-specific motivation. Incorporate every substantive point
   from that section — do not skip any.
2. Do NOT retell the CV. Pick 2–3 most relevant achievements and elaborate with specifics.
   LENGTH: the entire letter must fit on ONE DIN A4 page (~250–380 words in `body_paragraphs`;
   including salutation and closing). Prefer exactly 4 paragraphs; use 5 only if essential.
   Keep each paragraph to 4–7 lines (~60–80 words) — dense keyword lists count as bloat.
3. NEVER use hollow generic phrases: "dynamisch", "belastbar", "flexibel", "teamfähig",
   "motiviert", "kommunikativ". Replace with concrete evidence instead.
4. Structure: exactly 4 items in `body_paragraphs` when possible (5 only if essential) — letter body ONLY:
   - Einleitung (1 paragraph): why THIS company and THIS role specifically — reference their
     tech stack, product, or company mission from the job description; weave in per-application
     notes from CANDIDATE CONTEXT (e.g. product familiarity, specific interest); end with a hint at fit.
   - Hauptteil (2–3 paragraphs): concrete achievements with numbers or outcomes where available;
     embed keywords from the job posting where the candidate genuinely has that skill;
     demonstrate soft skills through situations, not adjectives.
   - Schluss (1 paragraph): if CANDIDATE CONTEXT lists profile/situation items (relocation,
     Festanstellung, visa support, availability, work-format preferences), include them in
     1 natural sentence before the Gesprächswunsch; then direct Gesprächswunsch using
     indicative mood, NOT Konjunktiv.
     ❌ "Ich würde mich freuen" → ✅ "Ich freue mich auf ein persönliches Gespräch"
     Include Gehaltsvorstellung and/or Eintrittstermin ONLY when explicitly requested
     (see APPLICATION REQUIREMENTS section).
5. LANGUAGE: write in the language of the job posting (see "Job language" field).
   - German: formal register, Sie-form — UNLESS the job posting uses du/dich/dir,
     in which case use Du-form and open with "Hallo [Team / name]," instead of
     "Sehr geehrte Damen und Herren,"
   - English: professional register, direct tone.
6. TONE by company stage:
   - startup      → energetic, emphasize ownership, breadth, speed; cultural fit matters;
                    action verbs: "aufgebaut", "eingeführt", "optimiert", "verantwortet"
   - mittelstand  → reliable, pragmatic, cost-aware, process-minded
   - enterprise   → formal, process-oriented, cross-team collaboration, compliance awareness
7. DATE: always set `"date": null` in JSON — the application injects today's date after generation.
8. BETREFF: no leading "Betreff:" label — just the subject line text itself.
   Format: "Bewerbung als {Position}" (DE) or "Application for {Position}" (EN).
   Optionally append " – Ref. {refnr}" if a reference number is present.
9. ANREDE ends with a comma: "Sehr geehrte Damen und Herren,"
10. GRUßFORMEL has NO comma: "Mit freundlichen Grüßen" (not "...Grüßen,")
11. `body_paragraphs` must NEVER contain the salutation (`salutation` field) or the
    closing/Grußformel (`closing` field). Put Grußformel only in `closing`.
12. EMPLOYER NAMES: `body_paragraphs` must NEVER contain `[WORK_COMP_N]` tokens or real
    past employer names from the CV. The CV redacts employers for privacy — describe
    experience generically ("in my most recent role" / "in meiner letzten Position").
    Every `[WORK_COMP_N]` string in the output is a critical failure.

OUTPUT: Return ONLY a valid JSON object. No markdown fences, no commentary, no extra text.\
"""

_USER_TEMPLATE = """\
## JOB CONTEXT

Position:      {titel}
Company:       {firma}
Company stage: {company_stage}
Work mode:     {work_mode}
Job language:  {language}
German level required: {german_level}
English ok:    {english_ok}
Salary range:  {salary_range}
Uses du-form:  {uses_du_form}

## JOB DESCRIPTION

{beschreibung}

## SKILL ANALYSIS

Candidate skills matching this job:         {matched_skills}
Job skills not found in candidate profile:  {missing_skills}
Skill coverage:                             {fit_pct}%

Note: check the full CV text below before concluding a skill is truly absent.

## APPLICATION REQUIREMENTS

Gehaltsvorstellung requested in posting: {gehaltsvorstellung_requested}
Eintrittstermin requested in posting:    {starttermin_requested}

{candidate_context_section}{privacy_section}\
## CANDIDATE CV (source of truth for skills and work experience)

{cv_text}

## CANDIDATE PROFILE (structured metadata)

{cv_profile_json}

## OUTPUT SCHEMA

Return a JSON object with exactly these fields:
{{
  "language": "de or en",
  "candidate_name": "copy from CV header — use [CANDIDATE_NAME] verbatim if present",
  "contact": {{
    "city": "[CITY] or city from CV — no postal code, no country suffix",
    "email": "[EMAIL] or email from CV",
    "phone": "[PHONE] or phone string or null",
    "linkedin": "[LINKEDIN] or linkedin URL or null",
    "xing": "[XING] or xing profile URL or null",
    "github": "[GITHUB] or github URL or null"
  }},
  "date": null,
  "firma": "{firma}",
  "subject": "Bewerbung als {titel} (DE) or Application for {titel} (EN) — no 'Betreff:' prefix",
  "salutation": "Sehr geehrte Damen und Herren, (DE Sie-form) or Hallo Team, (DE Du-form if uses_du_form=yes) or Dear Hiring Team, (EN)",
  "body_paragraphs": [
    "exactly 4 paragraphs (5 only if essential) — ~250–380 words total; NEVER salutation, closing, or [WORK_COMP_N]",
    "Einleitung: why this company and role — per-application CANDIDATE CONTEXT notes here if present",
    "Hauptteil 1–2 (or 1–3): concrete achievements — refer to past roles generically, never [WORK_COMP_N]",
    "Schluss: profile/situation from CANDIDATE CONTEXT if present; then Gesprächswunsch; Gehalt/Start only if requested"
  ],
  "closing": "Grußformel ONLY here — Mit freundlichen Grüßen (DE) or Kind regards, (EN); never inside body_paragraphs",
  "gehaltsvorstellung": "salary expectation string or null — include ONLY if gehaltsvorstellung_requested=yes",
  "starttermin": "earliest start date string or null — include ONLY if starttermin_requested=yes",
  "tailoring_notes": ["note which CANDIDATE CONTEXT items were used and where — shown to candidate only"]
}}\
"""


def _load_candidate_context(role_slug: str, refnr: str) -> str:
    """Load personal candidate context from optional input files.

    Reads anschreiben_profile.md (permanent, all applications) and
    anschreiben_notes_{refnr}.md (per-job specific notes), returns combined text.
    Returns empty string if neither file exists.
    """
    import re as _re
    input_dir = role_input_dir(role_slug)
    safe_refnr = _re.sub(r"[^\w\-]", "_", refnr)

    parts: list[str] = []
    profile_path = input_dir / "anschreiben_profile.md"
    if profile_path.exists():
        text = profile_path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(f"### Personal profile & situation\n\n{text}")

    notes_path = input_dir / f"anschreiben_notes_{safe_refnr}.md"
    if notes_path.exists():
        text = notes_path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(f"### Notes for this specific application\n\n{text}")

    return "\n\n".join(parts)


_CANDIDATE_CONTEXT_HEADER = """\
## CANDIDATE CONTEXT

Personal notes from the candidate — information NOT in the CV. You MUST weave relevant
points into the letter:
- Per-application notes → Einleitung (why this company/role)
- Profile & situation (relocation, Festanstellung, visa support, availability, work-format
  preferences) → Schluss, as 1 sentence before the Gesprächswunsch
- Mention every substantive point below; do not skip any

"""


def _candidate_context_section(context: str) -> str:
    if not context:
        return ""
    return f"{_CANDIDATE_CONTEXT_HEADER}{context}\n\n"


def _detect_du_form(beschreibung: str) -> bool:
    """Return True if job posting addresses candidates in Du-form."""
    return bool(re.search(
        r"\b(dich|dir|dein|deine|deinen|deinem|deiner|du)\b",
        beschreibung,
        re.IGNORECASE,
    ))


def _detect_gehaltsvorstellung(beschreibung: str) -> bool:
    """Return True if posting explicitly requests salary expectations."""
    return bool(re.search(r"gehaltsvorstellung|gehaltswunsch|gehaltsangabe", beschreibung, re.IGNORECASE))


def _detect_starttermin(beschreibung: str) -> bool:
    """Return True if posting explicitly requests earliest start date from applicant."""
    return bool(re.search(
        r"(fr.{1,4}hestm.{1,6}gliche[rn]?\s+eintrittstermin|eintrittsdatum\s+nennen"
        r"|bitte\s+(geben|nennen)\s+Sie\s+(Ihren\s+)?eintrittstermin"
        r"|wann\s+(k.{1,4}nnen|k.{1,4}nnten)\s+Sie\s+(fr.{1,4}hestens\s+)?eintreten)",
        beschreibung,
        re.IGNORECASE,
    ))


def _privacy_section() -> str:
    if not anonymize_enabled():
        return ""
    return _PRIVACY_SECTION + "\n"


def _build_prompt(
    job_ctx: dict[str, Any],
    cv_text: str,
    cv_profile: dict[str, Any],
    matched: list[str],
    missing: list[str],
    language: str,
    candidate_context: str = "",
) -> str:
    fit_pct = round(len(matched) / len(matched + missing) * 100) if (matched or missing) else 0
    cv_profile_compact = json.dumps(
        profile_for_llm(cv_profile),
        ensure_ascii=False,
        indent=2,
    )
    beschreibung = job_ctx["beschreibung"]
    return _USER_TEMPLATE.format(
        candidate_context_section=_candidate_context_section(candidate_context),
        titel=job_ctx["titel"],
        firma=job_ctx["firma"],
        company_stage=job_ctx["company_stage"],
        work_mode=job_ctx["work_mode"],
        language=language,
        german_level=job_ctx["german_level"],
        english_ok="yes" if job_ctx["english_ok"] else "no",
        salary_range=job_ctx["salary_range"],
        uses_du_form="yes" if _detect_du_form(beschreibung) else "no",
        beschreibung=beschreibung,
        matched_skills=", ".join(sorted(matched)) if matched else "none detected",
        missing_skills=", ".join(sorted(missing)) if missing else "none",
        fit_pct=fit_pct,
        gehaltsvorstellung_requested="yes" if _detect_gehaltsvorstellung(beschreibung) else "no",
        starttermin_requested="yes" if _detect_starttermin(beschreibung) else "no",
        privacy_section=_privacy_section(),
        cv_text=cv_text,
        cv_profile_json=cv_profile_compact,
    )
