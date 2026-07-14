"""CV gap analysis and job recommendations based on skill vectors."""

import re
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from jobfit.config import (
    REGION_NAMES,
    REPORTS_DIR,
    STAGES,
    VIEW_CONFIGS,
    DEFAULT_VIEW,
    TOP_JOBS,
    MIN_MARKET_PCT,
)
from jobfit.cv.io import cv_read, load_cv_profile
from jobfit.scoring_config import load_scoring_config
from jobfit.dashboards.charts import (
    chart_similarity_hist,
    chart_cooccurrence,
    chart_gap,
    chart_priority_gaps,
)
from jobfit.dashboards._render import (
    _job_card_html,
    job_source_label,
    job_url,
    ensure_plotly_js,
    drawer_panel,
    page_shell,
    render_template,
)
from jobfit.roles import DEFAULT_ROLE, ROLES, Role
from jobfit.startup import require_product_jobs

from loguru import logger

OUTPUT_HTML = REPORTS_DIR / "cv_gap_analysis.html"

_CV_JS = (Path(__file__).parent / "static" / "cv.js").read_text()


def skill_vector(text: str, skills: list[tuple[str, str]] | None = None) -> np.ndarray:
    if skills is None:
        skills = ROLES[DEFAULT_ROLE].skills
    return np.array(
        [1.0 if re.search(pat, text, re.IGNORECASE) else 0.0 for _, pat in skills]
    )


def compute_view_data(
    matrix: np.ndarray,
    cv_vec: np.ndarray,
    valid_refnrs: list[str],
    classifications: dict[str, Any],
    stages_filter: list[str],
    skills: list[tuple[str, str]] | None = None,
) -> tuple[list[tuple[str, float]], list[tuple[str, float]], list[str], int]:
    if skills is None:
        skills = ROLES[DEFAULT_ROLE].skills
    mask = np.array([
        classifications[r].get("company_stage") in stages_filter
        for r in valid_refnrs
    ])
    n = int(mask.sum())
    if n == 0:
        return [], [], [], 0
    market_pct = matrix[mask].mean(axis=0) * 100
    skill_names = [name for name, _ in skills]
    gaps: list[tuple[str, float]] = []
    strengths: list[tuple[str, float]] = []
    irrelevant: list[str] = []
    for i, name in enumerate(skill_names):
        pct = float(market_pct[i])
        have = bool(cv_vec[i])
        if pct < MIN_MARKET_PCT:
            if have:
                irrelevant.append(name)
            continue
        (strengths if have else gaps).append((name, pct))
    return gaps, strengths, irrelevant, n


# ── Dimension multiplier ───────────────────────────────────────────────────────

_CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2", "native"]
_EDU_ORDER  = ["ausbildung", "bachelor", "master", "phd"]


def _cefr_rank(level: str | None) -> int:
    try:
        return _CEFR_ORDER.index(level) if level else -1
    except ValueError:
        return -1


def _edu_rank(level: str | None) -> int:
    try:
        return _EDU_ORDER.index(level) if level else -1
    except ValueError:
        return -1


def _dimension_multiplier(job_meta: dict[str, Any], profile: dict[str, Any]) -> float:
    mult = 1.0
    my_de = profile.get("german_level")
    if my_de:
        if job_meta.get("english_ok"):
            mult *= 1.05
        else:
            job_de = job_meta.get("german_level")
            if job_de and job_de not in ("required", None):
                diff = _cefr_rank(my_de) - _cefr_rank(job_de)
                if diff < 0:
                    mult *= 0.75
                elif diff > 0:
                    mult *= 1.03
    my_exp  = profile.get("experience_years")
    req_exp = job_meta.get("experience_years_min")
    if my_exp is not None and req_exp is not None:
        gap = req_exp - my_exp
        if gap > 0:
            mult *= max(0.70, 1.0 - gap * 0.05)
    my_edu  = profile.get("education")
    req_edu = job_meta.get("education_required")
    if my_edu and req_edu and req_edu not in ("unknown", "ausbildung"):
        if _edu_rank(my_edu) < _edu_rank(req_edu):
            mult *= 0.90
    return mult


# ── Market requirements ────────────────────────────────────────────────────────

