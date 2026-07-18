"""Shared HTML rendering helpers for job cards, badges, and page layout."""

import shutil
from pathlib import Path
from typing import Any

import jinja2
from loguru import logger

_CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2", "native"]


def _cefr_rank(level: str | None) -> int:
    try:
        return _CEFR_ORDER.index(level) if level else -1
    except ValueError:
        return -1


_SENIORITY_ORDER = ["junior", "mid", "senior", "lead"]


def _seniority_rank(s: str | None) -> int:
    try:
        return _SENIORITY_ORDER.index(s) if s else -1
    except ValueError:
        return -1


_EDU_ORDER = ["ausbildung", "bachelor", "master", "phd"]


def _edu_rank(e: str | None) -> int:
    try:
        return _EDU_ORDER.index(e) if e else -1
    except ValueError:
        return -1


def profile_dim_badges(job: dict[str, Any], profile: dict[str, Any]) -> str:
    """Return HTML badges showing profile match on non-skill dimensions."""
    parts: list[str] = []

    def badge(text: str, ok: bool | None) -> str:
        if ok is True:
            st = "background:#e8f5e9;color:#2e7d32"
        elif ok is False:
            st = "background:#ffebee;color:#c62828"
        else:
            st = "background:#f5f5f5;color:#9e9e9e"
        return f'<span style="{st};border-radius:4px;padding:1px 6px;font-size:0.78rem">{text}</span>'

    # Experience
    req_exp = job.get("experience_years_min")
    my_exp = profile.get("experience_years")
    if req_exp is not None and my_exp is not None:
        ok = my_exp >= req_exp
        parts.append(badge(f"exp: {req_exp}y", ok))
    elif req_exp is not None:
        parts.append(badge(f"exp: {req_exp}y", None))

    # Seniority
    req_sen = job.get("seniority")
    my_sen = profile.get("seniority")
    if req_sen and my_sen and req_sen not in ("mid", "unknown"):
        ok = _seniority_rank(my_sen) >= _seniority_rank(req_sen)
        parts.append(badge(req_sen, ok))

    # Education
    req_edu = job.get("education_required")
    my_edu = profile.get("education")
    if req_edu and req_edu != "unknown":
        ok = (_edu_rank(my_edu) >= _edu_rank(req_edu)) if my_edu else None
        parts.append(badge(req_edu, ok))

    # Missing certifications
    req_certs: list[str] = job.get("certifications_required") or []
    my_certs: set[str] = set(profile.get("certifications") or [])
    for cert in req_certs:
        parts.append(badge(cert, cert in my_certs))

    return " ".join(parts)


def job_url(refnr: str, externe_url: str = "") -> str:
    if externe_url:
        return externe_url
    return f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"


def job_source_label(ats_source: str, ats_slug: str) -> str:
    if not ats_source:
        return "BA"
    _ABBR = {
        "greenhouse": "GH", "lever": "Lever", "smartrecruiters": "SR",
        "ashby": "Ashby", "workable": "Workable",
        "germantechjobs": "GTJ", "berlinstartupjobs": "BSJ", "adzuna": "Adzuna",
        "devopsjobs": "DOJ", "devitjobs": "DevIT", "landingjobs": "Landing", "echojobs": "Echo",
    }
    abbr = _ABBR.get(ats_source, ats_source)
    if not ats_slug:
        return abbr
    return f"{abbr}/{ats_slug}"


def tags_html(skills: list[str], color: str) -> str:
    style = f"background:{color};color:#fff;padding:2px 8px;border-radius:10px;font-size:0.8rem;white-space:nowrap"
    return " ".join(f'<span style="{style}">{s}</span>' for s in skills)


_STAGE_STYLE = {
    "startup":     "background:#e8f5e9;color:#2e7d32",
    "mittelstand": "background:#e3f2fd;color:#1565c0",
    "enterprise":  "background:#f3e5f5;color:#6a1b9a",
}

