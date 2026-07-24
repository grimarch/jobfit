"""Load optional stories_enrichment.yaml config for stories draft/refine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from loguru import logger


@dataclass
class EmployerInfo:
    industry: str = ""
    company_stage: str = ""
    display_name: str = ""
    anonymize_level: str = "generic"  # "generic" | "named" | "token"
    comment: str = ""


@dataclass
class StoryOverride:
    comment: str = ""
    optional: bool | None = None  # None = use catalog default


@dataclass
class StoryEnrichment:
    voice: str = ""
    de_level: str = ""
    global_comment: str = ""
    employers: dict[str, EmployerInfo] = field(default_factory=dict)
    stories: dict[str, StoryOverride] = field(default_factory=dict)


def load_enrichment(path: Path | None) -> StoryEnrichment:
    """Load stories_enrichment.yaml. Returns default StoryEnrichment if absent."""
    if path is None or not path.is_file():
        return StoryEnrichment()

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected YAML mapping, got {type(data).__name__}")

    employers: dict[str, EmployerInfo] = {}
    for key, val in (data.get("employers") or {}).items():
        if not isinstance(val, dict):
            logger.warning("stories_enrichment: employers.{} is not a mapping — skipped", key)
            continue
        employers[str(key)] = EmployerInfo(
            industry=str(val.get("industry") or ""),
            company_stage=str(val.get("company_stage") or ""),
            display_name=str(val.get("display_name") or ""),
            anonymize_level=str(val.get("anonymize_level") or "generic"),
            comment=str(val.get("comment") or ""),
        )

    stories: dict[str, StoryOverride] = {}
    for key, val in (data.get("stories") or {}).items():
        if not isinstance(val, dict):
            logger.warning("stories_enrichment: stories.{} is not a mapping — skipped", key)
            continue
        opt_raw = val.get("optional")
        stories[str(key)] = StoryOverride(
            comment=str(val.get("comment") or ""),
            optional=bool(opt_raw) if opt_raw is not None else None,
        )

    return StoryEnrichment(
        voice=str(data.get("voice") or ""),
        de_level=str(data.get("de_level") or ""),
        global_comment=str(data.get("global_comment") or ""),
        employers=employers,
        stories=stories,
    )


def default_enrichment_path(role_slug: str) -> Path:
    from jobfit.config import USER_DATA_DIR
    return USER_DATA_DIR / role_slug / "input" / "stories_enrichment.yaml"


def format_employer_context(
    work_comp: str, enrichment: StoryEnrichment
) -> str:
    """Format employer context line for draft Input table."""
    emp = enrichment.employers.get(work_comp)
    if emp is None:
        return "—"
    parts: list[str] = []
    if emp.display_name:
        parts.append(emp.display_name)
    if emp.industry:
        parts.append(emp.industry)
    if emp.company_stage:
        parts.append(emp.company_stage)
    if emp.anonymize_level and emp.anonymize_level != "generic":
        parts.append(f"anonymize: {emp.anonymize_level}")
    ctx = " · ".join(parts) if parts else "—"
    if emp.comment:
        # Flatten block-scalar comments to single line for table cells
        comment_line = " ".join(emp.comment.strip().splitlines())
        ctx = f"{ctx}. {comment_line}"
    return ctx
