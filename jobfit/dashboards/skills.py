"""Generate visual HTML report for product companies skills analysis."""

import re
from collections import defaultdict
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from jobfit.config import (
    REPORTS_DIR,
    REGION_NAMES,
    STAGES,
)
from jobfit.dashboards.analysis import (
    load_descriptions,
    skills_table_html,
    geography_table_html,
)
from jobfit.dashboards._render import ensure_plotly_js, page_shell, render_template
from jobfit.roles import DEFAULT_ROLE, ROLES, Role

from loguru import logger

OUTPUT_HTML = REPORTS_DIR / "product_skills_chart.html"
TOP_N = 20

STAGE_LABELS = {"startup": "Startup", "mittelstand": "Mittelstand", "enterprise": "Enterprise"}
STAGE_COLORS = {"startup": "#3b7dd8", "mittelstand": "#f1a44e", "enterprise": "#27a269"}

_FONT = dict(family="system-ui,-apple-system,sans-serif", size=12)
_BG   = dict(plot_bgcolor="white", paper_bgcolor="white")
_GRID = "#eef0f5"
_CFG  = {"responsive": True, "displayModeBar": True, "displaylogo": False}


def _html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, config=_CFG)


def _load_classifications(role: Role) -> dict[str, dict[str, Any]]:
    from jobfit.db import get_session, cls_to_meta
    from jobfit.db.models import Classification as ClsModel, Job as JobModel

    with get_session() as session:
        rows = (
            session.query(ClsModel)
            .join(JobModel, ClsModel.refnr == JobModel.refnr)
            .filter(ClsModel.role == role.slug, JobModel.closed_at.is_(None))
            .all()
        )

    if not rows:
        return {}

    seen: set[tuple[str, str]] = set()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        meta = cls_to_meta(row)
        key = (meta.get("titel") or "", meta.get("firma") or "")
        if key not in seen:
            seen.add(key)
            result[row.refnr] = meta
    return result


def _group_by_stage(classifications: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {s: [] for s in STAGES}
    for refnr, meta in classifications.items():
        if meta.get("company_type") == "product":
            stage = meta.get("company_stage", "")
            if stage in groups:
                groups[stage].append(refnr)
            else:
                groups.setdefault("other", []).append(refnr)
    return groups


def build_skills_df(
    groups: dict[str, list[str]],
    descriptions: dict[str, str],
    skills: list[tuple[str, str]],
) -> pd.DataFrame:
    all_refnrs = [r for stage in STAGES for r in groups[stage]]
    rows: list[dict[str, Any]] = []
    for name, pattern in skills:
        row: dict[str, Any] = {"skill": name}
        for stage in STAGES:
            n = sum(
                1 for r in groups[stage]
                if r in descriptions and re.search(pattern, descriptions[r], re.IGNORECASE)
            )
            row[stage] = n
            row[f"{stage}_pct"] = n / len(groups[stage]) * 100 if groups[stage] else 0
        n_all = sum(
            1 for r in all_refnrs
            if r in descriptions and re.search(pattern, descriptions[r], re.IGNORECASE)
        )
        row["all"] = n_all
        row["all_pct"] = n_all / len(all_refnrs) * 100 if all_refnrs else 0
        rows.append(row)
    return pd.DataFrame(rows).set_index("skill").sort_values("all_pct", ascending=False)


def build_geo_df(
    groups: dict[str, list[str]],
    classifications: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for stage in STAGES:
        for refnr in groups[stage]:
            raw = classifications[refnr].get("region", "")
            region = REGION_NAMES.get(raw, raw or "Unknown")
            counts[region][stage] += 1
    rows = [
        {"region": r, **{s: counts[r].get(s, 0) for s in STAGES}}
        for r in counts
    ]
    df = pd.DataFrame(rows).set_index("region")
    df["total"] = df[STAGES].sum(axis=1)
    return df.sort_values("total", ascending=False)


def chart_top_skills(df: pd.DataFrame, totals: dict[str, int]) -> str:
    top = df.head(TOP_N)
    fig = go.Figure(go.Bar(
        y=top.index.tolist(),
        x=top["all_pct"].tolist(),
        orientation="h",
        marker_color="#3b7dd8",
        text=[f"{v:.0f}%" for v in top["all_pct"]],
        textposition="outside",
        cliponaxis=False,
    ))
    fig.update_layout(
        height=max(320, TOP_N * 26 + 80),
        margin=dict(l=0, r=60, t=30, b=10),
        title=dict(text=f"Top {TOP_N} skills — all product companies (n={totals['all']})", font=dict(size=13)),
        xaxis=dict(title="% of jobs", range=[0, 115], gridcolor=_GRID),
        yaxis=dict(autorange="reversed"),
        showlegend=False,
        font=_FONT, **_BG,
    )
    return _html(fig)


def chart_heatmap(df: pd.DataFrame, totals: dict[str, int]) -> str:
    top = df.head(TOP_N)
    col_labels = [f"{STAGE_LABELS[s]} (n={totals[s]})" for s in STAGES]
    z = top[[f"{s}_pct" for s in STAGES]].values
    text = [[f"{v:.0f}" for v in row] for row in z]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=col_labels,
        y=top.index.tolist(),
        colorscale="YlOrRd",
        zmin=0, zmax=100,
        text=text, texttemplate="%{text}",
        hoverongaps=False,
        colorbar=dict(title="%", thickness=12, len=0.8),
    ))
    fig.update_layout(
        height=max(380, TOP_N * 22 + 100),
        margin=dict(l=0, r=30, t=30, b=20),
        title=dict(text=f"Skills by company stage — top {TOP_N}", font=dict(size=13)),
        xaxis=dict(tickangle=0),
        yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
        font=_FONT, **_BG,
    )
    return _html(fig)


