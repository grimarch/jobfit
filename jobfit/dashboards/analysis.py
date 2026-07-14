"""Analyze skills and geography for product companies, broken down by stage."""

import re
from collections import defaultdict
from typing import Any

from jobfit.config import (
    REGION_NAMES,
    STAGES,
)
from jobfit.dashboards._render import render_template
from jobfit.roles import DEFAULT_ROLE, ROLES, Role

from loguru import logger


def load_descriptions(classifications: dict[str, Any], role: "Role | None" = None) -> dict[str, str]:
    """Load job descriptions for product companies from DB."""
    from jobfit.db import get_session
    from jobfit.db.models import Job

    refnrs = [r for r, m in classifications.items() if m.get("company_type") == "product"]
    if not refnrs:
        return {}
    with get_session() as session:
        rows = session.query(Job.refnr, Job.beschreibung).filter(Job.refnr.in_(refnrs)).all()
    return {r: (d or "") for r, d in rows}


def count_skills(refnrs: list[str], descriptions: dict[str, str], skills: list[tuple[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name, pattern in skills:
        n = sum(
            1
            for r in refnrs
            if r in descriptions and re.search(pattern, descriptions[r], re.IGNORECASE)
        )
        counts[name] = n
    return counts


def pct(n: int, total: int) -> str:
    if total == 0:
        return "  -"
    return f"{round(n / total * 100):>3}%"


def render_skills_table(
    groups: dict[str, list[str]],
    descriptions: dict[str, str],
    lines: list[str],
    skills: list[tuple[str, str]] | None = None,
) -> None:
    if skills is None:
        skills = ROLES[DEFAULT_ROLE].skills
    counts_by_stage: dict[str, dict[str, int]] = {}
    for stage in STAGES:
        counts_by_stage[stage] = count_skills(groups[stage], descriptions, skills)

    all_refnrs = [r for refnrs in groups.values() for r in refnrs]
    counts_all = count_skills(all_refnrs, descriptions, skills)

    totals = {s: len(groups[s]) for s in STAGES}
    total_all = len(all_refnrs)

    header = (
        f"{'SKILL':<22} "
        f"{'ALL':>5}({total_all:>3})  "
        f"{'START':>5}({totals['startup']:>3})  "
        f"{'MITTEL':>5}({totals['mittelstand']:>3})  "
        f"{'ENTER':>5}({totals['enterprise']:>3})"
    )
    lines.append(header)
    lines.append("-" * len(header))

    # Sort by all-product count descending
    sorted_skills = sorted(counts_all.items(), key=lambda x: -x[1])

    for name, n_all in sorted_skills:
        if n_all == 0:
            continue
        row = f"{name:<22} {pct(n_all, total_all):>5} {n_all:>4}   "
        for stage in STAGES:
            n = counts_by_stage[stage][name]
            row += f"{pct(n, totals[stage]):>5} {n:>4}   "
        lines.append(row)


def _pct_int(n: int, total: int) -> int:
    return round(n / total * 100) if total else 0


_STAGE_LABELS = {"startup": "Startup", "mittelstand": "Mittelstand", "enterprise": "Enterprise"}


def skills_table_html(
    groups: dict[str, list[str]],
    descriptions: dict[str, str],
    skills: list[tuple[str, str]] | None = None,
) -> str:
    if skills is None:
        skills = ROLES[DEFAULT_ROLE].skills
    counts_by_stage = {s: count_skills(groups[s], descriptions, skills) for s in STAGES}
    all_refnrs = [r for refnrs in groups.values() for r in refnrs]
    counts_all = count_skills(all_refnrs, descriptions, skills)
    totals = {s: len(groups[s]) for s in STAGES}
    total_all = len(all_refnrs)
    sorted_skills = sorted(counts_all.items(), key=lambda x: -x[1])

    rows = [
        {
            "name": name,
            "n_all": n_all,
            "pct_all": _pct_int(n_all, total_all),
            "cells": [
                {"n": counts_by_stage[s][name], "pct": _pct_int(counts_by_stage[s][name], totals[s])}
                for s in STAGES
            ],
        }
        for name, n_all in sorted_skills if n_all > 0
    ]
    stage_headers = [(_STAGE_LABELS[s], totals[s]) for s in STAGES]
    return render_template("skills_table.html", total_all=total_all, stage_headers=stage_headers, rows=rows)


def geography_table_html(
    groups: dict[str, list[str]],
    classifications: dict[str, Any],
) -> str:
    region_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for stage in STAGES:
        for refnr in groups[stage]:
            raw = classifications[refnr].get("region", "")
            region = REGION_NAMES.get(raw, raw or "Unknown")
            region_counts[region][stage] += 1

    sorted_regions = sorted(region_counts.items(), key=lambda x: -sum(x[1].values()))
    rows = [
        {"region": region, "total": sum(sc.values()), "counts": [sc.get(s, 0) for s in STAGES]}
        for region, sc in sorted_regions
    ]
    return render_template(
        "geo_table.html",
        rows=rows,
        stage_labels=[_STAGE_LABELS[s] for s in STAGES],
    )


def render_geography(
    groups: dict[str, list[str]],
    classifications: dict[str, Any],
    lines: list[str],
) -> None:
    region_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for stage in STAGES:
        for refnr in groups[stage]:
            raw_region = classifications[refnr].get("region", "")
            region = REGION_NAMES.get(raw_region, raw_region or "Unknown")
            region_counts[region][stage] += 1

    totals_by_region = {r: sum(s.values()) for r, s in region_counts.items()}
    sorted_regions = sorted(totals_by_region.items(), key=lambda x: -x[1])

    header = f"{'REGION':<26} {'TOTAL':>6}  {'STARTUP':>7}  {'MITTELSTAND':>11}  {'ENTERPRISE':>10}"
    lines.append(header)
    lines.append("-" * len(header))

    for region, total in sorted_regions:
        sc = region_counts[region]
        lines.append(
            f"{region:<26} {total:>6}  "
            f"{sc.get('startup', 0):>7}  "
            f"{sc.get('mittelstand', 0):>11}  "
            f"{sc.get('enterprise', 0):>10}"
        )


def run(role: "Role | None" = None) -> None:
    if role is None:
        role = ROLES[DEFAULT_ROLE]
    logger.info("Analyzing product companies...")

    from jobfit.db import get_session, cls_to_meta
    from jobfit.db.models import Classification as ClsModel, Job as JobModel

    classifications: dict[str, Any] = {}
    descriptions: dict[str, str] = {}
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
            if cls_row.company_type == "product":
                descriptions[refnr] = job_row.beschreibung or ""

    groups: dict[str, list[str]] = {s: [] for s in STAGES}
    total_product = 0
    for refnr, meta in classifications.items():
        if meta.get("company_type") == "product":
            total_product += 1
            stage = meta.get("company_stage", "")
            if stage in groups:
                groups[stage].append(refnr)
            else:
                groups.setdefault("other", []).append(refnr)

    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"PRODUCT COMPANIES — SKILLS & GEOGRAPHY ANALYSIS [{role.label}]")
    lines.append("=" * 70)
    lines.append(
        f"Product companies: {total_product}  "
        f"(startup: {len(groups['startup'])}, "
        f"mittelstand: {len(groups['mittelstand'])}, "
        f"enterprise: {len(groups['enterprise'])})"
    )
    lines.append("")

    lines.append("=" * 70)
    lines.append("SKILLS")
    lines.append("=" * 70)
    render_skills_table(groups, descriptions, lines, role.skills)
    lines.append("")

    lines.append("=" * 70)
    lines.append("GEOGRAPHY")
    lines.append("=" * 70)
    render_geography(groups, classifications, lines)

    logger.info("Analysis done")
