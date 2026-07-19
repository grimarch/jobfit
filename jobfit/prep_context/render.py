"""Render prep context data to Markdown and/or JSON."""

from __future__ import annotations

import json
from typing import Any


def _yn(val: Any) -> str:
    if val is None:
        return "unspecified"
    return str(val).lower() if isinstance(val, bool) else str(val)


def _fmt_weights(d: dict[str, float]) -> str:
    return ", ".join(f"{k}={v}" for k, v in d.items())


def render_preferences_md(prefs: dict[str, Any]) -> str:
    lines: list[str] = ["## Preferences"]
    lines.append(f"- company_type weights: {_fmt_weights(prefs['company_type_weights'])}")
    industries = ", ".join(sorted(prefs["preferred_industries"]))
    lines.append(f"- preferred industries: {industries or '-'}")
    lines.append(f"- preferred industry bonus: {prefs['preferred_industry_bonus']}")
    lines.append(f"- stage bonus: {_fmt_weights(prefs['company_stage_bonus'])}")
    lines.append(f"- work_mode weights: {_fmt_weights(prefs['work_mode_weights'])}")
    lines.append(f"- english ok bonus: {prefs['english_ok_bonus']}")
    lines.append(f"- on_call penalty: {prefs['on_call_penalty']}, no_on_call bonus: {prefs['no_on_call_bonus']}")
    if prefs.get("german_level_weights"):
        lines.append(f"- german_level weights: {_fmt_weights(prefs['german_level_weights'])}")
    lines.append(
        f"- salary bonus: >={prefs['salary_bonus_threshold']} → +{prefs['salary_bonus_points']}"
    )
    lines.append(
        f"- dreamjob: min_score={prefs['dreamjob_min_score']}, "
        f"stages={'+'.join(prefs['dreamjob_stages']) or 'any'}, "
        f"preferred_industry_required={str(prefs['dreamjob_require_preferred_industry']).lower()}"
    )
    lines.append(
        f"- easywin: min_skill_coverage={prefs['easywin_min_skill_coverage']}, "
        f"fallback_min_score={prefs['easywin_fallback_min_score']}"
    )
    return "\n".join(lines)


def render_market_md(snapshot: dict[str, Any]) -> str:
    lines: list[str] = ["## Market snapshot"]
    lines.append(
        f"Scope: product, {snapshot['scope_label']}, n={snapshot['n']}"
    )
    lines.append("")
    lines.append("**Top strengths vs CV** (market skill ∩ CV):")
    for name, pct in snapshot["strengths"]:
        lines.append(f"- {name} — {pct}%")
    if not snapshot["strengths"]:
        lines.append("- (none)")
    lines.append("")
    lines.append("**Top gaps vs CV** (market skill − CV):")
    for name, pct in snapshot["gaps"]:
        lines.append(f"- {name} — {pct}%")
    if not snapshot["gaps"]:
        lines.append("- (none)")
    return "\n".join(lines)


def render_job_md(job: dict[str, Any], idx: int) -> str:
    lines: list[str] = [f"### S{idx}"]
    lines.append(f"- title: {job.get('title') or '-'}")
    lines.append(
        f"- company_type / stage / industry: "
        f"{job.get('company_type') or '-'} / "
        f"{job.get('company_stage') or '-'} / "
        f"{job.get('industry') or '-'}"
    )
    lines.append(
        f"- work_mode / on_call / german_level / english_ok: "
        f"{job.get('work_mode') or '-'} / "
        f"{_yn(job.get('on_call'))} / "
        f"{job.get('german_level') or 'unspecified'} / "
        f"{_yn(job.get('english_ok'))}"
    )
    lines.append(
        f"- seniority / experience_years_min: "
        f"{job.get('seniority') or '-'} / "
        f"{job.get('experience_years_min') or '-'}"
    )
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")
    if salary_min or salary_max:
        lines.append(f"- salary: {salary_min or '-'} – {salary_max or '-'}")
    lines.append(f"- tier / score: {job.get('tier') or '-'} / {job.get('score', '-')}")
    must = job.get("must_have_skills") or []
    lines.append(f"- must_have_skills: [{', '.join(must)}]")
    overlap = job.get("overlap_with_cv") or []
    lines.append(f"- overlap_with_cv: [{', '.join(overlap)}]")
    gaps = job.get("gaps_vs_cv") or []
    lines.append(f"- gaps_vs_cv: [{', '.join(gaps)}]")
    lines.append(f"- prep_heuristic: {job.get('prep_heuristic') or '-'}")
    lines.append("- why_starred: ")
    excerpt = job.get("jd_excerpt") or ""
    if excerpt:
        lines.append(f"- jd_excerpt: {excerpt}")
    return "\n".join(lines)


def render_md(data: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.append("# Prep context (anonymized)")
    parts.append(f"Generated: {data['generated_at']}")
    parts.append(f"Role: {data['role']}")
    parts.append(f"CV source: {data['cv_source']}")
    parts.append(
        f"Market scope: product, {data['market_snapshot']['scope_label']}, "
        f"n={data['market_snapshot']['n']}"
    )
    parts.append(f"As of: {data['as_of']}")
    parts.append("")
    parts.append(render_preferences_md(data["preferences"]))
    parts.append("")
    parts.append(render_market_md(data["market_snapshot"]))
    parts.append("")
    parts.append("## Starred jobs")
    for i, job in enumerate(data["starred"], start=1):
        parts.append(render_job_md(job, i))
        parts.append("")
    return "\n".join(parts)


def render_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)
