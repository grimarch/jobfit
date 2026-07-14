"""Merge classifications and brands from an old jobfit Postgres into the current DB.

Keeps jobs in the target database unchanged. Copies:
  - known_brands (merge all rows)
  - unmatched_industries (merge all rows)
  - classifications where refnr exists in target jobs (for the given --role)

Environment:
  DATABASE_URL      — target Postgres (new jobfit DB), required
  OLD_DATABASE_URL  — source Postgres (old project DB), required

Setup (run from the jobfit project directory):

    docker compose up -d db

    # Start old Postgres on the jobfit Docker network.
    # The volume name is fixed; cwd does NOT matter (not stellenangebote-parser/).
    docker run -d --name pg-old \\
      --network jobfit_default \\
      -v stellenangebote-parser_postgres_data:/var/lib/postgresql/data \\
      -e POSTGRES_PASSWORD=jobfit -e POSTGRES_USER=jobfit -e POSTGRES_DB=jobfit \\
      postgres:16-alpine

    until docker exec pg-old pg_isready -U jobfit; do sleep 1; done

    docker compose run --rm \\
      -e OLD_DATABASE_URL=postgresql://jobfit:jobfit@pg-old:5432/jobfit \\
      app python scripts/merge_from_old_pg.py --role devops

    docker rm -f pg-old
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import make_transient

from jobfit.db.models import Classification, Job, KnownBrand, UnmatchedIndustry

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


def _merge_rows(dst_session_cls, rows: list) -> int:
    if not rows:
        return 0
    for row in rows:
        make_transient(row)
    with dst_session_cls() as dst:
        for row in rows:
            dst.merge(row)
        dst.commit()
    return len(rows)


def merge_brands_and_industries(
    old_session_cls, new_session_cls, *, dry_run: bool
) -> None:
    for model in (KnownBrand, UnmatchedIndustry):
        with old_session_cls() as src:
            rows = src.query(model).all()
            src.expunge_all()
        print(f"{model.__tablename__}: {len(rows)} rows in source")
        if dry_run:
            continue
        merged = _merge_rows(new_session_cls, rows)
        print(f"  → merged {merged} into target")


def merge_classifications(
    old_session_cls,
    new_session_cls,
    *,
    role: str,
    dry_run: bool,
) -> None:
    with new_session_cls() as dst:
        target_refnrs = {
            refnr for (refnr,) in dst.query(Job.refnr).filter(Job.role == role).all()
        }

    if not target_refnrs:
        print(f"classifications: no jobs in target for role '{role}'")
        return

    with old_session_cls() as src:
        rows = (
            src.query(Classification)
            .filter(
                Classification.role == role, Classification.refnr.in_(target_refnrs)
            )
            .all()
        )
        src.expunge_all()

    skipped = 0
    with old_session_cls() as src:
        skipped = (
            src.query(func.count())
            .select_from(Classification)
            .filter(
                Classification.role == role, Classification.refnr.notin_(target_refnrs)
            )
            .scalar()
            or 0
        )

    print(
        f"classifications: {len(rows)} to merge for role '{role}' "
        f"({skipped} in source skipped — no matching job in target)"
    )

    if dry_run:
        return

    merged = _merge_rows(new_session_cls, rows)
    print(f"  → merged {merged} into target")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge brands/classifications from old Postgres"
    )
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
    print(
        f"  jobs={_count(OldSession, Job)}"
        f"  classifications={_count(OldSession, Classification)}"
        f"  brands={_count(OldSession, KnownBrand)}"
    )
    print("Target (new) before:")
    print(
        f"  jobs={_count(NewSession, Job, role=args.role)}"
        f"  classifications={_count(NewSession, Classification, role=args.role)}"
        f"  brands={_count(NewSession, KnownBrand, role=args.role)}"
    )

    if args.dry_run:
        print("Dry run — no writes.")

    merge_brands_and_industries(OldSession, NewSession, dry_run=args.dry_run)
    merge_classifications(OldSession, NewSession, role=args.role, dry_run=args.dry_run)

    if not args.dry_run:
        from jobfit.classify import unclassified_count

        print("Target (new) after:")
        print(
            f"  classifications={_count(NewSession, Classification, role=args.role)}"
            f"  brands={_count(NewSession, KnownBrand, role=args.role)}"
        )
        print(f"  unclassified jobs: {unclassified_count(args.role)}")
        print(
            "Next: jobfit classify --role", args.role, "(only remaining jobs need LLM)"
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
