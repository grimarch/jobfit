"""Fetch DE DevOps jobs via jobhive Parquet snapshots.

jobhive (storage.stapply.ai) provides daily Parquet snapshots for 49 ATS
platforms. We download, cache locally (24 h TTL), filter for DE + DevOps,
and write directly to the jobs DB table.
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
from loguru import logger

from jobfit.config import ATS_SOURCES, DE_CITIES_RE, DE_RE, RAW_DIR
from jobfit.db import get_session
from jobfit.db.models import Job
from jobfit.fetchers._cache import get_jobs
from jobfit.roles import DEFAULT_ROLE, ROLES, Role

ATS_SEEN_FILE = RAW_DIR / "ats_seen.json"


def is_germany(location: str, country_iso: str = "") -> bool:
    if country_iso:
        return country_iso.upper() == "DE"
    return bool(DE_RE.search(location) or DE_CITIES_RE.search(location))


def _extract_slug(company: str, ats: str) -> str:
    if ats == "personio":
        return (company or "").split(".")[0] or "unknown"
    return company or "unknown"


def _display_name(row: pd.Series, slug: str, ats: str) -> str:
    if ats == "smartrecruiters":
        raw = row.get("raw")
        if isinstance(raw, dict):
            sr = raw.get("company", {})
            if isinstance(sr, dict):
                name = sr.get("name", "")
                if name:
                    return name
    if slug and (any(c.isupper() for c in slug[1:]) or " " in slug):
        return slug
    return slug.title() if slug else "unknown"


def _str(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val)


def _num(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f  # NaN check: NaN != NaN
    except (TypeError, ValueError):
        return None


def _fix_phenom_url(url: str) -> str:
    # jobhive stores {domain}/job/{id} but Phenom SPA requires {domain}/global/en/job/{id}
    return re.sub(r"(https://[^/]+)/job/", r"\1/global/en/job/", url)


def _wttj_canonical_url(uuid: str) -> str | None:
    """Resolve WttJ canonical URL via public UUID API. Returns None on failure."""
    try:
        req = Request(
            f"https://api.welcometothejungle.com/api/v1/jobs/{uuid}",
            headers={"Accept": "application/json"},
        )
        with urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        org = data.get("website_organization_slug", "")
        slug = data.get("job_slug", "")
        if org and slug:
            return f"https://www.welcometothejungle.com/en/companies/{org}/jobs/{slug}"
    except (HTTPError, URLError, Exception):
        pass
    return None


def _row_to_job(row: pd.Series, ats: str, role_slug: str, now: datetime) -> Job:
    url = _str(row.get("url"))
    if ats == "phenom" and url:
        url = _fix_phenom_url(url)
    elif ats == "welcometothejungle" and url:
        uuid = _str(row.get("ats_id"))
        url = _wttj_canonical_url(uuid) or url
    location = _str(row.get("location"))
    slug = _extract_slug(_str(row.get("company")), ats)
    employment_type = _str(row.get("employment_type"))

    return Job(
        refnr=f"ats-{ats}-{row['ats_id']}",
        role=role_slug,
        titel=_str(row.get("title")),
        beschreibung=_str(row.get("description")),
        firma=_display_name(row, slug, ats),
        externe_url=url,
        partner_name=f"{ats}/{slug}",
        ort_raw=location,
        vollzeit=employment_type.upper() != "PART_TIME",
        ats_source=ats,
        ats_slug=slug,
        via="jobhive",
        salary_min_raw=_num(row.get("salary_min")),
        salary_max_raw=_num(row.get("salary_max")),
        salary_currency=_str(row.get("salary_currency")) or None,
        salary_period=_str(row.get("salary_period")) or None,
        salary_summary=_str(row.get("salary_summary")) or None,
        fetched_at=now,
    )


def run(args: argparse.Namespace) -> None:
    role: Role = getattr(args, "role_obj", ROLES[DEFAULT_ROLE])
    sources = getattr(args, "ats", None) or ATS_SOURCES
    dry_run = getattr(args, "dry_run", False)
    force_refresh = getattr(args, "force_refresh", False)
    stats_out = getattr(args, "stats_out", None)

    with get_session() as session:
        known: set[str] = {
            r for (r,) in session.query(Job.refnr).filter(Job.role == role.slug)
        }

    all_refnrs: set[str] = set()
    new_count = 0
    stats: dict[str, dict] = {}
    now = datetime.now()

    for ats in sources:
        logger.info(f"[{ats}]")
        try:
            df = get_jobs(ats, force_refresh=force_refresh)
        except Exception as e:
            logger.warning(f"[{ats}] failed to load: {e}")
            # Preserve existing jobs for this source so mark_closed doesn't falsely close them
            with get_session() as session:
                existing = {
                    r for (r,) in session.query(Job.refnr).filter(
                        Job.role == role.slug, Job.ats_source == ats
                    )
                }
            all_refnrs.update(existing)
            continue

        titles = df["title"].fillna("").astype(str)
        locations = df["location"].fillna("").astype(str)
        country_isos = (
            df["country_iso"].fillna("").astype(str)
            if "country_iso" in df.columns
            else pd.Series([""] * len(df))
        )
        de_mask = pd.Series(
            [is_germany(loc, iso) for loc, iso in zip(locations, country_isos)],
            index=df.index,
        )
        matched_df = df[titles.str.contains(role.title_re) & de_mask]
        if "ats_id" in matched_df.columns:
            matched_df = matched_df.drop_duplicates(subset=["ats_id"], keep="first")

        matched = [_row_to_job(row, ats, role.slug, now) for _, row in matched_df.iterrows()]
        new_jobs = [j for j in matched if j.refnr not in known]
        logger.info(f"  → {len(matched)} matched, {len(new_jobs)} new")

        if not dry_run and new_jobs:
            with get_session() as session:
                for job in new_jobs:
                    session.add(job)
            known.update(j.refnr for j in new_jobs)

        stats[ats] = {"total": len(matched), "companies": {}}
        for job in matched:
            slug = job.ats_slug
            stats[ats]["companies"][slug] = stats[ats]["companies"].get(slug, 0) + 1

        all_refnrs.update(j.refnr for j in matched)
        new_count += len(new_jobs)

    if not dry_run:
        existing_seen = set(json.loads(ATS_SEEN_FILE.read_text())) if ATS_SEEN_FILE.exists() else set()
        ATS_SEEN_FILE.write_text(json.dumps(sorted(existing_seen | all_refnrs), ensure_ascii=False))

    if stats_out:
        Path(stats_out).parent.mkdir(parents=True, exist_ok=True)
        Path(stats_out).write_text(json.dumps(stats, indent=2, ensure_ascii=False))
        logger.info(f"Stats saved to {stats_out}")

    suffix = " (dry-run)" if dry_run else ""
    logger.info(f"jobhive done: {len(all_refnrs)} total, {new_count} new{suffix}")


def backfill_salary() -> int:
    """Patch jobhive Job records missing salary data using cached Parquet snapshots.

    Returns the number of records updated.
    """
    from collections import defaultdict
    from jobfit.fetchers._cache import CACHE_DIR

    with get_session() as session:
        jobs_to_patch = session.query(Job).filter(
            Job.via == "jobhive",
            Job.salary_min_raw.is_(None),
        ).all()

        # Group by ATS source extracted from refnr: ats-{ats}-{id}
        by_ats: dict[str, list[tuple[Job, str]]] = defaultdict(list)
        for job in jobs_to_patch:
            parts = job.refnr.split("-", 2)
            if len(parts) == 3:
                by_ats[parts[1]].append((job, parts[2]))

        updated = 0
        _SAL_COLS = ["salary_min", "salary_max", "salary_currency", "salary_period", "salary_summary"]

        for ats, items in by_ats.items():
            cache_path = CACHE_DIR / f"{ats}.parquet"
            if not cache_path.exists():
                continue
            try:
                df = pd.read_parquet(cache_path)
            except Exception as e:
                logger.warning(f"[{ats}] backfill: failed to load parquet: {e}")
                continue

            if "salary_min" not in df.columns:
                continue

            df = df[["ats_id"] + [c for c in _SAL_COLS if c in df.columns]]
            df = df.drop_duplicates("ats_id").set_index("ats_id")

            for job, raw_id in items:
                try:
                    ats_id: int | str = int(raw_id)
                except ValueError:
                    ats_id = raw_id  # UUID strings (e.g. welcometothejungle)

                if ats_id not in df.index:
                    continue

                row = df.loc[ats_id]
                job.salary_min_raw = _num(row.get("salary_min"))
                job.salary_max_raw = _num(row.get("salary_max"))
                job.salary_currency = _str(row.get("salary_currency")) or None
                job.salary_period = _str(row.get("salary_period")) or None
                job.salary_summary = _str(row.get("salary_summary")) or None
                updated += 1

    logger.info(f"backfill_salary: updated {updated} existing job records")
    return updated