def _market_requirements_html(classifications: dict[str, Any], profile: dict[str, Any]) -> str:
    jobs = list(classifications.values())
    n = len(jobs)
    if n == 0:
        return ""

    exp_values = [j["experience_years_min"] for j in jobs if j.get("experience_years_min")]
    exp_2plus  = sum(1 for v in exp_values if v >= 2)
    exp_3plus  = sum(1 for v in exp_values if v >= 3)
    exp_5plus  = sum(1 for v in exp_values if v >= 5)

    sen_counts: dict[str, int] = {}
    for j in jobs:
        sen_counts[j.get("seniority", "mid")] = sen_counts.get(j.get("seniority", "mid"), 0) + 1

    edu_counts: dict[str, int] = {}
    for j in jobs:
        e = j.get("education_required", "unknown")
        edu_counts[e] = edu_counts.get(e, 0) + 1

    cert_counts: dict[str, int] = {}
    for j in jobs:
        for c in (j.get("certifications_required") or []):
            cert_counts[c] = cert_counts.get(c, 0) + 1
    top_certs = sorted(cert_counts.items(), key=lambda x: -x[1])[:10]

    my_exp   = profile.get("experience_years")
    my_edu   = profile.get("education")
    my_sen   = profile.get("seniority")
    my_certs: set[str] = set(profile.get("certifications") or [])
    my_de    = profile.get("german_level")

    def _item(label: str, count: int, highlight: bool = False) -> dict[str, Any]:
        return {"label": label, "count": count, "pct": round(count / n * 100) if n else 0, "highlight": highlight}

    my_exp_bucket = (
        "5+" if my_exp is not None and my_exp >= 5 else
        "3+" if my_exp is not None and my_exp >= 3 else
        "2+" if my_exp is not None and my_exp >= 2 else None
    )

    exp_items = (
        [
            _item(f"≥ 5 years ({exp_5plus})", exp_5plus, highlight=(my_exp_bucket == "5+")),
            _item(f"≥ 3 years ({exp_3plus})", exp_3plus, highlight=(my_exp_bucket == "3+")),
            _item(f"≥ 2 years ({exp_2plus})", exp_2plus, highlight=(my_exp_bucket == "2+")),
            _item(f"not specified ({n - len(exp_values)})", n - len(exp_values)),
        ]
        if exp_values else []
    )

    sen_order = ["junior", "mid", "senior", "lead"]
    sen_items = [
        _item(f"{s} ({sen_counts.get(s, 0)})", sen_counts.get(s, 0), highlight=(s == my_sen))
        for s in sen_order if sen_counts.get(s)
    ]

    edu_order = ["phd", "master", "bachelor", "ausbildung", "unknown"]
    edu_items = [
        _item(f"{e} ({edu_counts.get(e, 0)})", edu_counts.get(e, 0), highlight=(e == my_edu))
        for e in edu_order if edu_counts.get(e)
    ]

    cert_items = [
        _item(f"{c} ({cnt})", cnt, highlight=(c in my_certs))
        for c, cnt in top_certs
    ]

    profile_parts: list[str] = []
    if my_exp is not None:
        profile_parts.append(f"{my_exp} years of experience")
    if my_edu:
        profile_parts.append(my_edu)
    if my_sen:
        profile_parts.append(my_sen)
    if my_de:
        profile_parts.append(f"DE {my_de}")
    if my_certs:
        profile_parts.append(f"Certs: {', '.join(sorted(my_certs))}")

    return render_template(
        "cv_market_req.html",
        profile_parts=profile_parts,
        exp_items=exp_items,
        sen_items=sen_items,
        edu_items=edu_items,
        cert_items=cert_items,
    )


# ── Drawer content ─────────────────────────────────────────────────────────────

def _priority_gaps_drawer(priority_gaps: list[tuple[str, int]], top_n: int) -> str:
    items = [{"name": name, "count": count} for name, count in priority_gaps]
    return render_template("cv_priority_gaps.html", items=items, top_n=top_n)


def _skills_list_drawer(cv_vec: np.ndarray, skill_names: list[str]) -> str:
    have_count = int(cv_vec.sum())
    items = [{"name": name, "have": bool(cv_vec[i])} for i, name in enumerate(skill_names)]
    return render_template("cv_skills_list.html", have_count=have_count, total=len(skill_names), items=items)


# ── View section ───────────────────────────────────────────────────────────────

def _view_section_html(
    v: dict[str, Any],
    top10_chart_html: str,
    what_if_preview_html: str,
) -> str:
    return render_template(
        "cv_view_section.html",
        vid=v["id"],
        label=v["label"],
        n=v["n"],
        chart_html=v["chart_html"],
        mreq=v.get("market_req_html", ""),
        irrelevant=v["irrelevant"],
        top10_chart_html=top10_chart_html,
        what_if_preview_html=what_if_preview_html,
        default_view=DEFAULT_VIEW,
        min_market_pct=MIN_MARKET_PCT,
        top_jobs=TOP_JOBS,
    )


