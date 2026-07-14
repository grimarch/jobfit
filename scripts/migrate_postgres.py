"""One-time script: migrate data from SQLite to PostgreSQL.

Called automatically by docker-entrypoint.sh on first boot when data/jobfit.db exists.
A sentinel file data/.pg_migrated is written after a successful run to prevent repeats.

Manual usage:
    docker compose exec app uv run python scripts/migrate_postgres.py
"""

import os

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import joinedload, sessionmaker
from sqlalchemy.orm.session import make_transient

from jobfit.db.models import Classification, Job, KnownBrand, UnmatchedIndustry

SQLITE_URL = os.getenv("SQLITE_URL", "sqlite:///data/jobfit.db")
PG_URL = os.environ.get("DATABASE_URL", "")

if not PG_URL or not PG_URL.startswith("postgresql"):
    raise SystemExit("DATABASE_URL must be a PostgreSQL URL (postgresql://...)")

sqlite_engine = create_engine(SQLITE_URL)
pg_engine = create_engine(PG_URL)

SqliteSession = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
PgSession = sessionmaker(bind=pg_engine, expire_on_commit=False)


def _count(session_cls, model):
    with session_cls() as s:
        return s.query(func.count()).select_from(model).scalar()


# ── Jobs + Classifications ────────────────────────────────────────────────────

sqlite_jobs = _count(SqliteSession, Job)
sqlite_cls = _count(SqliteSession, Classification)
print(f"SQLite    — jobs: {sqlite_jobs}, classifications: {sqlite_cls}")

pg_jobs_before = _count(PgSession, Job)
pg_cls_before = _count(PgSession, Classification)
print(f"PG before — jobs: {pg_jobs_before}, classifications: {pg_cls_before}")

with SqliteSession() as src:
    jobs = src.query(Job).options(joinedload(Job.classification)).all()
    src.expunge_all()

for job in jobs:
    make_transient(job)
    if job.classification is not None:
        make_transient(job.classification)

with PgSession() as dst:
    for job in jobs:
        dst.merge(job)
    dst.commit()

pg_jobs_after = _count(PgSession, Job)
pg_cls_after = _count(PgSession, Classification)
print(f"PG after  — jobs: {pg_jobs_after}, classifications: {pg_cls_after}")

# ── KnownBrand + UnmatchedIndustry ───────────────────────────────────────────

for model in [KnownBrand, UnmatchedIndustry]:
    with SqliteSession() as src:
        rows = src.query(model).all()
        src.expunge_all()
    for row in rows:
        make_transient(row)
    with PgSession() as dst:
        for row in rows:
            dst.merge(row)
        dst.commit()
    print(f"Migrated {model.__tablename__}: {len(rows)} rows")
