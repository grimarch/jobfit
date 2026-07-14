"""Role dataclass — defines a job search profile."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Role:
    slug: str                       # "devops" — used in directory names and CLI flag
    label: str                      # "DevOps / SRE / Platform" — shown in reports
    title_re: re.Pattern[str]       # filter applied to job title during fetch
    skills: list[tuple[str, str]]     # (display_name, regex_pattern) — hard skills only
    practices: list[tuple[str, str]] = field(default_factory=list)  # methodologies / disciplines


def load_role(yaml_path: Path) -> Role:
    """Build a Role from a jobfit/roles/{slug}.yaml definition file."""
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return Role(
        slug=raw["slug"],
        label=raw["label"],
        title_re=re.compile(raw["title_re"], re.IGNORECASE),
        skills=[(name, pattern) for name, pattern in raw["skills"]],
        practices=[(name, pattern) for name, pattern in raw.get("practices", [])],
    )
