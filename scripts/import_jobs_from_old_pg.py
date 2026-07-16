"""Import jobs from an old jobfit Postgres into the current DB.

Copies rows from the source `jobs` table into the target `jobs` table.
The import is idempotent: existing rows with the same `refnr` are updated.

Environment:
  DATABASE_URL      - target Postgres (new jobfit DB), required
  OLD_DATABASE_URL  - source Postgres (old project DB), required

Setup (run from the jobfit project directory):

    docker compose up -d db

    # Start old Postgres on the jobfit Docker network.
    docker run -d --name pg-old \
      --network jobfit_default \
      -v stellenangebote-parser_postgres_data:/var/lib/postgresql/data \
      -e POSTGRES_PASSWORD=jobfit -e POSTGRES_USER=jobfit -e POSTGRES_DB=jobfit \
      postgres:16-alpine

    until docker exec pg-old pg_isready -U jobfit; do sleep 1; done

    docker compose run --rm \
      -e OLD_DATABASE_URL=postgresql://jobfit:jobfit@pg-old:5432/jobfit \
      app python scripts/import_jobs_from_old_pg.py --role devops

    docker rm -f pg-old
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import make_transient

from jobfit.db.models import Job

NEW_URL = os.environ.get("DATABASE_URL", "")
OLD_URL = os.environ.get("OLD_DATABASE_URL", "")


def _require_pg_url(name: str, url: str) -> None:
    if not url or not url.startswith("postgresql"):
        raise SystemExit(f"{name} must be a PostgreSQL URL (postgresql://...)")


def _session(url: str):
    engine = create_engine(url, echo=False)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _count(session_cls, model, **filters) -> int:
    with session_cls() as session:
        query = session.query(func.count()).select_from(model)
        for key, value in filters.items():
            query = query.filter(getattr(model, key) == value)
        return query.scalar() or 0


def _copy_jobs(old_session_cls, new_session_cls, *, role: str, dry_run: bool) -> None:
    with old_session_cls() as src:
        rows = src.query(Job).filter(Job.role == role).all()
        src.expunge_all()

    print(f"jobs: {len(rows)} rows in source for role '{role}'")

    if dry_run or not rows:
        return

    for row in rows:
        make_transient(row)

    with new_session_cls() as dst:
        for row in rows:
            dst.merge(row)
        dst.commit()

    print(f"  -> merged {len(rows)} into target")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import jobs from old Postgres")
    parser.add_argument("--role", default="devops", help="Role slug (default: devops)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print counts only, do not write"
    )
    args = parser.parse_args()

    _require_pg_url("DATABASE_URL", NEW_URL)
    _require_pg_url("OLD_DATABASE_URL", OLD_URL)

    OldSession = _session(OLD_URL)
    NewSession = _session(NEW_URL)

    print("Source (old):")
    print(f"  jobs={_count(OldSession, Job, role=args.role)}")
    print("Target (new) before:")
    print(f"  jobs={_count(NewSession, Job, role=args.role)}")

    if args.dry_run:
        print("Dry run - no writes.")

    _copy_jobs(OldSession, NewSession, role=args.role, dry_run=args.dry_run)

    if not args.dry_run:
        print("Target (new) after:")
        print(f"  jobs={_count(NewSession, Job, role=args.role)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
