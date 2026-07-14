"""Full job listings report (BA + ATS sources)."""

from typing import Any

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from jobfit.config import (
    REGION_NAMES,
    REPORTS_DIR,
)
from jobfit.cv.io import cv_file, load_cv_profile
from jobfit.dashboards.cv import skill_vector
from jobfit.dashboards._render import (
    _job_card_html,
    job_source_label,
    job_url,
    ensure_plotly_js,
    page_shell,
    render_template,
)
from jobfit.roles import DEFAULT_ROLE, ROLES, Role

from loguru import logger

OUTPUT_HTML = REPORTS_DIR / "listings.html"


def render_ats_html(
    all_jobs: list[dict[str, Any]],
    cv_skill_count: int,
    n_skills: int = 0,
    profile: dict[str, Any] | None = None,
    role_name: str = "",
) -> str:
    _PLATFORMS = [
        ("all",               "All",              None),
        ("ba",                "BA",               ""),
        ("gh",                "GH",               "greenhouse"),
        ("lever",             "Lever",            "lever"),
        ("sr",                "SR",               "smartrecruiters"),
        ("ashby",             "Ashby",            "ashby"),
        ("workable",          "Workable",         "workable"),
        ("personio",          "Personio",         "personio"),
        ("join",              "Join",             "join_com"),
        ("successfactors",    "SAP SF",           "successfactors"),
        ("workday",           "Workday",          "workday"),
        ("softgarden",        "Softgarden",       "softgarden"),
        ("eures",             "EURES",            "eures"),
        ("phenom",            "Phenom",           "phenom"),
        ("recruitee",         "Recruitee",        "recruitee"),
        ("welcometothejungle","WttJ",             "welcometothejungle"),
        ("germantechjobs",    "GTJ",              "germantechjobs"),
        ("berlinstartupjobs", "BSJ",              "berlinstartupjobs"),
        ("adzuna",            "Adzuna",           "adzuna"),
        ("devopsjobs",        "DOJ",              "devopsjobs"),
        ("devitjobs",         "DevIT",            "devitjobs"),
        ("landingjobs",       "Landing",          "landingjobs"),
        ("echojobs",          "Echo",             "echojobs"),
    ]

    platform_jobs: dict[str, list[dict[str, Any]]] = {}
    for pid, _, psource in _PLATFORMS:
        if pid == "all":
            platform_jobs[pid] = sorted(all_jobs, key=lambda j: -j["sim"])
        else:
            platform_jobs[pid] = sorted(
                [j for j in all_jobs if j["ats_source"] == psource],
                key=lambda j: -j["sim"],
            )

    active = [(pid, lbl) for pid, lbl, _ in _PLATFORMS if platform_jobs.get(pid)]

    tabs = [
        {"pid": pid, "label": lbl, "n": len(platform_jobs[pid]), "is_active": i == 0}
        for i, (pid, lbl) in enumerate(active)
    ]

    sections_parts: list[str] = []
    for i, (pid, _) in enumerate(active):
        jobs = platform_jobs[pid]
        hidden = "" if i == 0 else ' style="display:none"'

        if pid == "all":
            cards = "".join(_job_card_html(j, profile) for j in jobs)
            sections_parts.append(f'<div data-view="{pid}"{hidden}>\n{cards}</div>\n')
        else:
            companies: dict[str, list[dict[str, Any]]] = {}
            for j in jobs:
                key = j["firma"] or j["ats_slug"] or "Unknown"
                companies.setdefault(key, []).append(j)
            sorted_companies = sorted(
                companies.items(), key=lambda kv: -max(j["sim"] for j in kv[1])
            )
            company_blocks = "".join(
                render_template(
                    "company_block.html",
                    firma=firma,
                    best=max(j["sim"] for j in cjobs),
                    n_jobs=len(cjobs),
                    stage=cjobs[0].get("stage", ""),
                    industry=cjobs[0].get("industry", ""),
                    cards_html="".join(_job_card_html(j, profile) for j in cjobs),
                )
                for firma, cjobs in sorted_companies
            )
            sections_parts.append(f'<div data-view="{pid}"{hidden}>\n{company_blocks}</div>\n')

    body = render_template(
        "listings_body.html",
        n_total=len(all_jobs),
        cv_skill_count=cv_skill_count,
        n_skills=n_skills,
        tabs=tabs,
        sections_html="".join(sections_parts),
    )
    return page_shell("Listings Dashboard", body, "listings", role_name=role_name)


