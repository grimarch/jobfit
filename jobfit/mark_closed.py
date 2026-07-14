"""Mark jobs that have disappeared from their source as closed.

Reads:
  data/raw/bundesagentur.json  — current BA listing (refnrs still live)
  data/raw/ats_seen.json       — refnrs returned by the last ATS fetch run

For each open job in the DB that is NOT in its source's current set,
sets closed_at = now() on the Job row.
"""

import argparse
import json
from datetime import datetime

from loguru import logger

from jobfit.config import RAW_DIR
from jobfit.db import get_session
from jobfit.db.models import Job
from jobfit.roles import DEFAULT_ROLE, ROLES, Role

BA_RAW = RAW_DIR / "bundesagentur.json"
ATS_SEEN_FILE = RAW_DIR / "ats_seen.json"


def _load_ba_seen() -> set[str] | None:
    if not BA_RAW.exists():
        return None
    with open(BA_RAW) as f:
        listing = json.load(f)
    return {job["refnr"] for job in listing.get("stellenangebote", [])}


def _load_ats_seen() -> set[str] | None:
    if not ATS_SEEN_FILE.exists():
        return None
    with open(ATS_SEEN_FILE) as f:
        return set(json.load(f))


def run(args: argparse.Namespace) -> None:
    role: Role = getattr(args, "role_obj", ROLES[DEFAULT_ROLE])
    dry_run = getattr(args, "dry_run", False)
    now = datetime.now()

    ba_seen = _load_ba_seen()
    ats_seen = _load_ats_seen()

    if ba_seen is None:
        logger.warning("bundesagentur.json not found — skipping BA closed detection")
    if ats_seen is None:
        logger.warning("ats_seen.json not found — skipping ATS closed detection")

    newly_closed: list[str] = []
    already_closed = 0

    with get_session() as session:
        jobs = session.query(Job).filter(Job.role == role.slug).all()
        total = len(jobs)

        for job in jobs:
            if job.closed_at is not None:
                already_closed += 1
                continue

            is_ba = not job.via
            seen = ba_seen if is_ba else ats_seen

            if seen is None or job.refnr in seen:
                continue

            logger.info(f"CLOSED {job.refnr} | {job.firma} | {job.titel}")
            newly_closed.append(job.refnr)

            if not dry_run:
                job.closed_at = now

    active = total - already_closed - len(newly_closed)
    suffix = " (dry-run)" if dry_run else ""
    logger.info(
        f"mark-closed: {len(newly_closed)} newly closed{suffix}"
        f"  |  {already_closed} already closed"
        f"  |  {active} still active"
    )
