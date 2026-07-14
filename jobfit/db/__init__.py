"""Database engine, session factory, and helpers for jobfit."""

import json
import os
from contextlib import contextmanager
from typing import Any, Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Set it to a PostgreSQL connection string, e.g.:\n"
        "  export DATABASE_URL=postgresql://jobfit:jobfit@localhost:5432/jobfit"
    )

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def cls_to_meta(cls_row: Any) -> dict[str, Any]:
    """Convert a Classification ORM row to the meta dict used by business logic."""
    certs_str = cls_row.certifications_required
    try:
        certs: list[str] = json.loads(certs_str) if certs_str else []
    except (ValueError, TypeError):
        certs = []
    return {
        "company_type":         cls_row.company_type,
        "company_stage":        cls_row.company_stage,
        "industry":             cls_row.industry,
        "firma":                cls_row.firma,
        "titel":                cls_row.titel,
        "ort":                  cls_row.ort,
        "region":               cls_row.region,
        "work_mode":            cls_row.work_mode,
        "english_ok":           bool(cls_row.english_ok),
        "german_level":         cls_row.german_level,
        "on_call":              bool(cls_row.on_call),
        "salary_min":           cls_row.salary_min,
        "salary_max":           cls_row.salary_max,
        "experience_years_min": cls_row.experience_years_min,
        "seniority":            cls_row.seniority,
        "certifications_required": certs,
        "education_required":   cls_row.education_required,
    }
