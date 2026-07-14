"""Unit tests for jobfit/dashboards/targets.py — location, scoring, tiering."""

import pytest

from jobfit.dashboards.targets import (
    _clean_ort,
    _first_city,
)
from jobfit.dashboards.scoring import norm_firma as _norm_firma, score as _score, tier as _tier
from tests.conftest import make_meta, make_scoring_config

_CONFIG = make_scoring_config()


# ── _clean_ort ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ort,expected", [
    # Multi-city: prefer German city
    ("New York, San Francisco, Munich or London",               "Munich"),
    ("New York or London",                                      "New York or London"),  # no DE city, no comma → or-strip not applied
    ("London, Berlin, Amsterdam",                               "Berlin"),

    # Multi-country: Germany present but bare country
    ("Italy, Austria, Finland, France, Germany, Netherlands",   "Germany"),
    ("Germany, Munich",                                         "Munich"),   # bare country skipped in favor of city
    ("Deutschland, Berlin",                                     "Berlin"),

    # Single German city
    ("Berlin",                                                  "Berlin"),
    ("München",                                                 "München"),

    # Semicolons: pick first German segment
    ("München; Hamburg; Berlin",                                "München"),
    ("New York; Berlin",                                        "Berlin"),

    # NUTS codes
    ("DE (DE1)",                                                "Baden-Württ."),
    ("DE (DE1, DE2)",                                           "Baden-Württ. +1"),

    # Remote strip
    ("Berlin (remote possible)",                                "Berlin"),
    ("Remote, Berlin",                                          "Berlin"),

    # Street address → postal code extraction
    # Note: compound "Musterstraße" has no \b before "straße", street regex doesn't fire
    ("Musterstraße 12, 80333 München",                          "80333 München"),
    # Single-digit house number: \b matches after the digit (next char is comma)
    ("Muster Str. 5, 80333 München",                            "München"),

    # Empty / garbage
    ("",                                                        ""),
    ("---",                                                     ""),

    # Pure remote with no city: remote-strip clears the string but ort stays unchanged,
    # _first_city returns token as fallback (no —)
    ("Remote only",                                             "Remote only"),
])
def test_clean_ort(ort, expected):
    assert _clean_ort(ort) == expected


# ── _first_city ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("parts,expected", [
    (["Berlin", "Germany"],         "Berlin"),   # skips country
    (["Germany", "Austria"],        "Germany"),  # fallback to tokens[0]
    (["Bayern", "München"],         "München"),  # skips Bundesland on pass 1
    (["remote", "Berlin"],          "Berlin"),   # skips work mode
    (["Remote only"],               "Remote only"),  # fallback
])
def test_first_city(parts, expected):
    assert _first_city(parts) == expected


# ── _norm_firma ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,expected", [
    ("Acme GmbH & Co. KG",         "acme"),
    ("Startup AG",                  "startup"),
    ("careers.acme.com",            "acme"),
    ("www.jobs.startup.io",         "startup"),
    ("ACME Digital Deutschland",    "acme"),
    ("Intershop1",                  "intershop"),
])
def test_norm_firma(name, expected):
    assert _norm_firma(name) == expected


def test_norm_firma_same_company_deduplication():
    """Two variants of the same company should normalize to identical strings."""
    assert _norm_firma("Acme GmbH") == _norm_firma("ACME gmbh")


# ── _score ────────────────────────────────────────────────────────────────────

def test_score_high():
    meta = make_meta(
        company_type="product",
        company_stage="startup",
        industry="AI / ML",
        work_mode="remote",
        english_ok=True,
        on_call=False,
        german_level=None,
        salary_max=95000,
    )
    assert _score(meta, _CONFIG) >= 12


def test_score_consulting_penalty():
    meta = make_meta(
        company_type="consulting",
        work_mode="onsite",
        english_ok=False,
        on_call=True,
        salary_max=None,
    )
    assert _score(meta, _CONFIG) <= 0


