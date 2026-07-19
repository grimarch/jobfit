"""Unit tests for skill overlap, gaps, and prep heuristic."""

import pytest

from jobfit.prep_context.overlap import compute_cv_skills, compute_job_overlap, prep_heuristic
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
    meta = make_meta(company_type="product", company_stage="startup")
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