# ── What-if ────────────────────────────────────────────────────────────────────

def _what_if_preview_html(what_if: list[dict[str, Any]], coverage_count: int, top_n: int = 10) -> str:
    return render_template("cv_whatif_preview.html", what_if=what_if, coverage_count=coverage_count, top_n=top_n)


def _what_if_drawer_html(what_if: list[dict[str, Any]], coverage_count: int) -> str:
    return render_template("cv_whatif_drawer.html", what_if=what_if, coverage_count=coverage_count)


# ── Data loaders and computation helpers ───────────────────────────────────────

def _load_db_data(
    role: "Role",
) -> tuple[dict[str, Any], dict[str, str], dict[str, str], dict[str, str], list[str]]:
    """Returns (classifications, descriptions, url_cache, source_cache, product_refnrs)."""
    from jobfit.db import get_session, cls_to_meta
    from jobfit.db.models import Classification as ClsModel, Job as JobModel

    classifications: dict[str, Any] = {}
    descriptions: dict[str, str] = {}
    url_cache: dict[str, str] = {}
    source_cache: dict[str, str] = {}
    product_refnrs: list[str] = []
    seen: set[tuple[str, str]] = set()

    with get_session() as session:
        db_rows = (
            session.query(ClsModel, JobModel)
            .join(JobModel)
            .filter(JobModel.role == role.slug, JobModel.closed_at.is_(None))
            .all()
        )
        for cls_row, job_row in db_rows:
            dedup_key = (cls_row.titel or "", cls_row.firma or "")
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            refnr = job_row.refnr
            meta = cls_to_meta(cls_row)
            classifications[refnr] = meta
            url_cache[refnr] = job_row.externe_url or ""
            source_cache[refnr] = job_source_label(job_row.ats_source or "", job_row.ats_slug or "")
            if cls_row.company_type == "product":
                product_refnrs.append(refnr)
                descriptions[refnr] = job_row.beschreibung or ""

    return classifications, descriptions, url_cache, source_cache, product_refnrs


def _build_views(
    cv_vec: np.ndarray,
    valid_refnrs: list[str],
    classifications: dict[str, Any],
    matrix: np.ndarray,
    profile: dict[str, Any],
    role: "Role",
) -> list[dict[str, Any]]:
    all_views: list[dict[str, Any]] = []
    for view_id, view_label, stages_filter in VIEW_CONFIGS:
        g, s, irr, n = compute_view_data(
            matrix, cv_vec, valid_refnrs, classifications, stages_filter, role.skills
        )
        chart_html = chart_gap(g, s, f"{view_label} (n={n})")
        filtered_cls = {
            r: classifications[r] for r in valid_refnrs
            if classifications[r].get("company_stage") in stages_filter
        }
        mreq = _market_requirements_html(filtered_cls, profile)
        all_views.append({
            "id": view_id, "label": view_label, "gaps": g, "strengths": s,
            "irrelevant": irr, "n": n, "chart_html": chart_html, "market_req_html": mreq,
        })
        logger.debug(f"  {view_label}: {len(g)} gaps, {len(s)} strengths, n={n}")
    return all_views


def _build_top_jobs(
    ranked_sims: np.ndarray,
    valid_refnrs: list[str],
    classifications: dict[str, Any],
    cv_vec: np.ndarray,
    matrix: np.ndarray,
    skill_names: list[str],
    url_cache: dict[str, str],
    source_cache: dict[str, str],
) -> list[dict[str, Any]]:
    top_jobs: list[dict[str, Any]] = []
    for idx in ranked_sims.argsort()[::-1][:TOP_JOBS]:
        refnr    = valid_refnrs[idx]
        meta     = classifications[refnr]
        job_vec  = matrix[idx]
        matched  = [skill_names[i] for i in range(len(skill_names)) if cv_vec[i] == 1 and job_vec[i] == 1]
        missing  = [skill_names[i] for i in range(len(skill_names)) if cv_vec[i] == 0 and job_vec[i] == 1]
        top_jobs.append({
            "sim":                    ranked_sims[idx],
            "titel":                  meta.get("titel", ""),
            "firma":                  meta.get("firma", refnr),
            "ort":                    meta.get("ort", ""),
            "region":                 REGION_NAMES.get(meta.get("region", ""), meta.get("region", "")),
            "stage":                  meta.get("company_stage", ""),
            "industry":               meta.get("industry", ""),
            "source":                 source_cache.get(refnr, "BA"),
            "work_mode":              meta.get("work_mode", ""),
            "english_ok":             meta.get("english_ok", False),
            "german_level":           meta.get("german_level"),
            "on_call":                meta.get("on_call", False),
            "salary_min":             meta.get("salary_min"),
            "salary_max":             meta.get("salary_max"),
            "experience_years_min":   meta.get("experience_years_min"),
            "seniority":              meta.get("seniority"),
            "certifications_required": meta.get("certifications_required", []),
            "education_required":     meta.get("education_required"),
            "matched":                matched,
            "missing":                missing,
            "url":                    job_url(refnr, url_cache.get(refnr, "")),
        })
    return top_jobs


