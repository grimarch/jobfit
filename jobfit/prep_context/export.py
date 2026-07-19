"""Main export logic: query starred jobs, build and write prep context."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from jobfit.dashboards.scoring import score as compute_score, tier as compute_tier, norm_firma
from jobfit.prep_context.market import build_market_snapshot
from jobfit.prep_context.overlap import compute_cv_skills, compute_job_overlap, prep_heuristic
from jobfit.prep_context.redact import redact_excerpt
from jobfit.prep_context.render import render_md
from jobfit.roles import ROLES
from jobfit.scoring_config import load_scoring_config


def _load_cv_text(cv_path: Path | None, role_slug: str) -> tuple[str, str]:
    """Return (cv_text, cv_source_label). cv_path takes priority over role default."""
    if cv_path is not None:
        text = cv_path.read_text(encoding="utf-8")
        return text, str(cv_path)
    from jobfit.cv.io import cv_read, cv_file
    source = str(cv_file(role_slug))
    return cv_read(role_slug), source


def _load_known_brands(role_slug: str) -> frozenset[str]:
    from jobfit.db import get_session
    from jobfit.db.models import KnownBrand
    with get_session() as session:
        rows = (
            session.query(KnownBrand.firma)
            .filter(KnownBrand.role == role_slug, KnownBrand.is_known.is_(True))
            .all()
        )
    return frozenset(norm_firma(r.firma) for r in rows)


def _query_starred(role_slug: str, include_closed: bool) -> list[tuple[Any, Any]]:
    from jobfit.db import get_session
    from jobfit.db.models import Classification, Job
    with get_session() as session:
        q = (
            session.query(Classification, Job)
            .join(Job, Classification.refnr == Job.refnr)
            .filter(
                Classification.role == role_slug,
                Classification.starred_at.isnot(None),
            )
        )
        if not include_closed:
            q = q.filter(Job.closed_at.is_(None))
        q = q.order_by(Classification.starred_at.desc())
        rows = q.all()
    return rows  # type: ignore[return-value]


def _as_of_date(rows: list[tuple[Any, Any]]) -> str:
    dates = [
        cls_row.enriched_at
        for cls_row, _ in rows
        if cls_row.enriched_at is not None
    ]
    if dates:
        return max(dates).date().isoformat()
    return datetime.now(timezone.utc).date().isoformat()


def _build_preferences(role_slug: str) -> dict[str, Any]:
    config = load_scoring_config(role_slug)
    return {
        "company_type_weights": config.company_type_weights,
        "preferred_industries": sorted(config.preferred_industries),
        "preferred_industry_bonus": config.preferred_industry_bonus,
        "company_stage_bonus": config.company_stage_bonus,
        "work_mode_weights": config.work_mode_weights,
        "english_ok_bonus": config.english_ok_bonus,
        "on_call_penalty": config.on_call_penalty,
        "no_on_call_bonus": config.no_on_call_bonus,
        "german_level_weights": config.german_level_weights,
        "salary_bonus_threshold": config.salary_bonus_threshold,
        "salary_bonus_points": config.salary_bonus_points,
        "dreamjob_min_score": config.dreamjob_min_score,
        "dreamjob_stages": config.dreamjob_stages,
        "dreamjob_require_preferred_industry": config.dreamjob_require_preferred_industry,
        "easywin_min_skill_coverage": config.easywin_min_skill_coverage,
        "easywin_fallback_min_score": config.easywin_fallback_min_score,
    }


def _build_job_record(
    cls_row: Any,
    job_row: Any,
    idx: int,
    cv_skills: frozenset[str],
    role_slug: str,
    known_brands: frozenset[str],
    config: Any,
    role: Any,
    jd_excerpt_chars: int,
) -> dict[str, Any]:
    from jobfit.db import cls_to_meta

    meta = cls_to_meta(cls_row)
    job_score = compute_score(meta, config)
    job_skills, overlap, gaps = compute_job_overlap(cv_skills, job_row.beschreibung or "", role)
    job_tier = compute_tier(job_score, meta, known_brands, job_skills, cv_skills, config)
    heuristic = prep_heuristic(meta, job_tier, overlap, job_skills, config)
    excerpt = redact_excerpt(
        job_row.beschreibung or "",
        cls_row.firma or job_row.firma or "",
        jd_excerpt_chars,
    )

    return {
        "id": f"S{idx}",
        "refnr": cls_row.refnr,
        "title": cls_row.titel or job_row.titel or "",
        "company_type": meta.get("company_type"),
        "company_stage": meta.get("company_stage"),
        "industry": meta.get("industry"),
        "work_mode": meta.get("work_mode"),
        "on_call": meta.get("on_call"),
        "german_level": meta.get("german_level"),
        "english_ok": meta.get("english_ok"),
        "seniority": meta.get("seniority"),
        "experience_years_min": meta.get("experience_years_min"),
        "salary_min": meta.get("salary_min"),
        "salary_max": meta.get("salary_max"),
        "tier": job_tier,
        "score": job_score,
        "must_have_skills": sorted(job_skills),
        "overlap_with_cv": overlap,
        "gaps_vs_cv": gaps,
        "prep_heuristic": heuristic,
        "why_starred": "",
        "jd_excerpt": excerpt,
    }


def run(
    role_slug: str,
    cv_path: Path | None,
    out_path: Path,
    jd_excerpt_chars: int,
    market_scope: str,
    include_closed: bool,
    dry_run: bool,
) -> None:
    """Build and write the anonymized Markdown prep context file.

    Args:
        role_slug:        Role slug (e.g. "devops").
        cv_path:          Path to CV file; if None, uses role default via cv_read().
        out_path:         Output path for the Markdown file.
        jd_excerpt_chars: Max chars of JD excerpt per job (0 = no excerpt).
        market_scope:     VIEW_CONFIGS key: "sm", "startup", "mittelstand", "enterprise".
        include_closed:   Include starred jobs whose closed_at is set.
        dry_run:          Print summary counts without writing files.
    """
    role = ROLES[role_slug]
    config = load_scoring_config(role_slug)
    cv_text, cv_source = _load_cv_text(cv_path, role_slug)
    cv_skills = compute_cv_skills(cv_text, role)

    rows = _query_starred(role_slug, include_closed)
    known_brands = _load_known_brands(role_slug)
    market = build_market_snapshot(role, cv_skills, scope=market_scope)

    starred_records: list[dict[str, Any]] = []
    for idx, (cls_row, job_row) in enumerate(rows, start=1):
        record = _build_job_record(
            cls_row, job_row, idx, cv_skills, role_slug,
            known_brands, config, role, jd_excerpt_chars,
        )
        starred_records.append(record)

    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    as_of = _as_of_date(rows)

    data: dict[str, Any] = {
        "generated_at": now_utc,
        "role": role_slug,
        "cv_source": cv_source,
        "as_of": as_of,
        "preferences": _build_preferences(role_slug),
        "market_snapshot": market,
        "starred": starred_records,
    }

    logger.info(
        "prep-context: role={}, starred={}, market_n={}, cv={}",
        role_slug,
        len(starred_records),
        market["n"],
        cv_source,
    )

    if dry_run:
        print(
            f"dry-run: {len(starred_records)} starred jobs, "
            f"market n={market['n']} ({market['scope_label']}), "
            f"cv={cv_source}"
        )
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_md(data), encoding="utf-8")
    logger.info("Wrote {}", out_path)
