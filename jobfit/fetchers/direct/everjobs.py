"""Fetch DE jobs via self-hosted Ever Jobs API.

Sources covered (configured in EVERJOBS_SOURCES):
  - germantechjobs  : RSS, Germany-only tech jobs, includes salary data
  - berlinstartupjobs: RSS, Berlin startup ecosystem
  - adzuna          : official REST API, requires ADZUNA_APP_ID + ADZUNA_APP_KEY env vars

Prerequisites:
  Run the ever-jobs sidecar: ghcr.io/ever-jobs/ever-jobs:latest (port 3001).
  Set EVERJOBS_URL in env (default: http://localhost:3001).
  For Adzuna: set ADZUNA_APP_ID and ADZUNA_APP_KEY in ever-jobs environment.
"""

import argparse
import json
import os
import re
from datetime import datetime
from typing import Any

from loguru import logger

from jobfit.config import DE_CITIES_RE, DE_RE, RAW_DIR
from jobfit.db import get_session
from jobfit.db.models import Job
from jobfit.fetchers.direct._http import post_json
from jobfit.roles import DEFAULT_ROLE, ROLES, Role

_ATS_SEEN_FILE = RAW_DIR / "ats_seen.json"

# ever-jobs siteType identifiers for sources without ToS risks
EVERJOBS_SOURCES = [
    "germantechjobs",  # RSS, Germany-only tech jobs, salary data
    "berlinstartupjobs",  # RSS, Berlin startup ecosystem
    "devopsjobs",  # RSS, global DevOps/infra — geo-filtered post-fetch
    "devitjobs",  # XML, Europe IT/dev, salary data — geo-filtered post-fetch
    "landingjobs",  # REST, Europe tech + relocation — geo-filtered post-fetch
    "echojobs",  # REST, curated global tech — geo-filtered post-fetch
    "hackernews",  #
    "hackerone",  #
]

# Search terms per role — maps to title_re alternatives in each role definition
_SEARCH_TERMS_BY_ROLE: dict[str, list[str]] = {
    "devops": [
        "DevOps Engineer",
        "Platform Engineer",
        "Site Reliability Engineer",
        "Cloud Engineer",
        "Infrastructure Engineer",
    ],
}
_DEFAULT_SEARCH_TERMS = ["DevOps Engineer"]

_RESULTS_PER_SITE = 50
_HOURS_OLD = 60 * 24  # 60 days, matches BA default

_PERIOD_MAP: dict[str, str] = {
    "yearly": "YEAR",
    "monthly": "MONTH",
    "hourly": "HOUR",
    "weekly": "MONTH",
}

# These RSS sources are Germany-only by definition — skip geo check
_DE_ONLY_SOURCES = {"germantechjobs", "berlinstartupjobs"}

# GermanTechJobs title format: "Job Title - City @ Company [salary]"
_CITY_FROM_TITLE_RE = re.compile(r"\)\s*-\s*([^@()\[\]]+?)\s*@")


def _everjobs_url() -> str:
    return os.environ.get("EVERJOBS_URL", "http://localhost:3001").rstrip("/")


def _is_germany(raw: dict[str, Any]) -> bool:
    if raw.get("site") in _DE_ONLY_SOURCES:
        return True
    loc = raw.get("location") or {}
    country = (loc.get("country") or "").lower()
    if country in ("germany", "deutschland", "de", "deu"):
        return True
    city = loc.get("city") or ""
    return bool(DE_RE.search(country) or DE_CITIES_RE.search(city))


