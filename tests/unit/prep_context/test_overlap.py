"""Unit tests for skill overlap, gaps, and prep heuristic."""

import pytest

from jobfit.prep_context.overlap import (
    compute_cv_skills,
    compute_job_overlap,
    detect_agency_suspect,
    prep_heuristic,
)
from tests.conftest import make_meta, make_scoring_config

_ROLE_SKILLS: list[tuple[str, str]] = [
    ("Docker",     "docker"),
    ("Kubernetes", r"kubernetes|\bk8s\b"),
    ("Terraform",  "terraform"),
    ("AWS",        r"\baws\b|amazon web services"),
    ("Ansible",    "ansible"),
]

_CONFIG = make_scoring_config()


# ── compute_cv_skills ─────────────────────────────────────────────────────────

class _FakeRole:
    skills = _ROLE_SKILLS


def test_cv_skills_detected():
    cv = "I have experience with Docker, Kubernetes and AWS."
    skills = compute_cv_skills(cv, _FakeRole())  # type: ignore[arg-type]
    assert "Docker" in skills
    assert "Kubernetes" in skills
    assert "AWS" in skills
    assert "Terraform" not in skills


# ── compute_job_overlap ───────────────────────────────────────────────────────

def test_overlap_and_gaps():
    cv = "Docker, Kubernetes, AWS"
    jd = "We use Terraform, Kubernetes, Docker and Ansible."
    cv_skills = compute_cv_skills(cv, _FakeRole())  # type: ignore[arg-type]
    job_skills, overlap, gaps = compute_job_overlap(cv_skills, jd, _FakeRole())  # type: ignore[arg-type]
    assert set(overlap) == {"Docker", "Kubernetes"}
    assert set(gaps) == {"Terraform", "Ansible"}
    assert "AWS" not in gaps  # AWS not in JD


def test_overlap_sorted():
    cv = "Docker Kubernetes AWS Terraform Ansible"
    jd = "Terraform, Kubernetes, Ansible, Docker, AWS"
    cv_skills = compute_cv_skills(cv, _FakeRole())  # type: ignore[arg-type]
    _, overlap, gaps = compute_job_overlap(cv_skills, jd, _FakeRole())  # type: ignore[arg-type]
    assert overlap == sorted(overlap)
    assert gaps == sorted(gaps)


def test_no_job_skills_empty_sets():
    cv_skills = compute_cv_skills("Java Spring Boot", _FakeRole())  # type: ignore[arg-type]
    job_skills, overlap, gaps = compute_job_overlap(cv_skills, "We need a senior engineer.", _FakeRole())  # type: ignore[arg-type]
    assert len(job_skills) == 0
    assert overlap == []
    assert gaps == []


# ── prep_heuristic ────────────────────────────────────────────────────────────

def test_heuristic_not_product_is_skip():
    meta = make_meta(company_type="consulting", company_stage="startup")
    assert prep_heuristic(meta, "skip", [], frozenset(), _CONFIG) == "skip-for-prep"


def test_heuristic_public_sector_is_skip():
    meta = make_meta(company_type="public_sector", company_stage="startup")
    assert prep_heuristic(meta, "skip", [], frozenset(), _CONFIG) == "skip-for-prep"


def test_heuristic_excluded_title_is_skip():
    # cv_match_exclude_title_regex matches lead/head/principal (senior manager titles)
    meta = make_meta(company_type="product", company_stage="startup", titel="Head of DevOps")
    assert prep_heuristic(meta, "easywin", ["Docker"], frozenset({"Docker"}), _CONFIG) == "skip-for-prep"


def test_heuristic_cvbuilder_tier_is_brand_only():
    meta = make_meta(company_type="product", company_stage="startup")
    job_skills = frozenset({"Docker", "Kubernetes", "Terraform"})
    overlap = ["Docker", "Kubernetes", "Terraform"]  # 100% but cvbuilder overrides
    assert prep_heuristic(meta, "cvbuilder", overlap, job_skills, _CONFIG) == "brand-only"


def test_heuristic_high_ratio_sm_is_fit():
    # industry must be in preferred_industries to avoid the industry ceiling.
    # "Cybersecurity" normalizes to "Cybersecurity" which is in the test config.
    meta = make_meta(company_type="product", company_stage="startup", industry="Cybersecurity")
    job_skills = frozenset({"Docker", "Kubernetes"})
    overlap = ["Docker", "Kubernetes"]  # 100% ratio
    assert prep_heuristic(meta, "dreamjob", overlap, job_skills, _CONFIG) == "fit"


def test_heuristic_high_ratio_enterprise_not_fit():
    meta = make_meta(company_type="product", company_stage="enterprise")
    job_skills = frozenset({"Docker", "Kubernetes"})
    overlap = ["Docker", "Kubernetes"]  # 100% but enterprise → stretch
    result = prep_heuristic(meta, "easywin", overlap, job_skills, _CONFIG)
    assert result == "stretch"


def test_heuristic_mid_ratio_is_stretch():
    meta = make_meta(company_type="product", company_stage="startup")
    job_skills = frozenset({"Docker", "Kubernetes", "Terraform", "AWS"})
    overlap = ["Docker"]  # 25% ratio — boundary case → stretch
    assert prep_heuristic(meta, "easywin", overlap, job_skills, _CONFIG) == "stretch"


