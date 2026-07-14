"""Plotly chart helpers — return self-contained HTML div snippets."""

import numpy as np
import plotly.graph_objects as go

_FONT = dict(family="system-ui,-apple-system,sans-serif", size=12)
_BG = dict(plot_bgcolor="white", paper_bgcolor="white")
_GRID = "#eef0f5"
_CFG = {"responsive": True, "displayModeBar": True, "displaylogo": False}


def _html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, config=_CFG)


def chart_gap(
    gaps: list[tuple[str, float]],
    strengths: list[tuple[str, float]],
    subtitle: str = "",
) -> str:
    """Horizontal bar: red gaps (ascending) + green strengths (ascending)."""
    g = sorted(gaps, key=lambda x: -x[1])
    s = sorted(strengths, key=lambda x: -x[1])

    fig = go.Figure()
    if g:
        fig.add_trace(go.Bar(
            y=[n for n, _ in g], x=[p for _, p in g],
            orientation="h", name="Gap", marker_color="#d04444",
            text=[f"{p:.0f}%" for _, p in g], textposition="outside",
            cliponaxis=False,
        ))
    if s:
        fig.add_trace(go.Bar(
            y=[n for n, _ in s], x=[p for _, p in s],
            orientation="h", name="Strength", marker_color="#27a269",
            text=[f"{p:.0f}%" for _, p in s], textposition="outside",
            cliponaxis=False,
        ))

    height = max(280, (len(g) + len(s)) * 24 + 80)
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=70, t=30, b=10),
        xaxis=dict(title="% of jobs", range=[0, 115], gridcolor=_GRID),
        yaxis=dict(autorange="reversed"),
        legend=dict(orientation="h", y=1.06, x=0),
        barmode="overlay",
        font=_FONT, **_BG,
    )
    return _html(fig)


def chart_priority_gaps(priority_gaps: list[tuple[str, int]], top_n: int) -> str:
    """Horizontal bar: missing skills by frequency in top-N jobs."""
    if not priority_gaps:
        return "<p style='color:#6b7a95;font-size:13px'>No data</p>"

    sorted_pg = sorted(priority_gaps, key=lambda x: x[1])
    names = [n for n, _ in sorted_pg]
    counts = [c for _, c in sorted_pg]

    fig = go.Figure(go.Bar(
        y=names, x=counts, orientation="h",
        marker_color="#7c3fd0",
        text=[f"{c}/{top_n}" for c in counts], textposition="outside",
        cliponaxis=False,
    ))
    height = max(220, len(names) * 24 + 80)
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=60, t=20, b=10),
        xaxis=dict(title=f"of {top_n} jobs", range=[0, top_n * 1.25], gridcolor=_GRID),
        yaxis=dict(autorange="reversed"),
        showlegend=False,
        font=_FONT, **_BG,
    )
    return _html(fig)


def chart_similarity_hist(sims: np.ndarray, threshold: float) -> str:
    """Histogram of cosine similarities with threshold line."""
    covered = int((sims >= threshold).sum())

    fig = go.Figure(go.Histogram(
        x=sims, nbinsx=20,
        xbins=dict(start=0, end=1, size=0.05),
        marker_color="#3b7dd8", opacity=0.75,
    ))
    fig.add_vline(
        x=threshold, line_dash="dash", line_color="#d04444", line_width=2,
        annotation_text=f"threshold {threshold}  ({covered}/{len(sims)})",
        annotation_position="top right",
        annotation_font_color="#d04444",
    )
    fig.update_layout(
        height=240,
        margin=dict(l=0, r=20, t=30, b=40),
        xaxis=dict(title="Cosine similarity", range=[0, 1], gridcolor=_GRID),
        yaxis=dict(title="Jobs", gridcolor=_GRID),
        showlegend=False,
        font=_FONT, **_BG,
    )
    return _html(fig)


def chart_cooccurrence(
    matrix: np.ndarray, skill_names: list[str], top_n: int = 22
) -> str:
    """Skill co-occurrence heatmap: P(col | row) × 100."""
    freq = matrix.mean(axis=0)
    top_idx = freq.argsort()[::-1][:top_n]
    top_names = [skill_names[i] for i in top_idx]
    sub = matrix[:, top_idx]

    counts = sub.T @ sub
    totals = sub.sum(axis=0)
    with np.errstate(invalid="ignore"):
        cooc = np.where(totals[:, None] > 0, counts / totals[:, None] * 100, 0.0)
    np.fill_diagonal(cooc, None)  # type: ignore[call-overload]

    text = [[f"{v:.0f}" if v is not None else "" for v in row] for row in cooc]

    fig = go.Figure(go.Heatmap(
        z=cooc, x=top_names, y=top_names,
        colorscale="YlOrRd", zmin=0, zmax=100,
        text=text, texttemplate="%{text}",
        hoverongaps=False,
        colorbar=dict(title="%", thickness=12, len=0.8),
    ))
    fig.update_layout(
        height=580,
        margin=dict(l=0, r=30, t=20, b=110),
        xaxis=dict(tickangle=45, tickfont=dict(size=10)),
        yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
        font=_FONT, **_BG,
    )
    return _html(fig)