def _compute_what_if(
    cv_vec: np.ndarray,
    sims: np.ndarray,
    matrix: np.ndarray,
    valid_refnrs: list[str],
    classifications: dict[str, Any],
    skill_names: list[str],
    url_cache: dict[str, str],
    coverage_count: int,
    coverage_threshold: float,
) -> list[dict[str, Any]]:
    what_if: list[dict[str, Any]] = []
    for i, name in enumerate(skill_names):
        if cv_vec[i] == 1:
            continue
        sim_vec    = cv_vec.copy()
        sim_vec[i] = 1.0
        new_sims   = cosine_similarity(sim_vec.reshape(1, -1), matrix)[0]
        newly      = [
            j for j in range(len(valid_refnrs))
            if sims[j] < coverage_threshold and new_sims[j] >= coverage_threshold
        ]
        if not newly:
            continue
        newly_jobs = [
            {
                "titel": classifications[valid_refnrs[j]].get("titel", ""),
                "firma": classifications[valid_refnrs[j]].get("firma", valid_refnrs[j]),
                "stage": classifications[valid_refnrs[j]].get("company_stage", ""),
                "sim":   new_sims[j],
                "url":   job_url(valid_refnrs[j], url_cache.get(valid_refnrs[j], "")),
            }
            for j in sorted(newly, key=lambda j: -new_sims[j])
        ]
        what_if.append({"name": name, "delta": len(newly), "new_count": coverage_count + len(newly), "jobs": newly_jobs})
    what_if.sort(key=lambda x: -x["delta"])
    return what_if


def _compute_priority_gaps(top_jobs: list[dict[str, Any]]) -> list[tuple[str, int]]:
    missing_counts: dict[str, int] = {}
    for job in top_jobs:
        for skill in job["missing"]:
            missing_counts[skill] = missing_counts.get(skill, 0) + 1
    return sorted(missing_counts.items(), key=lambda x: -x[1])


# ── HTML rendering ─────────────────────────────────────────────────────────────

def render_html(
    all_views: list[dict[str, Any]],
    top_jobs: list[dict[str, Any]],
    priority_gaps: list[tuple[str, int]],
    what_if: list[dict[str, Any]],
    cv_skill_count: int,
    n_jobs: int,
    coverage_count: int,
    sim_hist_html: str,
    cooc_html: str,
    n_skills: int = 0,
    profile: dict[str, Any] | None = None,
    cv_vec: np.ndarray | None = None,
    skill_names: list[str] | None = None,
    role_name: str = "",
    coverage_threshold: float = 0.0,
) -> str:
    top10_chart_html = chart_priority_gaps(priority_gaps, TOP_JOBS)
    wi_preview_html  = _what_if_preview_html(what_if, coverage_count)
    wi_drawer_html   = _what_if_drawer_html(what_if, coverage_count)

    view_sections_html = "".join(
        _view_section_html(v, top10_chart_html, wi_preview_html)
        for v in all_views
    )

    coverage_pct = round(coverage_count / n_jobs * 100) if n_jobs else 0
    kpi_row_html = render_template(
        "cv_kpi_row.html",
        cv_skill_count=cv_skill_count,
        n_skills=n_skills,
        skill_pct=round(cv_skill_count / n_skills * 100) if n_skills else 0,
        coverage_pct=coverage_pct,
        coverage_count=coverage_count,
        n_jobs=n_jobs,
        coverage_threshold=coverage_threshold,
        top3_gaps=priority_gaps[:3],
        top_jobs_n=TOP_JOBS,
    )

    job_cards_html = "".join(_job_card_html(job, profile) for job in top_jobs)

    body = render_template(
        "cv_body.html",
        all_views=all_views,
        default_view=DEFAULT_VIEW,
        kpi_row_html=kpi_row_html,
        view_sections_html=view_sections_html,
        cooc_html=cooc_html,
        job_cards_html=job_cards_html,
        top_jobs_n=TOP_JOBS,
    )

    pg_body = _priority_gaps_drawer(priority_gaps, TOP_JOBS)
    skills_body = (
        _skills_list_drawer(cv_vec, skill_names)
        if cv_vec is not None and skill_names is not None
        else "<p class='muted'>No data</p>"
    )
    drawers = (
        drawer_panel("drawer-gaps", "Priority gaps",
                     f"Skills from top {TOP_JOBS} similar jobs missing from CV", pg_body)
        + drawer_panel("drawer-coverage", f"Market Coverage — {coverage_pct}%",
                       f"Cosine similarity distribution across {n_jobs} jobs", sim_hist_html)
        + drawer_panel("drawer-skills", f"Skills in CV — {cv_skill_count} / {n_skills}",
                       "Full role skill list and CV coverage", skills_body)
        + drawer_panel("drawer-whatif", "Simulation: +1 skill",
                       "Jobs unlocked by adding a skill — expand for details", wi_drawer_html)
    )

    return page_shell("CV Dashboard", body, "cv", role_name=role_name, drawers=drawers, extra_js=_CV_JS)