def test_heuristic_low_ratio_is_brand_only():
    meta = make_meta(company_type="product", company_stage="startup")
    job_skills = frozenset({"Docker", "Kubernetes", "Terraform", "AWS", "Ansible"})
    overlap = []  # 0% ratio
    assert prep_heuristic(meta, "easywin", overlap, job_skills, _CONFIG) == "brand-only"


def test_heuristic_no_job_skills_zero_ratio_brand_only():
    meta = make_meta(company_type="product", company_stage="startup")
    assert prep_heuristic(meta, "easywin", [], frozenset(), _CONFIG) == "brand-only"


# ── prep_heuristic: v2 ceiling rules ─────────────────────────────────────────
# Helpers — a "would-be fit" baseline: startup, preferred industry, high ratio.
_FIT_SKILLS = frozenset({"Docker", "Kubernetes"})
_FIT_OVERLAP = ["Docker", "Kubernetes"]
_FIT_META_BASE = dict(
    company_type="product",
    company_stage="startup",
    industry="Cybersecurity",  # in preferred_industries
    work_mode="remote",
    on_call=False,
)


def test_heuristic_onsite_with_penalty_caps_at_stretch():
    meta = make_meta(**{**_FIT_META_BASE, "work_mode": "onsite"})
    # _CONFIG.work_mode_weights["onsite"] == -1 (negative penalty)
    assert prep_heuristic(meta, "easywin", _FIT_OVERLAP, _FIT_SKILLS, _CONFIG) == "stretch"


def test_heuristic_remote_no_onsite_ceiling():
    meta = make_meta(**_FIT_META_BASE)  # work_mode="remote"
    assert prep_heuristic(meta, "easywin", _FIT_OVERLAP, _FIT_SKILLS, _CONFIG) == "fit"


def test_heuristic_non_preferred_industry_caps_at_stretch():
    # "SaaS / Cloud" is not in preferred_industries → ceiling
    meta = make_meta(**{**_FIT_META_BASE, "industry": "SaaS / Cloud"})
    assert prep_heuristic(meta, "easywin", _FIT_OVERLAP, _FIT_SKILLS, _CONFIG) == "stretch"


def test_heuristic_preferred_industry_no_ceiling():
    meta = make_meta(**{**_FIT_META_BASE, "industry": "Cybersecurity"})
    assert prep_heuristic(meta, "easywin", _FIT_OVERLAP, _FIT_SKILLS, _CONFIG) == "fit"


def test_heuristic_on_call_with_penalty_caps_at_stretch():
    meta = make_meta(**{**_FIT_META_BASE, "on_call": True})
    # _CONFIG.on_call_penalty == -1 (negative)
    assert prep_heuristic(meta, "easywin", _FIT_OVERLAP, _FIT_SKILLS, _CONFIG) == "stretch"


def test_heuristic_no_on_call_no_ceiling():
    meta = make_meta(**{**_FIT_META_BASE, "on_call": False})
    assert prep_heuristic(meta, "easywin", _FIT_OVERLAP, _FIT_SKILLS, _CONFIG) == "fit"


def test_heuristic_agency_suspect_caps_at_stretch():
    meta = make_meta(**_FIT_META_BASE)
    assert prep_heuristic(
        meta, "easywin", _FIT_OVERLAP, _FIT_SKILLS, _CONFIG, agency_suspect=True
    ) == "stretch"


def test_heuristic_no_agency_no_ceiling():
    meta = make_meta(**_FIT_META_BASE)
    assert prep_heuristic(
        meta, "easywin", _FIT_OVERLAP, _FIT_SKILLS, _CONFIG, agency_suspect=False
    ) == "fit"


def test_heuristic_ceiling_does_not_raise_brand_only():
    # Ceilings only demote fit→stretch, never raise brand-only
    meta = make_meta(**{**_FIT_META_BASE, "industry": "Cybersecurity"})
    job_skills = frozenset({"Docker", "Kubernetes", "Terraform", "AWS", "Ansible"})
    overlap: list[str] = []  # 0% → brand-only base
    result = prep_heuristic(meta, "easywin", overlap, job_skills, _CONFIG)
    assert result == "brand-only"


# ── detect_agency_suspect ─────────────────────────────────────────────────────

def test_agency_suspect_staffing_agency():
    assert detect_agency_suspect("We are a staffing agency specializing in DevOps talent.")


def test_agency_suspect_recruitment_agency():
    assert detect_agency_suspect("Our recruitment agency places engineers at top firms.")


def test_agency_suspect_our_clients_include():
    assert detect_agency_suspect("Our clients include startups and digital agencies.")


def test_agency_suspect_we_recruit():
    assert detect_agency_suspect("We recruit on behalf of leading tech companies.")


def test_agency_suspect_personalvermittlung():
    assert detect_agency_suspect("Wir sind eine Personalvermittlung für IT-Fachkräfte.")


def test_agency_suspect_false_for_direct_employer():
    jd = (
        "We are building the next generation of cloud infrastructure. "
        "Join our platform team to own Kubernetes deployments end-to-end."
    )
    assert not detect_agency_suspect(jd)


def test_agency_suspect_case_insensitive():
    assert detect_agency_suspect("STAFFING AGENCY with global reach.")
