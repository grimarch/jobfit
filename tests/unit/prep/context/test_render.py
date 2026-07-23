"""Unit tests for prep context render module."""

from __future__ import annotations

import jobfit.prep.context.render as render_mod
from jobfit.prep.context.render import render_job_md, render_md


# ── Fixtures ──────────────────────────────────────────────────────────────────

_JOB: dict = {
    "id": "S1",
    "refnr": "REF-12345",
    "starred_at": "2026-07-19T12:00:00Z",
    "title": "DevOps Engineer",
    "company_type": "product",
    "company_stage": "startup",
    "industry": "SaaS / Cloud",
    "work_mode": "remote",
    "on_call": False,
    "german_level": None,
    "english_ok": True,
    "seniority": "senior",
    "experience_years_min": 3,
    "salary_min": None,
    "salary_max": None,
    "tier": "dreamjob",
    "score": 12,
    "must_have_skills": ["Docker", "Kubernetes"],
    "overlap_with_cv": ["Docker"],
    "gaps_vs_cv": ["Kubernetes"],
    "prep_heuristic": "fit",
    "agency_suspect": False,
    "prep_label": "",
    "why_starred": "",
    "jd_excerpt": "We build cloud infrastructure at scale.",
}

_PREFS: dict = {
    "company_type_weights": {"product": 3, "consulting": -3},
    "preferred_industries": ["AI / ML"],
    "preferred_industry_bonus": 2,
    "company_stage_bonus": {"startup": 2},
    "work_mode_weights": {"remote": 3},
    "english_ok_bonus": 2,
    "on_call_penalty": -1,
    "no_on_call_bonus": 1,
    "german_level_weights": {},
    "salary_bonus_threshold": 90000,
    "salary_bonus_points": 2,
    "dreamjob_min_score": 9,
    "dreamjob_stages": ["startup"],
    "dreamjob_require_preferred_industry": True,
    "easywin_min_skill_coverage": 0.80,
    "easywin_fallback_min_score": 3,
}

_MARKET: dict = {
    "n": 42,
    "scope_label": "startup + mittelstand",
    "strengths": [("Docker", 80)],
    "gaps": [("Helm", 60)],
}

_DATA: dict = {
    "generated_at": "2026-07-19T00:00:00Z",
    "role": "devops",
    "cv_source": "prompts/CV.md",
    "as_of": "2026-07-15",
    "preferences": _PREFS,
    "market_snapshot": _MARKET,
    "starred": [_JOB],
}


# ── render_job_md ─────────────────────────────────────────────────────────────

def test_job_md_has_refnr():
    out = render_job_md(_JOB, 1)
    assert "- refnr: REF-12345" in out


def test_job_md_refnr_appears_before_title():
    out = render_job_md(_JOB, 1)
    assert out.index("- refnr:") < out.index("- title:")


def test_job_md_has_starred_at_when_present():
    out = render_job_md(_JOB, 1)
    assert "- starred_at: 2026-07-19T12:00:00Z" in out
    assert out.index("- refnr:") < out.index("- starred_at:") < out.index("- title:")


def test_job_md_omits_starred_at_when_empty():
    job = {**_JOB, "starred_at": ""}
    out = render_job_md(job, 1)
    assert "starred_at" not in out


def test_md_field_reference_mentions_dashboard_sort():
    out = render_md(_DATA)
    ref = out[out.index("## Field reference"):]
    assert "Starred tab" in ref
    assert "sort_key" in ref
    assert "starred_at" in ref


def test_job_md_has_prep_label_slot():
    out = render_job_md(_JOB, 1)
    assert "- prep_label: " in out


def test_job_md_has_why_starred_slot():
    out = render_job_md(_JOB, 1)
    assert "- why_starred: " in out


def test_job_md_has_prep_heuristic():
    out = render_job_md(_JOB, 1)
    assert "- prep_heuristic: fit" in out


def test_job_md_prep_label_after_prep_heuristic():
    out = render_job_md(_JOB, 1)
    assert out.index("- prep_heuristic:") < out.index("- prep_label:")


def test_job_md_why_starred_after_prep_label():
    out = render_job_md(_JOB, 1)
    assert out.index("- prep_label:") < out.index("- why_starred:")