def run(role: "Role | None" = None) -> str:
    if role is None:
        role = ROLES[DEFAULT_ROLE]
    logger.info("Building listings dashboard...")
    _cv_file = cv_file(role.slug)

    if not _cv_file.exists():
        logger.error(f"{_cv_file} not found.")
        return

    ensure_plotly_js(REPORTS_DIR)

    cv_vec = skill_vector(_cv_file.read_text(), role.skills)
    cv_skill_count = int(cv_vec.sum())
    profile = load_cv_profile(role.slug)
    skill_names = [name for name, _ in role.skills]

    from jobfit.db import get_session, cls_to_meta
    from jobfit.db.models import Classification as ClsModel, Job as JobModel

    logger.debug("Building listings...")
    all_jobs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    with get_session() as session:
        db_rows = (
            session.query(ClsModel, JobModel)
            .join(JobModel)
            .filter(
                JobModel.role == role.slug,
                JobModel.closed_at.is_(None),
                ClsModel.company_type == "product",
            )
            .all()
        )
        for cls_row, job_row in db_rows:
            dedup_key = (cls_row.titel or "", cls_row.firma or "")
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            meta = cls_to_meta(cls_row)
            refnr = job_row.refnr
            desc = job_row.beschreibung or ""
            job_vec = skill_vector(desc)
            sim = float(cosine_similarity(cv_vec.reshape(1, -1), job_vec.reshape(1, -1))[0][0])
            matched = [skill_names[i] for i in range(len(skill_names)) if cv_vec[i] == 1 and job_vec[i] == 1]
            missing = [skill_names[i] for i in range(len(skill_names)) if cv_vec[i] == 0 and job_vec[i] == 1]
            ats_source = job_row.ats_source or ""
            ats_slug = job_row.ats_slug or ""
            all_jobs.append({
                "sim": sim,
                "titel": meta.get("titel", ""),
                "firma": meta.get("firma", refnr),
                "ort": meta.get("ort", ""),
                "region": REGION_NAMES.get(meta.get("region", ""), meta.get("region", "")),
                "stage": meta.get("company_stage", ""),
                "industry": meta.get("industry", ""),
                "source": job_source_label(ats_source, ats_slug),
                "ats_source": ats_source,
                "ats_slug": ats_slug,
                "work_mode": meta.get("work_mode", ""),
                "english_ok": meta.get("english_ok", False),
                "german_level": meta.get("german_level"),
                "on_call": meta.get("on_call", False),
                "salary_min": meta.get("salary_min"),
                "salary_max": meta.get("salary_max"),
                "experience_years_min": meta.get("experience_years_min"),
                "seniority": meta.get("seniority"),
                "certifications_required": meta.get("certifications_required", []),
                "education_required": meta.get("education_required"),
                "matched": matched,
                "missing": missing,
                "url": job_url(refnr, job_row.externe_url or ""),
            })

    html = render_ats_html(
        all_jobs, cv_skill_count,
        n_skills=len(role.skills), profile=profile, role_name=role.slug,
    )
    logger.info("Rendered listings dashboard")
    return html


def save(role: "Role | None" = None) -> None:
    """Generate listings dashboard and write to OUTPUT_HTML."""
    html = run(role)
    if html:
        OUTPUT_HTML.write_text(html, encoding="utf-8")
        logger.info(f"Saved: {OUTPUT_HTML}")