def _to_job(raw: dict[str, Any], role_slug: str, now: datetime) -> Job:
    site = raw.get("site", "unknown")
    job_id = raw.get("id", "")

    comp: dict[str, Any] = raw.get("compensation") or {}
    loc: dict[str, Any] = raw.get("location") or {}
    city: str = loc.get("city") or ""
    state: str = loc.get("state") or ""
    # Fallback: extract city from GermanTechJobs title format "Title - City @ Company"
    if not city:
        m = _CITY_FROM_TITLE_RE.search(raw.get("title", ""))
        if m:
            city = m.group(1).strip()
    ort = ", ".join(filter(None, [city, state]))

    job_types: list[str] = raw.get("jobType") or []
    vollzeit = "parttime" not in [t.lower() for t in job_types] if job_types else True

    period_raw: str = str(comp.get("interval") or "")

    return Job(
        refnr=f"everjobs-{job_id}",
        role=role_slug,
        titel=raw.get("title", ""),
        beschreibung=raw.get("description", ""),
        firma=raw.get("companyName", ""),
        externe_url=raw.get("jobUrl", ""),
        partner_name=f"everjobs/{site}",
        ort_raw=ort,
        vollzeit=vollzeit,
        ats_source=site,
        ats_slug=None,
        via="everjobs",
        salary_min_raw=comp.get("minAmount"),
        salary_max_raw=comp.get("maxAmount"),
        salary_currency=comp.get("currency"),
        salary_period=_PERIOD_MAP.get(period_raw),
        salary_summary=None,
        fetched_at=now,
    )


def _search(base_url: str, term: str) -> list[dict[str, Any]]:
    payload = {
        "searchTerm": term,
        "location": "Germany",
        "siteType": EVERJOBS_SOURCES,
        "resultsWanted": _RESULTS_PER_SITE,
        "hoursOld": _HOURS_OLD,
        "descriptionFormat": "markdown",
        "enforceAnnualSalary": True,
    }
    try:
        resp = post_json(f"{base_url}/api/jobs/search", payload, timeout=120)
        return resp.get("jobs", []) if isinstance(resp, dict) else []
    except Exception as exc:
        logger.warning(f"[everjobs] search '{term}' failed: {exc}")
        return []


def run(args: argparse.Namespace) -> None:
    role: Role = getattr(args, "role_obj", ROLES[DEFAULT_ROLE])
    dry_run = getattr(args, "dry_run", False)

    base_url = _everjobs_url()
    search_terms = _SEARCH_TERMS_BY_ROLE.get(role.slug, _DEFAULT_SEARCH_TERMS)

    with get_session() as session:
        known: set[str] = {
            r for (r,) in session.query(Job.refnr).filter(Job.role == role.slug)
        }

    # Deduplicate across search terms by refnr
    seen_ids: set[str] = set()
    all_raw: list[dict] = []
    for term in search_terms:
        jobs = _search(base_url, term)
        for raw in jobs:
            rid = f"everjobs-{raw.get('site', '')}-{raw.get('id', '')}"
            if rid not in seen_ids:
                seen_ids.add(rid)
                all_raw.append(raw)
        logger.info(f"[everjobs] '{term}': {len(jobs)} raw results")

    now = datetime.now()
    matched = []
    for raw in all_raw:
        geo_ok = _is_germany(raw)
        title_ok = bool(role.title_re.search(raw.get("title", "")))
        if geo_ok and title_ok:
            matched.append(_to_job(raw, role.slug, now))
        else:
            logger.debug(
                f"[everjobs] skip site={raw.get('site')} geo={geo_ok} title={title_ok} "
                f"loc={raw.get('location')} | {raw.get('title', '')[:60]}"
            )
    new_jobs = [j for j in matched if j.refnr not in known]
    seen = {j.refnr for j in matched}

    suffix = " (dry-run)" if dry_run else ""
    logger.info(
        f"everjobs: {len(all_raw)} total, {len(matched)} DE {role.label}, "
        f"{len(new_jobs)} new{suffix}"
    )

    if dry_run:
        return

    if new_jobs:
        with get_session() as session:
            for job in new_jobs:
                session.add(job)

    existing_seen = (
        set(json.loads(_ATS_SEEN_FILE.read_text()))
        if _ATS_SEEN_FILE.exists()
        else set()
    )
    _ATS_SEEN_FILE.write_text(
        json.dumps(sorted(existing_seen | seen), ensure_ascii=False)
    )
