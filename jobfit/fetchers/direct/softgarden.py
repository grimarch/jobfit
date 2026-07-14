"""Fetch DE DevOps jobs from softgarden career pages.

Companies on softgarden host career pages at {slug}.career.softgarden.de.
Each page exposes a public Schema.org JSON feed at /jobs.feed.json —
no authentication required.

Company slugs are read from data/softgarden_companies.csv.
"""

import argparse
import csv
import json
from datetime import datetime

from loguru import logger

from jobfit.config import DE_CITIES_RE, RAW_DIR, SOFTGARDEN_COMPANIES_FILE
from jobfit.db import get_session
from jobfit.db.models import Job
from jobfit.fetchers.direct._http import get_json
from jobfit.roles import DEFAULT_ROLE, ROLES, Role

_ATS_SEEN_FILE = RAW_DIR / "ats_seen.json"


def _is_germany(job: dict) -> bool:
    loc = job.get("jobLocation", {})
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    addr = loc.get("address", {})
    country = addr.get("addressCountry", "")
    if country:
        return country.upper() in ("DE", "DEU", "GERMANY", "DEUTSCHLAND")
    return bool(DE_CITIES_RE.search(addr.get("addressLocality", "")))


def _fetch_feed(slug: str) -> list[dict]:
    url = f"https://{slug}.career.softgarden.de/jobs.feed.json"
    try:
        return get_json(url, timeout=10).get("dataFeedElement", [])
    except Exception:
        return []


def _item_to_job(item: dict, slug: str, company_name: str, role_slug: str, now: datetime) -> Job:
    job = item.get("item", item)
    loc = job.get("jobLocation", {})
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    addr = loc.get("address", {})
    city = addr.get("addressLocality", "")
    region = addr.get("addressRegion", "")
    ort = ", ".join(filter(None, [city, region])) or addr.get("streetAddress", "")

    identifier = job.get("identifier", {})
    job_id = (
        str(identifier.get("value", "")) if isinstance(identifier, dict) else str(identifier)
    )
    if not job_id:
        job_id = job.get("url", "").rstrip("/").split("/")[-1]

    org = job.get("hiringOrganization", {})
    firma = org.get("name", company_name) if isinstance(org, dict) else company_name

    vollzeit = job.get("employmentType", "FULL_TIME").upper() not in ("PART_TIME", "CONTRACTOR")

    return Job(
        refnr=f"ats-softgarden-{slug}-{job_id}",
        role=role_slug,
        titel=job.get("title", ""),
        beschreibung=job.get("description", ""),
        firma=firma,
        externe_url=job.get("url", ""),
        partner_name=f"softgarden/{slug}",
        ort_raw=ort,
        vollzeit=vollzeit,
        ats_source="softgarden",
        ats_slug=slug,
        via="softgarden_feed",
        salary_min_raw=None,
        salary_max_raw=None,
        salary_currency=None,
        salary_period=None,
        salary_summary=None,
        fetched_at=now,
    )


def _load_companies() -> list[tuple[str, str]]:
    with open(SOFTGARDEN_COMPANIES_FILE, newline="", encoding="utf-8") as f:
        return [(row["name"], row["slug"]) for row in csv.DictReader(f)]


def run(args: argparse.Namespace) -> None:
    role: Role = getattr(args, "role_obj", ROLES[DEFAULT_ROLE])
    dry_run = getattr(args, "dry_run", False)

    with get_session() as session:
        known: set[str] = {
            r for (r,) in session.query(Job.refnr).filter(Job.role == role.slug)
        }

    total_found = 0
    total_new = 0
    seen: set[str] = set()
    new_jobs: list[Job] = []
    now = datetime.now()

    for company_name, slug in _load_companies():
        items = _fetch_feed(slug)
        if not items:
            logger.warning(f"[{slug}] no feed / unreachable")
            continue

        matched = [
            _item_to_job(item, slug, company_name, role.slug, now)
            for item in items
            if role.title_re.search(item.get("item", item).get("title", ""))
            and _is_germany(item.get("item", item))
        ]
        new_items = [j for j in matched if j.refnr not in known]
        logger.info(f"  [{slug}] {len(items)} jobs, {len(matched)} DE {role.label}, {len(new_items)} new")

        if not dry_run:
            for job in new_items:
                known.add(job.refnr)
                new_jobs.append(job)

        seen.update(j.refnr for j in matched)
        total_found += len(matched)
        total_new += len(new_items)

    if not dry_run:
        if new_jobs:
            with get_session() as session:
                for job in new_jobs:
                    session.add(job)
        existing_seen = set(json.loads(_ATS_SEEN_FILE.read_text())) if _ATS_SEEN_FILE.exists() else set()
        _ATS_SEEN_FILE.write_text(json.dumps(sorted(existing_seen | seen), ensure_ascii=False))

    suffix = " (dry-run)" if dry_run else ""
    logger.info(f"softgarden done: {total_found} DE {role.label} jobs found, {total_new} new{suffix}")