def test_job_md_missing_refnr_renders_dash():
    job = {**_JOB, "refnr": None}
    out = render_job_md(job, 1)
    assert "- refnr: -" in out


def test_job_md_section_header():
    out = render_job_md(_JOB, 3)
    assert out.startswith("### S3")


# ── render_md ─────────────────────────────────────────────────────────────────

def test_md_has_how_to_use_section():
    out = render_md(_DATA)
    assert "## How to use" in out


def test_md_how_to_use_mentions_why_starred():
    out = render_md(_DATA)
    assert "why_starred" in out[out.index("## How to use"):]


def test_md_how_to_use_mentions_prep_label():
    out = render_md(_DATA)
    assert "prep_label" in out[out.index("## How to use"):]


def test_md_how_to_use_warns_about_prep_heuristic():
    out = render_md(_DATA)
    assert "prep_heuristic" in out[out.index("## How to use"):]


def test_md_has_field_reference_section():
    out = render_md(_DATA)
    assert "## Field reference" in out
    ref = out[out.index("## Field reference"):]
    assert "Startup + Mittelstand" in ref
    assert "`fit`" in ref and "`stretch`" in ref
    assert "`brand-only`" in ref and "`skip-for-prep`" in ref
    assert "prep_label" in ref and "why_starred" in ref
    assert "agency_suspect" in ref
    assert "tier / score" in ref or "**tier / score**" in ref


def test_md_field_reference_after_how_to_use():
    out = render_md(_DATA)
    assert out.index("## How to use") < out.index("## Field reference")


def test_md_starred_section_contains_refnr():
    out = render_md(_DATA)
    assert "- refnr: REF-12345" in out


def test_md_no_json_render_function():
    assert not hasattr(render_mod, "render_json"), (
        "render_json must be removed — only Markdown output is supported"
    )


# ── agency_suspect field ──────────────────────────────────────────────────────

def test_job_md_has_agency_suspect_false():
    out = render_job_md({**_JOB, "agency_suspect": False}, 1)
    assert "- agency_suspect: false" in out


def test_job_md_has_agency_suspect_true():
    out = render_job_md({**_JOB, "agency_suspect": True}, 1)
    assert "- agency_suspect: true" in out


def test_job_md_agency_suspect_omitted_when_none():
    job = {k: v for k, v in _JOB.items() if k != "agency_suspect"}
    out = render_job_md(job, 1)
    assert "agency_suspect" not in out


def test_job_md_agency_suspect_after_prep_heuristic():
    out = render_job_md({**_JOB, "agency_suspect": True}, 1)
    assert out.index("- prep_heuristic:") < out.index("- agency_suspect:")


# ── prep_label merge round-trip ───────────────────────────────────────────────

def test_job_md_prep_label_with_value():
    out = render_job_md({**_JOB, "prep_label": "fit"}, 1)
    assert "- prep_label: fit" in out


def test_job_md_why_starred_with_value():
    out = render_job_md({**_JOB, "why_starred": "great remote culture"}, 1)
    assert "- why_starred: great remote culture" in out


def test_job_md_omits_company_by_default():
    job = {**_JOB, "company": "Acme GmbH"}
    out = render_job_md(job, 1)
    assert "- company:" not in out


def test_job_md_renders_company_when_flag_set():
    job = {**_JOB, "company": "Acme GmbH"}
    out = render_job_md(job, 1, include_company=True)
    assert "- company: Acme GmbH" in out
    assert out.index("- title:") < out.index("- company:")


def test_job_md_company_dash_when_empty_and_flag_set():
    job = {**_JOB, "company": ""}
    out = render_job_md(job, 1, include_company=True)
    assert "- company: -" in out


def test_md_field_reference_omits_company_by_default():
    out = render_md(_DATA)
    ref = out[out.index("## Field reference"):]
    assert "**company**" not in ref


def test_md_field_reference_includes_company_when_flag_set():
    data = {**_DATA, "include_company": True}
    out = render_md(data)
    ref = out[out.index("## Field reference"):]
    assert "**company**" in ref
    assert "--include-company" in ref
