"""Scoring, tiering, and sort-key logic for target companies."""

import re
from typing import Any

from jobfit.industry import normalize
from jobfit.scoring_config import ScoringConfig

_FIRM_NORM_RE = re.compile(
    r"(gmbh\s*&\s*co\.?\s*k?g|gmbh|ag|se|s\.a\.|inc\.?|ltd\.?|llc\.?|b\.v\.|a\.s\.|"
    r"plc\.?|s\.?a\.?r?\.?l?\.?|kg|ohg|eg|k?da?[öo]r|holding|group|digital|"
    r"deutschland|germany|international|europe)\b",
    re.IGNORECASE,
)
_FIRM_PREFIX_RE = re.compile(r"^(www\.careers?\.|www\.jobs?\.|careers?\.|www\.|jobs?\.)", re.IGNORECASE)

_STAGE_ORDER = {"startup": 0, "mittelstand": 1, "enterprise": 2, "unknown": 3}
_MODE_ORDER  = {"remote": 0, "hybrid": 1, "onsite": 2}


def skills_from_text(text: str, role_skills: list[tuple[str, str]]) -> frozenset[str]:
    """Detect which role skills appear in text."""
    return frozenset(
        name for name, pat in role_skills
        if re.search(pat, text, re.IGNORECASE)
    )


def norm_firma(name: str) -> str:
    s = _FIRM_PREFIX_RE.sub("", name.lower())
    s = re.sub(r"\.(com|de|net|org|io|eu|at|ch)\s*$", "", s)
    s = _FIRM_NORM_RE.sub("", s)
    s = re.sub(r"(?<=[a-z])\d$", "", s)
    return re.sub(r"[\s\-_.,&@+]+", "", s)


def score(meta: dict[str, Any], config: ScoringConfig) -> int:
    s = 0

    s += config.company_type_weights.get(meta.get("company_type"), 0)

    if normalize(meta.get("industry") or "") in config.preferred_industries:
        s += config.preferred_industry_bonus

    s += config.company_stage_bonus.get(meta.get("company_stage"), 0)
    s += config.work_mode_weights.get(meta.get("work_mode"), 0)

    if meta.get("english_ok"):
        s += config.english_ok_bonus

    s += config.on_call_penalty if meta.get("on_call") else config.no_on_call_bonus

    de = meta.get("german_level")
    s += config.german_level_weights.get(de or "unspecified", 0)

    if (meta.get("salary_max") or 0) >= config.salary_bonus_threshold:
        s += config.salary_bonus_points

    return s


def tier(
    job_score: int,
    meta: dict[str, Any],
    known_brands: frozenset[str],
    job_skills: frozenset[str],
    user_skills: frozenset[str],
    config: ScoringConfig,
) -> str:
    is_wanted_stage = not config.dreamjob_stages or meta.get("company_stage") in config.dreamjob_stages
    is_preferred = normalize(meta.get("industry") or "") in config.preferred_industries
    is_known_brand = norm_firma(meta.get("firma", "")) in known_brands
    if (
        job_score >= config.dreamjob_min_score
        and is_wanted_stage
        and (is_preferred or not config.dreamjob_require_preferred_industry)
    ):
        return "dreamjob"
    if is_known_brand:
        return "cvbuilder"
    if job_skills:
        if len(job_skills & user_skills) / len(job_skills) >= config.easywin_min_skill_coverage:
            return "easywin"
    elif job_score >= config.easywin_fallback_min_score:
        return "easywin"
    return "skip"


def sort_key(job: dict[str, Any]) -> tuple[int, int, int, str]:
    return (
        -job["score"],
        _STAGE_ORDER.get(job.get("company_stage") or "unknown", 9),
        _MODE_ORDER.get(job.get("work_mode") or "onsite", 9),
        job.get("firma", ""),
    )
