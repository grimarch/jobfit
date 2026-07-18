"""Full sync orchestration: fetch → mark-closed → enrich → dashboards."""

import argparse

from loguru import logger

from jobfit import brands, classify, dashboards, enrich, fetchers, mark_closed
from jobfit.roles import ROLES

_ns = argparse.Namespace


def _fetch_and_close(role_slug: str) -> None:
    role_obj = ROLES[role_slug]
    fetch_args = _ns(
        role_obj=role_obj, dry_run=False, force_refresh=False,
        days=60, ats=None, stats_out=None,
    )
    fetchers.run_all(fetch_args)
    mark_closed.run(_ns(role_obj=role_obj, dry_run=False))


def run(role_slug: str) -> None:
    """Local full cycle: fetch → mark-closed → enrich → dashboards."""
    role_obj = ROLES[role_slug]
    _fetch_and_close(role_slug)
    enrich.run(role_obj)
    dashboards.run_analyze(role_obj)
    dashboards.cv.save(role_obj)
    dashboards.listings.save(role_obj)
    dashboards.targets.save(role_obj)
    unclassified = classify.unclassified_count(role_slug)
    if unclassified:
        logger.warning(f"⚠  {unclassified} unclassified jobs — run: jobfit classify --role {role_slug}")
    if not brands.has_any(role_slug):
        logger.warning(f"⚠  no known brands — run: jobfit brands --role {role_slug}")
    dashboards.print_links("all")


def run_for_serve(role_slug: str) -> None:
    """Serve-triggered cycle: fetch → mark-closed (server rebuilds dashboards via cache)."""
    _fetch_and_close(role_slug)
    unclassified = classify.unclassified_count(role_slug)
    if unclassified:
        logger.warning(f"⚠  {unclassified} unclassified jobs — run: jobfit classify --role {role_slug}")
