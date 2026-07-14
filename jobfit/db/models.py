"""SQLAlchemy ORM models for jobfit."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship



class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    refnr: Mapped[str] = mapped_column(String, primary_key=True)
    role: Mapped[str] = mapped_column(String, index=True)
    titel: Mapped[str] = mapped_column(String, default="")
    beschreibung: Mapped[str] = mapped_column(Text, default="")
    firma: Mapped[str] = mapped_column(String, default="")
    externe_url: Mapped[str] = mapped_column(String, default="")
    partner_name: Mapped[str] = mapped_column(String, default="")
    ort_raw: Mapped[str] = mapped_column(String, default="")
    vollzeit: Mapped[bool] = mapped_column(Boolean, default=True)
    ats_source: Mapped[str] = mapped_column(String, default="")
    ats_slug: Mapped[str] = mapped_column(String, default="")
    via: Mapped[str | None] = mapped_column(String, nullable=True)
    salary_min_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String, nullable=True)
    salary_period: Mapped[str | None] = mapped_column(String, nullable=True)
    salary_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    classification: Mapped["Classification"] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )


class Classification(Base):
    __tablename__ = "classifications"

    refnr: Mapped[str] = mapped_column(
        String, ForeignKey("jobs.refnr", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String, index=True)
    company_type: Mapped[str | None] = mapped_column(String, nullable=True)
    company_stage: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    firma: Mapped[str | None] = mapped_column(String, nullable=True)
    titel: Mapped[str | None] = mapped_column(String, nullable=True)
    ort: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    work_mode: Mapped[str | None] = mapped_column(String, nullable=True)
    english_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    german_level: Mapped[str | None] = mapped_column(String, nullable=True)
    on_call: Mapped[bool] = mapped_column(Boolean, default=False)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    experience_years_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seniority: Mapped[str | None] = mapped_column(String, nullable=True)
    certifications_required: Mapped[str | None] = mapped_column(String, nullable=True)
    education_required: Mapped[str | None] = mapped_column(String, nullable=True)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    starred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    job: Mapped["Job"] = relationship(back_populates="classification")


class KnownBrand(Base):
    __tablename__ = "known_brands"

    role: Mapped[str] = mapped_column(String, primary_key=True)
    firma: Mapped[str] = mapped_column(String, primary_key=True)
    is_known: Mapped[bool] = mapped_column(Boolean, default=False)


class UnmatchedIndustry(Base):
    __tablename__ = "unmatched_industries"

    role: Mapped[str] = mapped_column(String, primary_key=True)
    industry: Mapped[str] = mapped_column(String, primary_key=True)
    first_seen: Mapped[str] = mapped_column(String)
    notes: Mapped[str] = mapped_column(String, default="")