def chart_geography(geo_df: pd.DataFrame) -> str:
    fig = go.Figure()
    for stage in STAGES:
        fig.add_trace(go.Bar(
            name=STAGE_LABELS[stage],
            y=geo_df.index.tolist(),
            x=geo_df[stage].tolist(),
            orientation="h",
            marker_color=STAGE_COLORS[stage],
        ))
    fig.update_layout(
        barmode="stack",
        height=max(300, len(geo_df) * 24 + 80),
        margin=dict(l=0, r=30, t=30, b=10),
        title=dict(text="Geography of product jobs", font=dict(size=13)),
        xaxis=dict(title="Jobs", gridcolor=_GRID),
        yaxis=dict(autorange="reversed"),
        legend=dict(orientation="h", y=1.06, x=0),
        font=_FONT, **_BG,
    )
    return _html(fig)


def render_html(
    charts: dict[str, str],
    totals: dict[str, int],
    tables: dict[str, str] | None = None,
    role_name: str = "",
) -> str:
    body = render_template(
        "skills_body.html",
        charts=charts,
        totals=totals,
        tables=tables or {},
        top_n=TOP_N,
    )
    return page_shell("Skills Dashboard", body, "skills", role_name=role_name)


def run(role: Role | None = None) -> str | None:
    if role is None:
        role = ROLES[DEFAULT_ROLE]

    logger.info("Building skills dashboard...")

    classifications = _load_classifications(role)
    if not classifications:
        logger.error("No classifications in DB. Run classify first.")
        return None

    ensure_plotly_js(REPORTS_DIR)

    groups = _group_by_stage(classifications)
    totals: dict[str, int] = {s: len(groups[s]) for s in STAGES}
    totals["all"] = sum(len(v) for v in groups.values())

    logger.debug("Loading descriptions...")
    descriptions = load_descriptions(classifications, role)

    logger.debug("Building dataframes...")
    skills_df = build_skills_df(groups, descriptions, role.skills)
    geo_df = build_geo_df(groups, classifications)

    logger.debug("Rendering charts...")
    charts: dict[str, str] = {
        "top_skills": chart_top_skills(skills_df, totals),
        "heatmap":    chart_heatmap(skills_df, totals),
        "geography":  chart_geography(geo_df),
    }
    tables: dict[str, str] = {
        "skills": skills_table_html(groups, descriptions, role.skills),
        "geo":    geography_table_html(groups, classifications),
    }

    if role.practices:
        practices_df = build_skills_df(groups, descriptions, role.practices)
        charts["practices"] = chart_top_skills(practices_df, totals)
        tables["practices"] = skills_table_html(groups, descriptions, role.practices)

    html = render_html(charts, totals, tables=tables, role_name=role.slug)
    logger.info("Rendered skills dashboard")
    return html
