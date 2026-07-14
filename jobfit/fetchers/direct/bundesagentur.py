"""Fetch DE DevOps jobs from Bundesagentur für Arbeit REST API.

Three-phase pipeline (replaces the three bash scripts):
  1. Search  — query BA API for DevOps-related terms → data/raw/bundesagentur.json
  2. Details — fetch full job record per refnr        → data/raw/bundesagentur_details/
  3. Filter  — insert DevOps-relevant jobs into DB

The API key is public and documented in BA's developer portal.
"""

import argparse
import base64
import json
import time
import urllib.parse
import urllib.error
from datetime import datetime

from loguru import logger
from tqdm import tqdm

from jobfit.config import RAW_DIR
from jobfit.db import get_session
from jobfit.db.models import Job
from jobfit.fetchers.direct._http import get_json
from jobfit.roles import DEFAULT_ROLE, ROLES, Role

_API = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4"
_KEY = {"X-API-Key": "jobboerse-jobsuche"}

BA_RAW = RAW_DIR / "bundesagentur.json"
DETAILS_DIR = RAW_DIR / "bundesagentur_details"

_SEARCH_TERMS = [
    "DevOps",
    "Platform Engineer",
    "Site Reliability Engineer",
    "Cloud Engineer",
    "Infrastructure Engineer",
    "Cloud Architect",
    "Cloud Administrator",
    "Kubernetes Engineer",
    "Linux Administrator",
    "Operations Engineer",
    "Release Engineer",
]

_FIXED = "angebotsart=1&befristung=2&zeitarbeit=false&size=100"

# Hours/year used for STUNDENLOHN → annual conversion
_HOURS_PER_YEAR = 1760


