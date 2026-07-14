"""Migrate data/devops/jobs/*.json and classifications.json → SQLite DB.

Idempotent: safe to run multiple times.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from jobfit.config import classifications_file, jobs_dir
from jobfit.db import SessionLocal
from jobfit.db.models import Base, Classification, Job
from jobfit.enrich import _ats_to_eur_year, _HOURS_PER_YEAR

from sqlalchemy import create_engine as _ce
import os

_engine_url = os.getenv("DATABASE_URL", "sqlite:///data/jobfit.db")


def _ba_salary_raw(raw: dict) -> tuple[float | None, float | None, str | None, str | None]:
    """Convert BA salary fields to (min_raw, max_raw, currency, period) in EUR/YEAR."""
    vergtype = raw.get("verguetungsangabe")
    if vergtype not in ("JAHRESGEHALT", "STUNDENLOHN"):
        return None, None, None, None
    try:
        von = float(raw["gehaltsspanneVon"])
    except (KeyError, TypeError, ValueError):
        return None, None, None, None
    try:
        bis_raw = raw.get("gehaltsspanneBis")
        bis: float | None = float(bis_raw) if bis_raw else None
    except (TypeError, ValueError):
        bis = None
    multiplier = _HOURS_PER_YEAR if vergtype == "STUNDENLOHN" else 1
    lo = int(von * multiplier)
    hi = int(bis * multiplier) if bis else None
    if not (20_000 <= lo <= 300_000):
        return None, None, None, None
    if hi and not (20_000 <= hi <= 300_000):
        hi = None
    return float(lo), float(hi) if hi else None, "EUR", "YEAR"


def migrate_role(role_slug: str = "devops") -> None:
    from sqlalchemy import create_engine
    engine = create_engine(_engine_url)
    Base.metadata.create_all(engine)

    _jobs_dir = jobs_dir(role_slug)
    _cls_file = classifications_file(role_slug)

    with open(_cls_file) as f:
        classifications: dict = json.load(f)

    session = SessionLocal()
    try:
        jobs_before = session.query(Job).filter(Job.role == role_slug).count()
        cls_before = session.query(Classification).filter(Classification.role == role_slug).count()
        logger.info(f"Before: {jobs_before} jobs, {cls_before} classifications in DB")

        # ── Jobs ──────────────────────────────────────────────────────────────
        jobs_upserted = 0
        for job_file in sorted(_jobs_dir.glob("*.json")):
            refnr = job_file.stem
            with open(job_file) as f:
                raw: dict = json.load(f)

            fetched_at = datetime.fromtimestamp(job_file.stat().st_mtime)

            ort_raw = ""
            locs = raw.get("stellenlokationen") or []
            if locs:
                ort_raw = (locs[0].get("adresse") or {}).get("ort") or ""

            # Determine closed_at from classification _closed flag
            cls_meta = classifications.get(refnr, {})
            closed_at: datetime | None = datetime.now() if cls_meta.get("_closed") else None

            # Salary: prefer ATS structured fields, fallback to BA salary fields
            sal_min_raw = raw.get("_salary_min")
            sal_max_raw = raw.get("_salary_max")
            sal_currency = raw.get("_salary_currency")
            sal_period = raw.get("_salary_period")

            if sal_min_raw is None:
                sal_min_raw, sal_max_raw, sal_currency, sal_period = _ba_salary_raw(raw)

            existing = session.get(Job, refnr)
            if existing is None:
                session.add(Job(
                    refnr=refnr,
                    role=role_slug,
                    titel=raw.get("stellenangebotsTitel") or "",
                    beschreibung=raw.get("stellenangebotsBeschreibung") or "",
                    firma=raw.get("allianzpartnerName") or "",
                    externe_url=raw.get("externeURL") or "",
                    partner_name=raw.get("allianzpartnerName") or "",
                    ort_raw=ort_raw,
                    vollzeit=bool(raw.get("arbeitszeitVollzeit", True)),
                    ats_source=raw.get("_ats_source") or "",
                    ats_slug=raw.get("_ats_slug") or "",
                    via=raw.get("_via"),
                    salary_min_raw=sal_min_raw,
                    salary_max_raw=sal_max_raw,
                    salary_currency=sal_currency,
                    salary_period=sal_period,
                    salary_summary=raw.get("_salary_summary"),
                    fetched_at=fetched_at,
                    closed_at=closed_at,
                ))
            else:
                existing.titel = raw.get("stellenangebotsTitel") or ""
                existing.beschreibung = raw.get("stellenangebotsBeschreibung") or ""
                existing.firma = raw.get("allianzpartnerName") or ""
                existing.externe_url = raw.get("externeURL") or ""
                existing.partner_name = raw.get("allianzpartnerName") or ""
                existing.ort_raw = ort_raw
                existing.vollzeit = bool(raw.get("arbeitszeitVollzeit", True))
                existing.ats_source = raw.get("_ats_source") or ""
                existing.ats_slug = raw.get("_ats_slug") or ""
                existing.via = raw.get("_via")
                existing.salary_min_raw = sal_min_raw
                existing.salary_max_raw = sal_max_raw
                existing.salary_currency = sal_currency
                existing.salary_period = sal_period
                existing.salary_summary = raw.get("_salary_summary")
                existing.closed_at = closed_at
            jobs_upserted += 1

        session.commit()
        logger.info(f"Jobs processed: {jobs_upserted}")

        # ── Classifications ───────────────────────────────────────────────────
        cls_upserted = 0
        cls_skipped = 0
        for refnr, meta in classifications.items():
            if session.get(Job, refnr) is None:
                logger.warning(f"No job row for classification {refnr} — skipping")
                cls_skipped += 1
                continue

            certs = json.dumps(meta.get("certifications_required") or [])
            has_enriched = meta.get("work_mode") is not None
            enriched_at = datetime.now() if has_enriched else None

            existing_cls = session.get(Classification, refnr)
            if existing_cls is None:
                session.add(Classification(
                    refnr=refnr,
                    role=role_slug,
                    company_type=meta.get("company_type"),
                    company_stage=meta.get("company_stage"),
                    industry=meta.get("industry"),
                    firma=meta.get("firma"),
                    titel=meta.get("titel"),
                    ort=meta.get("ort"),
                    region=meta.get("region"),
                    work_mode=meta.get("work_mode"),
                    english_ok=bool(meta.get("english_ok", False)),
                    german_level=meta.get("german_level"),
                    on_call=bool(meta.get("on_call", False)),
                    salary_min=meta.get("salary_min"),
                    salary_max=meta.get("salary_max"),
                    experience_years_min=meta.get("experience_years_min"),
                    seniority=meta.get("seniority"),
                    certifications_required=certs,
                    education_required=meta.get("education_required"),
                    enriched_at=enriched_at,
                ))
            else:
                existing_cls.company_type = meta.get("company_type")
                existing_cls.company_stage = meta.get("company_stage")
                existing_cls.industry = meta.get("industry")
                existing_cls.firma = meta.get("firma")
                existing_cls.titel = meta.get("titel")
                existing_cls.ort = meta.get("ort")
                existing_cls.region = meta.get("region")
                existing_cls.work_mode = meta.get("work_mode")
                existing_cls.english_ok = bool(meta.get("english_ok", False))
                existing_cls.german_level = meta.get("german_level")
                existing_cls.on_call = bool(meta.get("on_call", False))
                existing_cls.salary_min = meta.get("salary_min")
                existing_cls.salary_max = meta.get("salary_max")
                existing_cls.experience_years_min = meta.get("experience_years_min")
                existing_cls.seniority = meta.get("seniority")
                existing_cls.certifications_required = certs
                existing_cls.education_required = meta.get("education_required")
                if has_enriched and existing_cls.enriched_at is None:
                    existing_cls.enriched_at = enriched_at
            cls_upserted += 1

        session.commit()
        if cls_skipped:
            logger.warning(f"Classifications skipped (no job file): {cls_skipped}")
        logger.info(f"Classifications processed: {cls_upserted}")

        jobs_after = session.query(Job).filter(Job.role == role_slug).count()
        cls_after = session.query(Classification).filter(Classification.role == role_slug).count()
        logger.info(f"After:  {jobs_after} jobs, {cls_after} classifications in DB")

    finally:
        session.close()


if __name__ == "__main__":
    migrate_role("devops")
