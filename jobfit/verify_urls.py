"""Verify active ATS job URLs are still reachable.

Makes HEAD requests in parallel; jobs returning 404 or 410 are marked
closed (closed_at = now) in the DB. WttJ checked via public UUID API
(WAF blocks HTTP). EURES skipped.
"""

import argparse
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from loguru import logger
from tqdm import tqdm

from jobfit.roles import DEFAULT_ROLE, ROLES, Role

_WTTJ_API = "https://api.welcometothejungle.com/api/v1/jobs/{uuid}"
_WAF_SKIP = {"eures"}   # truly undetectable: SPA returns 200 for all
_DEAD_STATUSES = {404, 410}
_TIMEOUT = 10
_WORKERS = 20
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _check_url(url: str) -> int | None:
    try:
        req = Request(url, method="HEAD", headers={"User-Agent": _UA})
        with urlopen(req, timeout=_TIMEOUT) as r:
            return r.status
    except HTTPError as e:
        return e.code
    except (URLError, Exception):
        return None


def _check_wttj(uuid: str) -> bool:
    """Return True if job is dead (UUID not found or unpublished)."""
    try:
        req = Request(_WTTJ_API.format(uuid=uuid), headers={"Accept": "application/json"})
        with urlopen(req, timeout=_TIMEOUT) as r:
            data = json.loads(r.read())
        org = data.get("website_organization_slug", "")
        job_slug = data.get("job_slug", "")
        if not org or not job_slug:
            return True
        # Check full job object for unpublished/archived status
        req2 = Request(
            f"https://api.welcometothejungle.com/api/v1/organizations/{org}/jobs/{job_slug}",
            headers={"Accept": "application/json"},
        )
        with urlopen(req2, timeout=_TIMEOUT) as r2:
            full = json.loads(r2.read())
        job = full.get("job", {})
        if job.get("archived_at") or job.get("unpublished_at"):
            return True
        if job.get("status") not in ("published", None):
            return True
        return False
    except HTTPError as e:
        return e.code == 404
    except (URLError, Exception):
        return False  # network error → don't close


def _fetch_open_ats_jobs(role: Role) -> list[Any]:
    from jobfit.db import get_session
    from jobfit.db.models import Job as JobModel, Classification as ClsModel

    with get_session() as session:
        return (
            session.query(JobModel, ClsModel)
            .outerjoin(ClsModel, JobModel.refnr == ClsModel.refnr)
            .filter(
                JobModel.role == role.slug,
                JobModel.refnr.like("ats-%"),
                JobModel.closed_at.is_(None),
            )
            .all()
        )


def _categorize_jobs(
    rows: list[Any],
) -> tuple[dict[str, tuple[str, str, str]], dict[str, tuple[str, str, str]], int]:
    """Split rows into HTTP-checkable, WttJ-API-checkable, and skipped."""
    to_check: dict[str, tuple[str, str, str]] = {}
    wttj_check: dict[str, tuple[str, str, str]] = {}
    skipped = 0

    for job_row, cls_row in rows:
        ats_source = job_row.ats_source or ""
        firma = (cls_row.firma if cls_row else None) or job_row.firma or ""
        titel = (cls_row.titel if cls_row else None) or job_row.titel or ""

        if ats_source in _WAF_SKIP:
            skipped += 1
            continue
        if ats_source == "welcometothejungle":
            uuid = job_row.refnr.replace("ats-welcometothejungle-", "")
            wttj_check[job_row.refnr] = (uuid, firma, titel)
            continue
        url = job_row.externe_url or ""
        if url:
            to_check[job_row.refnr] = (url, firma, titel)

    return to_check, wttj_check, skipped


def _run_checks(
    to_check: dict[str, tuple[str, str, str]],
    wttj_check: dict[str, tuple[str, str, str]],
) -> tuple[list[str], int]:
    """Submit parallel URL/API checks; return (dead_refnrs, n_errors)."""
    dead: list[str] = []
    n_errors = 0

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures: dict[Future[Any], tuple[str, str]] = {}
        for refnr, (url, _, _) in to_check.items():
            futures[pool.submit(_check_url, url)] = ("http", refnr)
        for refnr, (uuid, _, _) in wttj_check.items():
            futures[pool.submit(_check_wttj, uuid)] = ("wttj", refnr)

        with tqdm(total=len(futures), unit="url", desc="Verify URLs") as bar:
            for future in as_completed(futures):
                kind, refnr = futures[future]
                if kind == "http":
                    url, firma, titel = to_check[refnr]
                    try:
                        code = future.result()
                    except Exception:
                        code = None
                    if code in _DEAD_STATUSES:
                        logger.info(f"DEAD {code} | {firma} | {titel}")
                        dead.append(refnr)
                    elif code is None:
                        n_errors += 1
                        logger.debug(f"timeout/error | {url}")
                else:
                    _, firma, titel = wttj_check[refnr]
                    try:
                        is_dead = future.result()
                    except Exception:
                        is_dead = False
                    if is_dead:
                        logger.info(f"DEAD (WttJ API) | {firma} | {titel}")
                        dead.append(refnr)
                bar.update(1)

    return dead, n_errors


def _mark_closed(dead: list[str], now: datetime) -> None:
    from jobfit.db import get_session
    from jobfit.db.models import Job as JobModel

    with get_session() as session:
        for refnr in dead:
            job = session.get(JobModel, refnr)
            if job:
                job.closed_at = now


def run(args: argparse.Namespace) -> None:
    role: Role = getattr(args, "role_obj", ROLES[DEFAULT_ROLE])
    dry_run: bool = getattr(args, "dry_run", False)
    now = datetime.now()

    rows = _fetch_open_ats_jobs(role)
    to_check, wttj_check, skipped = _categorize_jobs(rows)

    logger.info(
        f"Checking {len(to_check)} URLs + {len(wttj_check)} WttJ via API  |  skipped: {skipped}"
    )

    dead, n_errors = _run_checks(to_check, wttj_check)

    if not dry_run and dead:
        _mark_closed(dead, now)

    suffix = " (dry-run)" if dry_run else ""
    logger.info(
        f"verify-urls done{suffix}: "
        f"{len(dead)} dead → closed, "
        f"{n_errors} timeout/error (skipped), "
        f"{skipped} skipped (eures)"
    )