def _search(days: int = 60) -> list[dict]:
    seen: dict[str, dict] = {}

    for term in _SEARCH_TERMS:
        q = urllib.parse.urlencode({"was": term})
        url1 = f"{_API}/jobs?{q}&{_FIXED}&veroeffentlichtseit={days}&page=1"
        try:
            data = get_json(url1, headers=_KEY, timeout=15)
        except Exception as exc:
            logger.warning(f"[{term}]: {exc}")
            continue

        total = data.get("maxErgebnisse", 0)
        pages = max(1, (total + 99) // 100)
        logger.info(f"  [{term}] {total} results, {pages} pages")

        for job in data.get("stellenangebote", []):
            seen[job["refnr"]] = job

        for p in range(2, pages + 1):
            url = f"{_API}/jobs?{q}&{_FIXED}&veroeffentlichtseit={days}&page={p}"
            try:
                for job in get_json(url, headers=_KEY, timeout=15).get("stellenangebote", []):
                    seen[job["refnr"]] = job
            except Exception:
                pass
            time.sleep(0.5)

    return list(seen.values())


def _fetch_details(refnrs: list[str], *, force: bool = False) -> int:
    """Fetch full detail for each refnr; skip if cached. Return count of newly fetched files."""
    DETAILS_DIR.mkdir(parents=True, exist_ok=True)
    fetched = 0
    to_fetch = [r for r in refnrs if force or not (DETAILS_DIR / f"{r.replace('/', '_')}.json").exists()]

    with tqdm(total=len(to_fetch), unit="job", desc="BA details", leave=False) as bar:
        for refnr in to_fetch:
            out = DETAILS_DIR / f"{refnr.replace('/', '_')}.json"
            encoded = base64.b64encode(refnr.encode()).decode()
            try:
                detail = get_json(f"{_API}/jobdetails/{encoded}", headers=_KEY, timeout=15)
                out.write_text(json.dumps(detail, ensure_ascii=False, indent=2))
                fetched += 1
            except Exception as exc:
                logger.warning(f"{refnr}: {exc}")

            bar.update(1)
            # Polite rate-limiting: 1s pause every 10 fetches
            if fetched > 0 and fetched % 10 == 0:
                time.sleep(1)

    return fetched


def _is_germany_ba(job: dict) -> bool:
    """Return True if at least one location has land==DEUTSCHLAND, or if no land field at all."""
    locs = job.get("stellenlokationen", [])
    if not locs:
        return True  # no location data → assume DE (BA is a German-only platform by design)
    lands = [loc.get("adresse", {}).get("land", "") for loc in locs]
    lands = [l for l in lands if l]
    if not lands:
        return True  # land field absent → assume DE
    return any(l.upper() == "DEUTSCHLAND" for l in lands)


def _ba_salary(raw: dict) -> tuple[float | None, float | None, str | None, str | None]:
    """Extract salary from BA structured fields → (min_raw, max_raw, currency, period)."""
    vergtype = raw.get("verguetungsangabe")
    if vergtype not in ("JAHRESGEHALT", "STUNDENLOHN"):
        return None, None, None, None
    try:
        von = float(raw["gehaltsspanneVon"])
    except (KeyError, TypeError, ValueError):
        return None, None, None, None
    try:
        bis: float | None = float(raw.get("gehaltsspanneBis") or 0) or None
    except (TypeError, ValueError):
        bis = None
    period = "YEAR" if vergtype == "JAHRESGEHALT" else "HOUR"
    return von, bis, "EUR", period


def _filter_to_jobs(role: Role) -> int:
    """Insert role-relevant detail files into DB. Return count of newly inserted records."""
    with get_session() as session:
        known: set[str] = {
            r for (r,) in session.query(Job.refnr).filter(Job.role == role.slug)
        }

    new_jobs: list[Job] = []
    now = datetime.now()

    for f in DETAILS_DIR.glob("*.json"):
        try:
            job = json.loads(f.read_text())
        except Exception:
            continue

        # Use actual refnr from JSON; sanitise slashes to match filename convention
        refnr = (job.get("refnr") or f.stem).replace("/", "_")
        if refnr in known:
            continue

        if not (role.title_re.search(job.get("stellenangebotsTitel", "")) and _is_germany_ba(job)):
            continue

        locs = job.get("stellenlokationen") or []
        ort_raw = ""
        if locs:
            ort_raw = (locs[0].get("adresse") or {}).get("ort") or locs[0].get("ort") or ""

        sal_min, sal_max, sal_currency, sal_period = _ba_salary(job)

        new_jobs.append(Job(
            refnr=refnr,
            role=role.slug,
            titel=job.get("stellenangebotsTitel") or "",
            beschreibung=job.get("stellenangebotsBeschreibung") or "",
            firma=job.get("firma") or "",
            externe_url=job.get("externeURL") or "",
            partner_name=job.get("allianzpartnerName") or "",
            ort_raw=ort_raw,
            vollzeit=bool(job.get("arbeitszeitVollzeit", True)),
            ats_source="",
            ats_slug="",
            via=None,
            salary_min_raw=sal_min,
            salary_max_raw=sal_max,
            salary_currency=sal_currency,
            salary_period=sal_period,
            salary_summary=None,
            fetched_at=now,
        ))
        known.add(refnr)

    if new_jobs:
        with get_session() as session:
            for job in new_jobs:
                session.add(job)

    return len(new_jobs)


def run(args: argparse.Namespace) -> None:
    role: Role = getattr(args, "role_obj", ROLES[DEFAULT_ROLE])
    dry_run = getattr(args, "dry_run", False)
    force = getattr(args, "force_refresh", False)
    days = getattr(args, "days", 60)

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Phase 1: Search")
    jobs = _search(days=days)
    logger.info(f"  Total unique: {len(jobs)}")
    if not dry_run:
        BA_RAW.write_text(
            json.dumps({"stellenangebote": jobs, "maxErgebnisse": len(jobs)},
                       ensure_ascii=False, indent=2)
        )
        logger.info(f"  Saved to {BA_RAW}")

    logger.info("Phase 2: Details")
    refnrs = [j["refnr"] for j in jobs]
    if dry_run:
        cached = sum(
            1 for r in refnrs
            if (DETAILS_DIR / f"{r.replace('/', '_')}.json").exists()
        )
        logger.info(f"  {cached}/{len(refnrs)} already cached (dry-run: skipping fetch)")
    else:
        fetched = _fetch_details(refnrs, force=force)
        logger.info(f"  Fetched {fetched} new detail files ({len(refnrs) - fetched} already cached)")

    logger.info("Phase 3: Filter")
    if dry_run:
        matched = sum(
            1 for f in DETAILS_DIR.glob("*.json")
            if role.title_re.search(
                json.loads(f.read_text()).get("stellenangebotsTitel", "")
            )
        ) if DETAILS_DIR.exists() else 0
        logger.info(f"  {matched} {role.label} jobs in cache (dry-run: not inserting)")
    else:
        inserted = _filter_to_jobs(role)
        logger.info(f"  Inserted {inserted} new {role.label} jobs into DB")
