"""Interactive dashboard modules.

Each module generates one or more HTML/txt dashboards in dashboards/.

Modules
-------
- analysis  : market stats — skill frequencies, company counts (txt + html)
- skills    : Skills Dashboard — top skills, heatmap, geography (html)
- cv        : CV Dashboard — gap analysis and job recommendations (txt + html)
- listings  : Listings Dashboard — all jobs grouped by ATS platform (html)
- charts    : shared chart helpers (used by cv)
- _render   : job card HTML renderer (used by cv and listings)
"""

from loguru import logger

from jobfit.config import REPORTS_DIR
from jobfit.dashboards import analysis, cv, skills, listings, targets
from jobfit.roles import Role

__all__ = ["analysis", "cv", "skills", "listings", "targets", "run_analyze", "run_cmd", "print_links"]

_FILES = [
    ("CV Dashboard",      "cv_gap_analysis.html"),
    ("Listings",          "listings.html"),
    ("Skills",            "product_skills_chart.html"),
    ("Target Companies",  "target_companies.html"),
]

_TARGETS: dict[str, set[str]] = {
    "all":      {"cv_gap_analysis.html", "listings.html", "product_skills_chart.html", "target_companies.html"},
    "cv":       {"cv_gap_analysis.html"},
    "listings": {"listings.html"},
    "analyze":  {"product_skills_chart.html"},
    "targets":  {"target_companies.html"},
}


def print_links(target: str = "all") -> None:
    """Log file:// links for dashboards relevant to the given target."""
    relevant = _TARGETS.get(target, _TARGETS["all"])
    visible = [
        (label, (REPORTS_DIR / fname).resolve())
        for label, fname in _FILES
        if fname in relevant and (REPORTS_DIR / fname).exists()
    ]
    if not visible:
        return
    logger.info("\nDashboards:")
    for label, path in visible:
        logger.info(f"  {label:<16} file://{path}")


def run_cmd(target: str, role: "Role | None" = None) -> None:
    """Build dashboards for the given target."""
    logger.info(f"Building dashboards ({target})...")
    if target in ("all", "analyze"):
        run_analyze(role)
    if target in ("all", "cv"):
        cv.save(role)
    if target in ("all", "listings"):
        listings.save(role)
    if target in ("all", "targets"):
        targets.save(role)
    print_links(target)


def run_analyze(role: "Role | None" = None) -> None:
    """Run market analysis: stats report + skills charts."""
    analysis.run(role)
    from jobfit.dashboards.skills import OUTPUT_HTML as SKILLS_HTML
    SKILLS_HTML.parent.mkdir(exist_ok=True)
    SKILLS_HTML.write_text(skills.run(role), encoding="utf-8")
