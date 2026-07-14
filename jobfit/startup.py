"""Startup prerequisites: verify DB state before server boot or CV dashboard build."""

from __future__ import annotations

import sys

from loguru import logger

from jobfit.roles import DEFAULT_ROLE, ROLES, Role


def _raise_not_ready(
    slug: str,
    *,
    job_count: int,
    unclassified: int,
    product_refnrs: list[str],
    valid_refnrs: list[str],
) -> None:
    if valid_refnrs:
        return

    if job_count == 0:
        raise RuntimeError(
            f"No jobs in DB for role '{slug}'. "
            f"Run: jobfit serve sync  (or jobfit sync --role {slug})"
        )

    if unclassified > 0:
        raise RuntimeError(
            f"{unclassified} job(s) not classified for role '{slug}'. "
            f"Run: jobfit classify --role {slug}"
        )

    if not product_refnrs:
        raise RuntimeError(
            f"No product company jobs for role '{slug}'. "
            f"Re-run classify or fetch more jobs: jobfit classify --role {slug}"
        )

    raise RuntimeError(
        f"Product jobs found for role '{slug}' but descriptions are missing. "
        f"Run: jobfit serve sync  (or jobfit fetch all --role {slug})"
    )


def load_product_job_refs(role: Role) -> tuple[list[str], list[str]]:
    """Return (product_refnrs, valid_refnrs) using the same dedup rules as the CV dashboard."""
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel, Job as JobModel

    product_refnrs: list[str] = []
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
        if cls_row.company_type == "product":
            refnr = job_row.refnr
            product_refnrs.append(refnr)
            descriptions[refnr] = job_row.beschreibung or ""

    valid_refnrs = [r for r in product_refnrs if r in descriptions]
    return product_refnrs, valid_refnrs


def require_product_jobs(
    role: Role,
    product_refnrs: list[str],
    valid_refnrs: list[str],
) -> None:
    """Raise RuntimeError with actionable setup instructions when CV data is missing."""
    if valid_refnrs:
        return

    from jobfit.classify import unclassified_count
    from jobfit.db import get_session
    from jobfit.db.models import Job as JobModel

    slug = role.slug
    with get_session() as session:
        job_count = (
            session.query(JobModel)
            .filter(JobModel.role == slug, JobModel.closed_at.is_(None))
            .count()
        )

    if job_count == 0:
        _raise_not_ready(
            slug,
            job_count=0,
            unclassified=0,
            product_refnrs=product_refnrs,
            valid_refnrs=valid_refnrs,
        )

    _raise_not_ready(
        slug,
        job_count=job_count,
        unclassified=unclassified_count(slug),
        product_refnrs=product_refnrs,
        valid_refnrs=valid_refnrs,
    )


def check_startup(role_slug: str = DEFAULT_ROLE) -> None:
    """Verify DB has classified product jobs before building dashboards."""
    role = ROLES.get(role_slug) or ROLES[DEFAULT_ROLE]
    product_refnrs, valid_refnrs = load_product_job_refs(role)
    require_product_jobs(role, product_refnrs, valid_refnrs)


def main() -> None:
    role_slug = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROLE
    try:
        check_startup(role_slug)
    except RuntimeError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