_MODE_STYLE = {
    "remote": "background:#e8f5e9;color:#2e7d32",
    "hybrid": "background:#e3f2fd;color:#1565c0",
    "onsite": "background:#f3e5f5;color:#6a1b9a",
}
_DE_STYLE = {
    "C2": "background:#ffebee;color:#c62828",
    "C1": "background:#fff3e0;color:#e65100",
    "B2": "background:#fff8e1;color:#f57f17",
    "B1": "background:#f9fbe7;color:#827717",
    "required": "background:#fce4ec;color:#ad1457",
}

def _job_card_html(job: dict[str, Any], profile: dict[str, Any] | None = None) -> str:
    matched_html = tags_html(job["matched"], "#27ae60")
    missing_html = tags_html(job["missing"], "#c0392b") if job["missing"] else ""
    src = job.get("source", "BA")
    src_st = "background:#f5f5f5;color:#616161" if src == "BA" else "background:#e3f2fd;color:#1565c0"
    src_title = src.split("/")[1] if "/" in src else ""
    src_label = src.split("/")[0] if "/" in src else src
    s_min, s_max = job.get("salary_min"), job.get("salary_max")
    salary_str = f"€{s_min // 1000}k–{s_max // 1000}k" if s_max else f"€{s_min // 1000}k" if s_min is not None else ""
    dim_html = profile_dim_badges(job, profile) if profile else ""
    return render_template(
        "job_card.html",
        job=job,
        matched_html=matched_html,
        missing_html=missing_html,
        src_st=src_st,
        src_title=src_title,
        src_label=src_label,
        salary_str=salary_str,
        dim_html=dim_html,
    )


# ── Page shell system ──────────────────────────────────────────────────────────

def ensure_plotly_js(reports_dir: Path) -> None:
    """Copy plotly.min.js from package data into reports_dir (once)."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    dest = reports_dir / "plotly.min.js"
    if not dest.exists():
        try:
            import plotly as _p
            src = Path(_p.__file__).parent / "package_data" / "plotly.min.js"
            if src.exists():
                shutil.copy(src, dest)
                return
        except Exception:
            pass
        logger.warning("plotly.min.js not found in package — charts need internet (CDN fallback).")


_STATIC = Path(__file__).parent / "static"
_SHARED_CSS = (_STATIC / "dashboard.css").read_text()
_SHARED_JS = (_STATIC / "dashboard.js").read_text()

_TEMPLATES = Path(__file__).parent / "templates"
_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATES)),
    autoescape=False,
    keep_trailing_newline=True,
)
_ENV.globals.update({
    "STAGE_STYLE": _STAGE_STYLE,
    "MODE_STYLE":  _MODE_STYLE,
    "DE_STYLE":    _DE_STYLE,
})

_NAV_ITEMS = [
    ("cv",       "◎", "CV Analysis",     "/cv"),
    ("listings", "☰", "Listings",         "/listings"),
    ("skills",   "◈", "Skills Market",    "/skills"),
    ("targets",  "◆", "Target Companies", "/"),
]


def render_template(name: str, **kwargs: Any) -> str:
    """Render a template from the dashboards/templates/ directory."""
    return _ENV.get_template(name).render(**kwargs)


def drawer_panel(panel_id: str, title: str, subtitle: str, body: str) -> str:
    """Render a drawer panel (hidden by default, opened via openDrawer())."""
    return render_template("drawer.html", panel_id=panel_id, title=title, subtitle=subtitle, body=body)


def page_shell(
    title: str,
    body: str,
    active_page: str,
    role_name: str = "",
    drawers: str = "",
    extra_js: str = "",
) -> str:
    """Full HTML document with sidebar, shared CSS/JS, and optional drawers."""
    return render_template(
        "page.html",
        title=title,
        body=body,
        active_page=active_page,
        role_name=role_name,
        drawers=drawers,
        extra_js=extra_js,
        nav_items=_NAV_ITEMS,
        css=_SHARED_CSS,
        shared_js=_SHARED_JS,
    )