# ── Main ──────────────────────────────────────────────────────────────────────


def run(role: "Role | None" = None) -> str:
    if role is None:
        role = ROLES[DEFAULT_ROLE]
    logger.info("Building CV dashboard...")
    ensure_plotly_js(REPORTS_DIR)

    config = load_scoring_config(role.slug)
    coverage_threshold = config.cv_match_coverage_threshold
    stage_weights = config.cv_match_stage_weights
    senior_filter_re = re.compile(config.cv_match_exclude_title_regex, re.IGNORECASE)

    try:
        cv_text = cv_read(role.slug)
    except FileNotFoundError as e:
        logger.error(str(e))
        return

    cv_vec         = skill_vector(cv_text, role.skills)
    profile        = load_cv_profile(role.slug)
    skill_names    = [name for name, _ in role.skills]

    classifications, descriptions, url_cache, source_cache, product_refnrs = _load_db_data(role)

    valid_refnrs = [r for r in product_refnrs if r in descriptions]
    require_product_jobs(role, product_refnrs, valid_refnrs)
    matrix       = np.vstack([skill_vector(descriptions[r], role.skills) for r in valid_refnrs])
    n_jobs       = len(valid_refnrs)
    cv_skill_count = int(cv_vec.sum())

    all_views = _build_views(cv_vec, valid_refnrs, classifications, matrix, profile, role)

    sims           = cosine_similarity(cv_vec.reshape(1, -1), matrix)[0]
    coverage_count = int((sims >= coverage_threshold).sum())

    ranked_sims = sims.copy()
    for i, refnr in enumerate(valid_refnrs):
        meta  = classifications[refnr]
        stage = meta.get("company_stage", "")
        ranked_sims[i] *= stage_weights.get(stage, 1.0)
        ranked_sims[i] *= _dimension_multiplier(meta, profile)
        if senior_filter_re.search(meta.get("titel", "")):
            ranked_sims[i] = -1

    top_jobs      = _build_top_jobs(ranked_sims, valid_refnrs, classifications, cv_vec, matrix, skill_names, url_cache, source_cache)
    priority_gaps = _compute_priority_gaps(top_jobs)
    what_if       = _compute_what_if(cv_vec, sims, matrix, valid_refnrs, classifications, skill_names, url_cache, coverage_count, coverage_threshold)

    OUTPUT_HTML.parent.mkdir(exist_ok=True)

    sim_hist_html = chart_similarity_hist(sims, coverage_threshold)
    cooc_html     = chart_cooccurrence(matrix, skill_names)

    html = render_html(
        all_views, top_jobs, priority_gaps, what_if,
        cv_skill_count, n_jobs, coverage_count,
        sim_hist_html, cooc_html,
        n_skills=len(role.skills), profile=profile,
        cv_vec=cv_vec, skill_names=skill_names, role_name=role.slug,
        coverage_threshold=coverage_threshold,
    )
    logger.info("Rendered CV dashboard")
    return html


def save(role: "Role | None" = None) -> None:
    """Generate CV dashboard and write to OUTPUT_HTML."""
    html = run(role)
    if html:
        OUTPUT_HTML.parent.mkdir(exist_ok=True)
        OUTPUT_HTML.write_text(html, encoding="utf-8")
        logger.info(f"Saved: {OUTPUT_HTML}")
