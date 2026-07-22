"""Render prep context data to Markdown."""

from __future__ import annotations

from typing import Any

_HOW_TO_USE = """\
## How to use
- Fill in `why_starred` and `prep_label` for each job (human fields).
- Do not edit `prep_heuristic` or `agency_suspect` — recalculated on every export.
- Re-export merges `why_starred` / `prep_label` by `refnr` unless `--no-merge`.
- `prep_context_demo.md` is a demo file only, not a source of truth."""

_FIELD_REFERENCE = """\
## Field reference

### Header
- **CV source** — path used for skill overlap (prefer `prompts/CV.md` for interview truth).
- **Market scope** — product jobs in the chosen stage group. Default CLI `--market-scope sm` means \
**Startup + Mittelstand** (both stages). Other values: `startup`, `mittelstand`, `enterprise`.
- **As of** — latest classification `enriched_at` among exported starred rows (or export date).

### Preferences / Market snapshot
- Copied from live scoring config and product-market skill frequencies vs the CV skill set.
- **Top strengths** — skills common in the market that also appear in the CV.
- **Top gaps** — skills common in the market that do not appear in the CV.

### Starred job fields
- **S1, S2, …** — display ids; same order as the Starred tab on the targets dashboard \
(`sort_key`: higher score first, then stage, work_mode, firma). S1 = top row in the UI.
- **refnr** — stable JobFit job id; used to merge human fields on re-export. Machine-written.
- **starred_at** — when you starred the job (UTC); informational only, does not control S-order.
- **company** — employer name from DB (only with `--include-company`; `jd_excerpt` stays redacted).
- **company_type / stage / industry** — from classification.
- **work_mode / on_call / german_level / english_ok** — from enrichment.
- **tier / score** — target-company scoring (`dreamjob`, `cvbuilder`, `easywin`, `skip`), not prep fitness.
- **must_have_skills** — skills detected in the JD via the role taxonomy.
- **overlap_with_cv / gaps_vs_cv** — JD skills ∩ / − CV skills (from CV text, not `cv_profile.json`).
- **prep_heuristic** — machine prep-fitness label (advisory). Values:
  - `fit` — product, overlap ≥ 50%, stage startup/mittelstand, no stretch ceiling applied
  - `stretch` — product with weaker fit, or a ceiling demoted `fit` (see below)
  - `brand-only` — product with low overlap (< 25%) or known-brand `cvbuilder` tier
  - `skip-for-prep` — not product, or title matches junior/intern exclude regex
- **Stretch ceilings** (can only demote `fit` → `stretch`): onsite with negative weight; \
industry not in preferred (after normalize); on-call with penalty; `agency_suspect`.
- **agency_suspect** — JD matched recruitment/staffing keyword patterns (`true`/`false`).
- **prep_label** — **your** prep verdict: `fit` | `stretch` | `brand-only` | `skip-for-prep` (leave empty until decided).
- **why_starred** — **your** reason for starring (free text).
- **jd_excerpt** — truncated JD with company name / URLs / emails redacted where possible.

### What to edit
Only `prep_label` and `why_starred`. Everything else is regenerated on export."""


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


def render_job_md(job: dict[str, Any], idx: int, *, include_company: bool = False) -> str:
    lines: list[str] = [f"### S{idx}"]
    lines.append(f"- refnr: {job.get('refnr') or '-'}")
    starred_at = job.get("starred_at") or ""
    if starred_at:
        lines.append(f"- starred_at: {starred_at}")
    lines.append(f"- title: {job.get('title') or '-'}")
    if include_company:
        lines.append(f"- company: {job.get('company') or '-'}")
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
    agency = job.get("agency_suspect")
    if agency is not None:
        lines.append(f"- agency_suspect: {str(agency).lower()}")
    lines.append(f"- prep_label: {job.get('prep_label') or ''}")
    lines.append(f"- why_starred: {job.get('why_starred') or ''}")
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
    include_company = bool(data.get("include_company"))
    for i, job in enumerate(data["starred"], start=1):
        parts.append(render_job_md(job, i, include_company=include_company))
        parts.append("")
    parts.append(_HOW_TO_USE)
    parts.append("")
    field_ref = _FIELD_REFERENCE
    if not include_company:
        field_ref = field_ref.replace(
            "- **company** — employer name from DB (only with `--include-company`; "
            "`jd_excerpt` stays redacted).\n",
            "",
        )
    parts.append(field_ref)
    return "\n".join(parts)
