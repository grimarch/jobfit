"""Skill overlap, gap computation, and prep heuristic for starred jobs."""

from __future__ import annotations

from typing import Any
import re

from jobfit.dashboards.scoring import skills_from_text
from jobfit.industry import normalize as normalize_industry
from jobfit.roles._base import Role
from jobfit.scoring_config import ScoringConfig

# Overlap ratio thresholds (documented here as the single source of truth).
# fit:       ratio >= _FIT_RATIO  AND  stage in startup/mittelstand
# stretch:   ratio >= _STRETCH_RATIO  (or fit conditions not met)
# brand-only: ratio < _STRETCH_RATIO  (or cvbuilder tier)
_FIT_RATIO = 0.5
_STRETCH_RATIO = 0.25

_SM_STAGES = frozenset({"startup", "mittelstand"})

# Keyword/regex patterns that indicate a recruitment or staffing agency posting.
# Applied case-insensitively to the raw JD text; any match → agency_suspect=True.
_AGENCY_PATTERNS: tuple[str, ...] = (
    r"\brecruiting\s+agency\b",
    r"\brecruitment\s+agency\b",
    r"\bstaffing\s+agency\b",
    r"\bpersonalvermittlung\b",
    r"\bpersonaldienstleister\b",
    r"\bheadhunter\b",
    r"\bour\s+clients?\s+(is|are|include)\b",
    r"\bwe\s+(place|connect|match)\b.{0,60}\b(talent|candidate|engineer)s?\b",
    r"\bconnect\b.{0,60}\bwith\s+(top|leading)\s+(companies|opportunities|employers)\b",
    r"\bon\s+behalf\s+of\b.{0,40}\b(client|company|employer)\b",
    r"\bwe\s+recruit\b",
    r"\btalent\s+acquisition\s+firm\b",
    r"\bplacement\s+(firm|agency|service)\b",
)

_AGENCY_RE = re.compile(
    "|".join(_AGENCY_PATTERNS),
    re.IGNORECASE | re.DOTALL,
)


def compute_cv_skills(cv_text: str, role: Role) -> frozenset[str]:
    return skills_from_text(cv_text, role.skills)


def compute_job_overlap(
    cv_skills: frozenset[str],
    jd_text: str,
    role: Role,
) -> tuple[frozenset[str], list[str], list[str]]:
    """Return (job_skills, overlap_sorted, gaps_sorted).

    overlap = sorted(job_skills & cv_skills)
    gaps    = sorted(job_skills - cv_skills)
    """
    job_skills = skills_from_text(jd_text, role.skills)
    overlap = sorted(job_skills & cv_skills)
    gaps = sorted(job_skills - cv_skills)
    return job_skills, overlap, gaps


def detect_agency_suspect(jd_text: str) -> bool:
    """Return True if the JD text matches known recruitment/staffing agency patterns."""
    return bool(_AGENCY_RE.search(jd_text))


def prep_heuristic(
    meta: dict[str, Any],
    tier_name: str,
    overlap: list[str],
    job_skills: frozenset[str],
    config: ScoringConfig,
    agency_suspect: bool = False,
) -> str:
    """Classify a starred job for interview prep.

    Base labels (in order of priority):
      skip-for-prep — not product company OR title matches exclude_title_regex
      brand-only    — cvbuilder tier OR ratio < _STRETCH_RATIO (0.25)
      stretch       — ratio >= _STRETCH_RATIO but not fit conditions
      fit           — ratio >= _FIT_RATIO (0.5) AND stage in startup/mittelstand

    Ceiling rules (can only demote 'fit' → 'stretch', never raise):
      work_mode=onsite  AND work_mode_weights["onsite"] < 0  → cap at stretch
      industry not in preferred_industries (after normalize)  → cap at stretch
      on_call=True      AND on_call_penalty < 0              → cap at stretch
      agency_suspect=True                                     → cap at stretch
    """
    if meta.get("company_type") != "product":
        return "skip-for-prep"

    title = meta.get("titel") or ""
    exclude_re = config.cv_match_exclude_title_regex
    if exclude_re and re.search(exclude_re, title, re.IGNORECASE):
        return "skip-for-prep"

    if tier_name == "cvbuilder":
        return "brand-only"

    ratio = len(overlap) / len(job_skills) if job_skills else 0.0
    stage = meta.get("company_stage") or ""

    if ratio >= _FIT_RATIO and stage in _SM_STAGES:
        base = "fit"
    elif ratio >= _STRETCH_RATIO:
        base = "stretch"
    else:
        base = "brand-only"

    if base != "fit":
        return base

    # Apply stretch ceilings — only meaningful when base == "fit".
    work_mode = meta.get("work_mode")
    if work_mode == "onsite" and config.work_mode_weights.get("onsite", 0) < 0:
        return "stretch"

    industry_canon = normalize_industry(meta.get("industry"))
    if industry_canon not in config.preferred_industries:
        return "stretch"

    if meta.get("on_call") and config.on_call_penalty < 0:
        return "stretch"

    if agency_suspect:
        return "stretch"

    return "fit"