def test_score_product_hybrid_mid():
    meta = make_meta(
        company_type="product",
        company_stage="mittelstand",
        industry="IT Services / B2B",
        work_mode="hybrid",
        english_ok=False,
        on_call=False,
        german_level="B2",
        salary_max=None,
    )
    score = _score(meta, _CONFIG)
    assert 2 <= score <= 8


def test_score_c2_german_penalty():
    meta = make_meta(german_level="C2", on_call=True, work_mode="onsite")
    base = make_meta(german_level=None, on_call=False, work_mode="remote")
    assert _score(meta, _CONFIG) < _score(base, _CONFIG)


def test_score_high_salary_bonus():
    without_salary = make_meta(salary_max=None)
    with_salary = make_meta(salary_max=90000)
    assert _score(with_salary, _CONFIG) == _score(without_salary, _CONFIG) + 2


# ── _tier ─────────────────────────────────────────────────────────────────────

def _brand(name: str) -> frozenset:
    return frozenset([_norm_firma(name)])


def test_tier_dreamjob():
    meta = make_meta(
        company_stage="startup",
        industry="Gaming / Media",
        work_mode="remote",
        english_ok=True,
        on_call=False,
        german_level=None,
        salary_max=95000,
    )
    score = _score(meta, _CONFIG)
    assert score >= 9
    result = _tier(score, meta, frozenset(), frozenset(), frozenset(), _CONFIG)
    assert result == "dreamjob"


def test_tier_cvbuilder_known_brand():
    meta = make_meta(company_stage="enterprise", firma="Siemens AG")
    score = _score(meta, _CONFIG)
    brands = _brand("Siemens AG")
    assert _tier(score, meta, brands, frozenset(), frozenset(), _CONFIG) == "cvbuilder"


def test_tier_easywin_by_skill_coverage():
    skills = frozenset(["kubernetes", "terraform", "ansible", "docker", "linux"])
    user_skills = frozenset(["kubernetes", "terraform", "ansible", "docker", "linux", "helm"])
    meta = make_meta(company_stage="enterprise", industry="Other", work_mode="onsite")
    score = _score(meta, _CONFIG)
    assert _tier(score, meta, frozenset(), skills, user_skills, _CONFIG) == "easywin"


def test_tier_easywin_by_score_no_skills():
    meta = make_meta(company_stage="mittelstand", work_mode="hybrid", english_ok=True)
    score = _score(meta, _CONFIG)
    assert score >= 3
    assert _tier(score, meta, frozenset(), frozenset(), frozenset(), _CONFIG) == "easywin"


def test_tier_skip_low_skill_coverage():
    skills = frozenset(["kubernetes", "terraform", "ansible", "docker", "puppet"])
    user_skills = frozenset(["kubernetes"])  # 20% coverage
    meta = make_meta(company_stage="unknown", work_mode="onsite", on_call=True,
                     english_ok=False, german_level="C2", company_type="consulting")
    score = _score(meta, _CONFIG)
    assert _tier(score, meta, frozenset(), skills, user_skills, _CONFIG) == "skip"


def test_tier_known_brand_enterprise():
    """Known brand enterprise company → cvbuilder (not dreamjob: not startup+preferred)."""
    meta = make_meta(
        firma="Big Corp",
        company_stage="enterprise",
        industry="IT Services / B2B",  # not preferred → dreamjob can't trigger
        work_mode="onsite",
        english_ok=False,
        salary_max=None,
    )
    score = _score(meta, _CONFIG)
    brands = _brand("Big Corp")
    assert _tier(score, meta, brands, frozenset(), frozenset(), _CONFIG) == "cvbuilder"


def test_tier_dreamjob_wins_over_brand():
    """dreamjob check fires before known_brand — this is intentional code order."""
    meta = make_meta(
        firma="Big Corp",
        company_stage="startup",
        industry="Cybersecurity",
        work_mode="remote",
        english_ok=True,
        salary_max=95000,
    )
    score = _score(meta, _CONFIG)
    assert score >= 9
    brands = _brand("Big Corp")
    # dreamjob condition is checked first in _tier(), known brand loses
    assert _tier(score, meta, brands, frozenset(), frozenset(), _CONFIG) == "dreamjob"
