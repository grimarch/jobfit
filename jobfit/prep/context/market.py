"""Market snapshot: skill frequency across product companies by stage."""

from __future__ import annotations

from typing import Any

from jobfit.config import VIEW_CONFIGS
from jobfit.dashboards.analysis import count_skills
from jobfit.roles._base import Role

_DEFAULT_TOP_N = 10


def _stages_for_scope(scope: str) -> tuple[list[str], str]:
    """Return (stages, label) for a scope key from VIEW_CONFIGS."""
    for key, label, stages in VIEW_CONFIGS:
        if key == scope:
            return stages, label
    return ["startup", "mittelstand"], "Startup + Mittelstand"


def build_market_snapshot(
    role: Role,
    cv_skills: frozenset[str],
    scope: str = "sm",
    top_n: int = _DEFAULT_TOP_N,
) -> dict[str, Any]:
    """Query DB for open product jobs in scoped stages; return skill frequency data.

    Returns:
        n           — number of matching jobs
        scope_label — human-readable scope name
        strengths   — [(skill_name, pct), ...] top skills present in CV, sorted by market freq
        gaps        — [(skill_name, pct), ...] top skills absent from CV, sorted by market freq
    """
    from jobfit.db import get_session
    from jobfit.db.models import Classification, Job

    stages, scope_label = _stages_for_scope(scope)

    descriptions: dict[str, str] = {}
    with get_session() as session:
        rows = (
            session.query(Job.refnr, Job.beschreibung)
            .join(Classification, Job.refnr == Classification.refnr)
            .filter(
                Job.role == role.slug,
                Job.closed_at.is_(None),
                Classification.company_type == "product",
                Classification.company_stage.in_(stages),
            )
            .all()
        )
        for refnr, beschreibung in rows:
            descriptions[refnr] = beschreibung or ""

    n = len(descriptions)
    refnrs = list(descriptions.keys())
    counts = count_skills(refnrs, descriptions, role.skills)

    sorted_skills = sorted(counts.items(), key=lambda x: -x[1])

    strengths: list[tuple[str, int]] = []
    gaps: list[tuple[str, int]] = []

    for name, count in sorted_skills:
        if count == 0:
            continue
        pct = round(count / n * 100) if n > 0 else 0
        if name in cv_skills:
            if len(strengths) < top_n:
                strengths.append((name, pct))
        else:
            if len(gaps) < top_n:
                gaps.append((name, pct))

    return {
        "n": n,
        "scope_label": scope_label,
        "strengths": strengths,
        "gaps": gaps,
    }
