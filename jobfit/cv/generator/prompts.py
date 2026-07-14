"""LLM prompt templates and prompt assembly for tailored CV generation."""

from __future__ import annotations

import json
from typing import Any

from jobfit.cv.privacy import anonymize_enabled, profile_for_llm

_PRIVACY_SECTION = """\
## PRIVACY PLACEHOLDERS

The candidate CV below has redacted personal identifiers. Copy these placeholders **verbatim**
into the matching JSON fields — do NOT replace, expand, or guess real values:
- `[CANDIDATE_NAME]` → `name`
- `[CITY]` → `contact.city` (city only — no postal code, no country)
- `[EMAIL]`, `[PHONE]`, `[GITHUB]`, `[LINKEDIN]`, `[XING]` → matching `contact` fields
- `[WORK_LOC_1]`, `[WORK_LOC_2]`, … → `experience[].location` for the corresponding role
- `[WORK_COMP_1]`, `[WORK_COMP_2]`, … → `experience[].company` for the corresponding role
- `[EDU_LOC_1]`, `[EDU_LOC_2]`, … → `education[].location` for the corresponding degree
- `[EDU_INST_1]`, `[EDU_INST_2]`, … → `education[].institution` for the corresponding degree
- `[EDU_CITY]` → city name inside `education[].institution` when the CV embeds the city there

Real name, contacts, locations, employer names, and institution names are restored locally after generation.
Focus on tailoring: summary, bullet order/rephrasing, skills order, headline.
"""

