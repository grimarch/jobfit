"""Loads personal scoring/tiering preferences from data/{role}/input/scoring.yaml.

These are subjective priorities (preferred industries, salary threshold, work-mode
weights, etc.) that differ per candidate — kept out of git like the CV and brand prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from jobfit.config import STAGES, role_input_dir

SCORING_FILE_NAME = "scoring.yaml"


@dataclass(frozen=True)
class ScoringConfig:
    preferred_industries: frozenset[str]
    company_type_weights: dict[str, int]
    preferred_industry_bonus: int
    company_stage_bonus: dict[str, int]
    work_mode_weights: dict[str, int]
    english_ok_bonus: int
    on_call_penalty: int
    no_on_call_bonus: int
    german_level_weights: dict[str, int]
    salary_bonus_threshold: int
    salary_bonus_points: int
    dreamjob_min_score: int
    dreamjob_stages: list[str]
    dreamjob_require_preferred_industry: bool
    easywin_min_skill_coverage: float
    easywin_fallback_min_score: int
    cv_match_stage_weights: dict[str, float]
    cv_match_coverage_threshold: float
    cv_match_exclude_title_regex: str
    tier_text: dict[str, dict[str, str]]


def scoring_file(role_slug: str) -> Path:
    return role_input_dir(role_slug) / SCORING_FILE_NAME


def load_scoring_config(role_slug: str) -> ScoringConfig:
    path = scoring_file(role_slug)
    if not path.exists():
        raise SystemExit(
            f"Missing: {path}\n"
            f"Create it with your personal scoring preferences:\n"
            f"  cp {path.with_name(SCORING_FILE_NAME + '.example')} {path}"
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    weights = raw["weights"]
    tiers = raw["tiers"]
    cv_match = raw["cv_match"]

    dreamjob_stages = tiers["dreamjob"].get("stages", [])
    invalid_stages = [s for s in dreamjob_stages if s not in STAGES]
    if invalid_stages:
        raise SystemExit(
            f"{path}: tiers.dreamjob.stages contains invalid value(s) {invalid_stages!r}, "
            f"must be a subset of {STAGES}"
        )

    return ScoringConfig(
        preferred_industries=frozenset(raw["preferred_industries"]),
        company_type_weights=weights["company_type"],
        preferred_industry_bonus=weights["preferred_industry_bonus"],
        company_stage_bonus=weights["company_stage_bonus"],
        work_mode_weights=weights["work_mode"],
        english_ok_bonus=weights["english_ok_bonus"],
        on_call_penalty=weights["on_call_penalty"],
        no_on_call_bonus=weights["no_on_call_bonus"],
        german_level_weights=weights["german_level"],
        salary_bonus_threshold=weights["salary_bonus"]["threshold"],
        salary_bonus_points=weights["salary_bonus"]["points"],
        dreamjob_min_score=tiers["dreamjob"]["min_score"],
        dreamjob_stages=dreamjob_stages,
        dreamjob_require_preferred_industry=tiers["dreamjob"]["require_preferred_industry"],
        easywin_min_skill_coverage=tiers["easywin"]["min_skill_coverage"],
        easywin_fallback_min_score=tiers["easywin"]["fallback_min_score"],
        cv_match_stage_weights=cv_match["stage_weights"],
        cv_match_coverage_threshold=cv_match["coverage_threshold"],
        cv_match_exclude_title_regex=cv_match["exclude_title_regex"],
        tier_text=raw["tier_text"],
    )
