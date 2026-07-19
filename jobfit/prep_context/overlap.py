"""Skill overlap, gap computation, and prep heuristic for starred jobs."""

from __future__ import annotations

from typing import Any
import re

from jobfit.dashboards.scoring import skills_from_text
from jobfit.roles._base import Role
from jobfit.scoring_config import ScoringConfig

# Overlap ratio thresholds (documented here as the single source of truth)
_FIT_RATIO = 0.5     # >= fit (if also sm stage)
_STRETCH_RATIO = 0.25  # >= stretch; < brand-only

_SM_STAGES = frozenset({"startup", "mittelstand"})


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


def prep_heuristic(
    meta: dict[str, Any],
    tier_name: str,
    overlap: list[str],
    job_skills: frozenset[str],
    config: ScoringConfig,
) -> str:
    """Classify a starred job for interview prep.

    Labels:
      fit        — product, ratio >= 0.5, stage in startup/mittelstand
      stretch    — product, 0.25 <= ratio < 0.5  (or ratio >= 0.5 but not sm stage)
      brand-only — product, tier == cvbuilder OR ratio < 0.25
      skip-for-prep — not product OR title matches exclude_title_regex

    Thresholds: _FIT_RATIO = 0.5, _STRETCH_RATIO = 0.25 (constants above).
    """
    if meta.get("company_type") != "product":
        return "skip-for-prep"

    title = meta.get("titel") or ""
    exclude_re = config.cv_match_exclude_title_regex
    if exclude_re and re.search(exclude_re, title, re.IGNORECASE):
        return "skip-for-prep"

    # cvbuilder known brands are prep-label brand-only regardless of coverage
    if tier_name == "cvbuilder":
        return "brand-only"

    ratio = len(overlap) / len(job_skills) if job_skills else 0.0
    stage = meta.get("company_stage") or ""

    if ratio >= _FIT_RATIO and stage in _SM_STAGES:
        return "fit"
    if ratio >= _STRETCH_RATIO:
        return "stretch"
    return "brand-only"