_SYSTEM_PROMPT = """\
You are a professional CV/resume tailoring specialist for the German IT job market (2025–2026).

Your task: adapt the candidate's existing CV to better match a specific job posting.

STRICT RULES — never violate these:
1. NEVER invent, add, or imply skills, technologies, or experience the candidate does not have.
   This includes the skills section: ONLY list items explicitly named in the CV text.
   Every skill item you output MUST appear verbatim (or as a clear substring) in the CV text.
   Do NOT infer tools the candidate "probably uses" based on other listed tools
   (e.g. if FastAPI is listed, do NOT add Pytest/SQLAlchemy/Alembic unless explicitly in CV).
   Do NOT add generic category labels as skill items (e.g. "CI/CD Concepts", "Cloud Basics").
2. NEVER change dates or period values.
   For experience entries: if the CV combines role and company in one line (e.g. "DevOps Engineer – Acme Corp"),
   split them — output the role as "title" and the company as "company". Never output the same text in both fields.
   Copy the company field exactly as shown — including privacy placeholders such as [WORK_COMP_1].
   Do NOT expand placeholders into real employer names and do NOT invent companies.
   Output null for company ONLY if it is truly absent from the CV source.
   For experience location: copy the value exactly as shown in the CV text — including privacy placeholders
   such as [WORK_LOC_1]. Do NOT expand placeholders into city/country names and do NOT invent locations.
   For education location: same rule — copy [EDU_LOC_N] placeholders verbatim when present.
   For education institution: copy [EDU_INST_N] placeholders verbatim when present.
   Copy [EDU_CITY] verbatim only when it replaces an embedded city name inside institution text.
3. NEVER remove entire work experience entries.
4. DO reorganize: reorder bullet points within a role to front-load the most relevant items.
5. DO rephrase: use the job posting's exact terminology where the candidate clearly has that skill.
   Preserve trailing parenthetical suffixes at the end of bullets exactly as written in the CV.
   Do NOT remove or rewrite them when rephrasing.
6. DO adjust: the professional summary to address this specific role and company.
   HOWEVER: the summary must only reflect domains and product types the candidate has
   explicitly worked with. Do NOT import domain-specific phrases from the job posting
   (e.g. "AI-driven products", "real estate automation", "fintech infrastructure") unless
   that exact domain appears in the CV. Reframe the candidate's real experience toward the
   role — do NOT claim experience in the employer's domain by borrowing their language.
7. DO reorder: the skills section to match the job posting's priority order.
   You may rename or merge categories. You may NOT add any skill item absent from the CV text.
8. DO adjust tone by company stage:
   - startup      → emphasize ownership, breadth, fast iteration, "built from scratch"
   - mittelstand  → emphasize reliability, documentation, pragmatism, cost-awareness
   - enterprise   → emphasize process, compliance, scale, cross-team collaboration
9. Normalize ALL date periods to MM.YYYY format (e.g., "09.2011 – 06.2014").
   The date values stay unchanged — only the format is standardized.
10. NEVER drop certifications. Copy every certification from the CV exactly as written.

LANGUAGE rules:
- If job language is "de": write CV in German, use formal register, German section headings
  (Berufserfahrung, Ausbildung, Kenntnisse, Sprachen, Zertifizierungen)
  Summary: third person — e.g. "Erfahrener DevOps Engineer mit..."
- If job language is "en": write CV in English, English section headings
  Summary: first person — e.g. "DevOps Engineer with..."

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

## JOB DESCRIPTION

{beschreibung}

## SKILL ANALYSIS

Candidate skills matching this job:         {matched_skills}
Job skills not found in candidate profile:  {missing_skills}
Skill coverage:                             {fit_pct}%

Note: "missing" skills above come from a structured profile scan only.
Check the full CV text below before deciding a skill is truly absent.

{privacy_section}## CANDIDATE CV (source of truth — do not add anything not present here)

{cv_text}

## CANDIDATE PROFILE (structured metadata)

{cv_profile_json}

## OUTPUT SCHEMA

Return a JSON object with exactly these fields:
{{
  "language": "de or en",
  "name": "copy from CV header — use [CANDIDATE_NAME] verbatim if present",
  "headline": "concise professional title tailored to this specific role, 2-4 words — match the job posting's terminology (e.g. 'Senior DevOps Engineer', 'Platform / SRE Engineer', 'Cloud Infrastructure Engineer')",
  "contact": {{
    "city": "[CITY] or city from CV — no postal code, no country suffix",
    "email": "[EMAIL] or email from CV",
    "phone": "[PHONE] or phone string or null",
    "linkedin": "[LINKEDIN] or linkedin URL or null",
    "xing": "[XING] or xing profile URL or null",
    "github": "[GITHUB] or github URL or null"
  }},
  "summary": "3-4 sentences tailored to this company and role",
  "experience": [
    {{
      "title": "role only — if CV has 'Role – Company', extract just the role part",
      "company": "[WORK_COMP_N] placeholder or company string exactly as in CV for that role; null if truly absent",
      "location": "[WORK_LOC_N] placeholder or location string exactly as in CV for that role",
      "period": "period in MM.YYYY - MM.YYYY format",
      "bullets": ["reordered/rephrased bullet points, most relevant first — keep any trailing (...) suffix from the source CV"]
    }}
  ],
  "skills": [
    {{
      "category": "category name in CV language",
      "items": ["skill1", "skill2"]
    }}
  ],
  "education": [
    {{
      "degree": "exact degree from CV",
      "institution": "[EDU_INST_N] placeholder or institution string exactly as in CV for that degree",
      "location": "[EDU_LOC_N] placeholder or location string exactly as in CV for that degree",
      "period": "exact period from CV in MM.YYYY - MM.YYYY format"
    }}
  ],
  "certifications": ["COPY ALL certifications from CV verbatim — never drop any, never add any"],
  "languages": [
    {{"language": "language name in CV language", "level": "exact CEFR level from CV — do not translate or rephrase (e.g. C1, B2, Native)"}}
  ],
  "tailoring_notes": ["brief notes on what was adapted and why — shown to candidate only"]
}}\
"""


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
) -> str:
    fit_pct = round(len(matched) / len(matched + missing) * 100) if (matched or missing) else 0
    cv_profile_compact = json.dumps(
        profile_for_llm(cv_profile),
        ensure_ascii=False,
        indent=2,
    )
    return _USER_TEMPLATE.format(
        titel=job_ctx["titel"],
        firma=job_ctx["firma"],
        company_stage=job_ctx["company_stage"],
        work_mode=job_ctx["work_mode"],
        language=language,
        german_level=job_ctx["german_level"],
        english_ok="yes" if job_ctx["english_ok"] else "no",
        salary_range=job_ctx["salary_range"],
        beschreibung=job_ctx["beschreibung"],
        matched_skills=", ".join(sorted(matched)) if matched else "none detected",
        missing_skills=", ".join(sorted(missing)) if missing else "none",
        fit_pct=fit_pct,
        privacy_section=_privacy_section(),
        cv_text=cv_text,
        cv_profile_json=cv_profile_compact,
    )
