"""Delete job JSON files after verifying they are all present in the database.

Run ONLY after confirming that:
  1. All fetchers write directly to DB (Phase 2 migration complete)
  2. All JSON data has been migrated (Phase 1 migration was run)
  3. uv run pytest tests/ passes

Usage:
    uv run python scripts/cleanup_json.py [--role ROLE] [--dry-run]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from jobfit.config import DATA_DIR
from jobfit.db import get_session
from jobfit.db.models import Job
from jobfit.roles import DEFAULT_ROLE, ROLES


def cleanup_role(role_slug: str, dry_run: bool = False) -> None:
    jobs_dir = DATA_DIR / role_slug / "jobs"
    if not jobs_dir.exists():
        logger.info(f"[{role_slug}] No jobs directory — nothing to clean up")
        return

    json_files = list(jobs_dir.glob("*.json"))
    if not json_files:
        logger.info(f"[{role_slug}] No JSON files found — already clean")
        return

    logger.info(f"[{role_slug}] Found {len(json_files)} JSON files in {jobs_dir}")

    with get_session() as session:
        db_refnrs = {r for (r,) in session.query(Job.refnr).filter(Job.role == role_slug)}

    file_stems = {f.stem for f in json_files}
    missing_from_db = file_stems - db_refnrs
    if missing_from_db:
        logger.error(
            f"[{role_slug}] {len(missing_from_db)} files not found in DB — ABORTING."
            f" Run migration first."
        )
        for stem in sorted(missing_from_db)[:10]:
            logger.error(f"  {stem}")
        if len(missing_from_db) > 10:
            logger.error(f"  ... and {len(missing_from_db) - 10} more")
        sys.exit(1)

    if dry_run:
        logger.info(f"[{role_slug}] dry-run: would delete {len(json_files)} files")
        return

    for f in json_files:
        f.unlink()
    logger.info(f"[{role_slug}] Deleted {len(json_files)} JSON files from {jobs_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--role", default=DEFAULT_ROLE, choices=list(ROLES), metavar="ROLE")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be deleted, don't delete")
    args = parser.parse_args()
    cleanup_role(args.role, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
