"""Shared fixtures for jobfit test suite."""

import pytest

from jobfit.scoring_config import ScoringConfig

# ── Sample texts ──────────────────────────────────────────────────────────────

GERMAN_TEXT_DENSE = (
    "Wir suchen einen erfahrenen DevOps Engineer für unser Team. "
    "Die Stelle ist in München und wir sind ein dynamisches Unternehmen. "
    "Sie werden mit modernen Tools und Technologien arbeiten. "
    "Wir bieten eine spannende Herausforderung und ein motiviertes Team. "
    "Sie haben mehrjährige Erfahrung und sind selbstständig. "
    "Wir freuen uns auf Ihre Bewerbung und sind gespannt auf Sie."
)

ENGLISH_TEXT_SPARSE = (
    "We are looking for an experienced DevOps Engineer to join our platform team. "
    "You will be working with Kubernetes, Terraform, and AWS in a cloud-native environment. "
    "Our stack includes GitLab CI, ArgoCD, and Prometheus for observability. "
    "You bring strong experience with infrastructure as code and container orchestration. "
    "We value collaboration, ownership, and continuous improvement. "
    "Join a team that ships fast and cares about reliability."
)


# ── BA job dict helpers ───────────────────────────────────────────────────────

def make_ba_job(lands: list[str] | None = None, has_locs: bool = True) -> dict:
    """Build a minimal BA job dict with stellenlokationen."""
    if not has_locs:
        return {}
    if lands is None:
        return {"stellenlokationen": []}
    return {
        "stellenlokationen": [
            {"adresse": {"land": land}} for land in lands
        ]
    }


def make_ba_job_no_land() -> dict:
    """BA job with stellenlokationen but no land field in adresse."""
    return {"stellenlokationen": [{"adresse": {}}]}


# ── Scoring config helper ───────────────────────────────────────────────────

def make_scoring_config(**overrides) -> ScoringConfig:
    """Build a ScoringConfig with the project's original hardcoded defaults."""
    defaults = dict(
        preferred_industries=frozenset({"Gaming / Media", "Cybersecurity", "AI / ML"}),
        company_type_weights={"product": 3, "consulting": -3, "public_sector": -3},
        preferred_industry_bonus=2,
        company_stage_bonus={"startup": 2, "mittelstand": 1},
        work_mode_weights={"remote": 3, "hybrid": 1, "onsite": -1},
        english_ok_bonus=2,
        on_call_penalty=-1,
        no_on_call_bonus=1,
        german_level_weights={"unspecified": 1, "C2": -1},
        salary_bonus_threshold=90_000,
        salary_bonus_points=2,
        dreamjob_min_score=9,
        dreamjob_stages=["startup"],
        dreamjob_require_preferred_industry=True,
        easywin_min_skill_coverage=0.80,
        easywin_fallback_min_score=3,
        cv_match_stage_weights={"startup": 1.3, "mittelstand": 1.2, "enterprise": 0.8},
        cv_match_coverage_threshold=0.4,
        cv_match_exclude_title_regex=r"\b(lead|head|principal|referatsleitung|teamleiter)\b",
        tier_text={
            "starred": {
                "summary": "Your shortlist — starred jobs from all tiers.",
                "criteria": "Contains jobs you starred in any tier",
                "scoring_note": "No placement rule — star any job via ★.",
            },
            "dreamjob": {
                "tagline": "Top priority, full preparation.",
            },
            "cvbuilder": {
                "summary": "Recognised IT brand — a strong line on the CV.",
                "criteria": "Recognised <strong>IT brand</strong>",
                "scoring_note": "Placement: recognised IT brand.",
            },
            "easywin": {
                "summary": "Strong skill match — not a dreamjob, not a brand.",
            },
            "skip": {
                "summary": "Weak match on key factors.",
                "criteria": "Consulting · public sector · poor skill match",
                "scoring_note": "Placement: catch-all.",
            },
        },
    )
    return ScoringConfig(**{**defaults, **overrides})


# ── Classification meta helpers ───────────────────────────────────────────────

def make_meta(**kwargs) -> dict:
    defaults = {
        "company_type": "product",
        "company_stage": "startup",
        "industry": "SaaS / Cloud",
        "work_mode": "remote",
        "english_ok": True,
        "on_call": False,
        "german_level": None,
        "salary_max": None,
    }
    return {**defaults, **kwargs}
