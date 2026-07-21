"""Load role prep layout and match CV bullets to structured claim rows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from jobfit import config
from jobfit.roles import ROLES, Role

_LAYOUTS_DIR = Path(__file__).parent / "layouts"
_CLAIMS_LAYOUT_FILE = "claims_layout.yaml"

_SKILL_PATTERNS: dict[str, str] | None = None


def _skill_patterns(role: Role) -> dict[str, str]:
    global _SKILL_PATTERNS
    if _SKILL_PATTERNS is None:
        _SKILL_PATTERNS = {name: pat for name, pat in role.skills}
    return _SKILL_PATTERNS


@dataclass(frozen=True)
class LayoutRow:
    label: str
    evidence: str
    status: str  # ok | weak | skip


@dataclass(frozen=True)
class LayoutSection:
    title: str
    kind: str  # claims | weak | certs
    rows: list[LayoutRow]


@dataclass(frozen=True)
class ClaimsLayout:
    slug: str
    gaps_heading: str
    gaps_intro: str
    sections: list[LayoutSection]
    do_not_claim_hard_stop: list[str]
    quick_reference: list[tuple[str, str]]  # theme, hint
    source_path: Path | None = None


def default_user_layout_path(role_slug: str) -> Path:
    """User-owned full layout override (gitignored input dir)."""
    return config.role_input_dir(role_slug) / _CLAIMS_LAYOUT_FILE


def repo_layout_path(role_slug: str) -> Path:
    return _LAYOUTS_DIR / f"{role_slug}.yaml"


def resolve_layout_path(role_slug: str) -> Path | None:
    """User claims_layout.yaml wins over repo layouts/{role}.yaml."""
    user = default_user_layout_path(role_slug)
    if user.is_file():
        return user
    repo = repo_layout_path(role_slug)
    if repo.is_file():
        return repo
    return None


def layout_path(role_slug: str) -> Path:
    """Deprecated alias — prefer resolve_layout_path()."""
    return repo_layout_path(role_slug)


def _parse_layout_meta(data: dict[str, Any], role_slug: str, source: Path) -> ClaimsLayout:
    sections: list[LayoutSection] = []
    for sec in data.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        rows: list[LayoutRow] = []
        for row in sec.get("rows") or []:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or row.get("skill") or "").strip()
            if not label:
                continue
            rows.append(
                LayoutRow(
                    label=label,
                    evidence="",
                    status="ok" if sec.get("kind") != "weak" else "weak",
                )
            )
        sections.append(
            LayoutSection(
                title=str(sec.get("title", "")),
                kind=str(sec.get("kind", "claims")),
                rows=rows,
            )
        )

    quick: list[tuple[str, str]] = []
    for item in data.get("quick_reference") or []:
        if isinstance(item, dict):
            quick.append((str(item.get("theme", "")), str(item.get("hint", "—"))))
        elif isinstance(item, str):
            quick.append((item, "—"))

    return ClaimsLayout(
        slug=str(data.get("slug", role_slug)),
        gaps_heading=str(data.get("gaps_heading", "## Gaps vs prep shortlist")),
        gaps_intro=str(data.get("gaps_intro", "")).strip(),
        sections=sections,
        do_not_claim_hard_stop=[str(x) for x in data.get("do_not_claim_hard_stop") or []],
        quick_reference=quick,
        source_path=source,
    )


def load_layout(role_slug: str) -> ClaimsLayout | None:
    path = resolve_layout_path(role_slug)
    if path is None:
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"claims layout must be a mapping: {path}")
    return _parse_layout_meta(data, role_slug, path)


def _bullet_rank(text: str) -> tuple[int, int]:
    return (len(re.findall(r"\d+", text)), len(text))


def _pick_bullet(
    bullets: list[str],
    pattern: str,
    *,
    exclude_pattern: str | None = None,
    used: set[int] | None = None,
) -> tuple[int, str] | None:
    pat = re.compile(pattern, re.IGNORECASE)
    ex = re.compile(exclude_pattern, re.IGNORECASE) if exclude_pattern else None
    best: tuple[tuple[int, int], int, str] | None = None
    for i, bullet in enumerate(bullets):
        if used is not None and i in used:
            continue
        if not pat.search(bullet):
            continue
        if ex is not None and ex.search(bullet):
            continue
        rank = _bullet_rank(bullet)
        if best is None or rank > best[0]:
            best = (rank, i, bullet)
    if best is None:
        return None
    return best[1], best[2]


def _truncate(text: str, limit: int = 280) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _match_row(
    row_spec: dict[str, Any],
    bullets: list[str],
    role: Role,
    used: set[int],
    cv_text: str,
) -> LayoutRow | None:
    label = str(row_spec.get("label") or row_spec.get("skill") or "").strip()
    if not label:
        return None

    if row_spec.get("skip_if"):
        return None

    kind_default = "ok"
    if row_spec.get("optional"):
        kind_default = "weak"

    bullet_pattern = row_spec.get("bullet_pattern")
    skill = row_spec.get("skill")
    cv_pattern = row_spec.get("cv_pattern")

    evidence: str | None = None
    status = str(row_spec.get("default_status") or kind_default)

    if cv_pattern:
        pat = re.compile(cv_pattern, re.IGNORECASE | re.MULTILINE)
        m = pat.search(cv_text)
        if m:
            start = max(0, cv_text.rfind("\n", 0, m.start()) + 1)
            end = cv_text.find("\n", m.end())
            line = cv_text[start : end if end != -1 else None].strip()
            evidence = _truncate(line) if line else _truncate(m.group(0))
            status = str(row_spec.get("default_status") or "ok")
        else:
            if row_spec.get("optional"):
                return None
            evidence = "—"
            status = "weak"
    elif bullet_pattern:
        picked = _pick_bullet(
            bullets,
            str(bullet_pattern),
            exclude_pattern=row_spec.get("exclude_pattern"),
            used=used,
        )
        if picked:
            idx, bullet = picked
            used.add(idx)
            evidence = _truncate(bullet)
            status = "ok"
        elif row_spec.get("optional"):
            return None
        else:
            evidence = "—"
            status = "weak"
    elif skill:
        patterns = _skill_patterns(role)
        pat_str = patterns.get(str(skill))
        if not pat_str:
            evidence = "—"
            status = "weak"
        else:
            picked = _pick_bullet(bullets, pat_str, used=used)
            if picked:
                idx, bullet = picked
                used.add(idx)
                evidence = _truncate(bullet)
                status = "ok"
            else:
                note = row_spec.get("note")
                if note:
                    evidence = str(note)
                else:
                    evidence = "Listed in CV skills section — no dedicated experience bullet matched"
                status = "weak"
    else:
        return None

    if row_spec.get("kind") == "weak" or row_spec.get("note") and status == "weak":
        note = row_spec.get("note")
        if note and evidence.startswith("Listed in CV"):
            evidence = str(note)

    return LayoutRow(label=label, evidence=evidence, status=status)


def build_layout_sections(
    cv_text: str,
    role_slug: str,
    *,
    bullets: list[str] | None = None,
    layout_file: Path | None = None,
) -> ClaimsLayout | None:
    """Return layout with evidence filled from CV. None if no layout file for role."""
    raw_path = layout_file or resolve_layout_path(role_slug)
    if raw_path is None:
        return None

    data = yaml.safe_load(raw_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"claims layout must be a mapping: {raw_path}")

    role = ROLES[role_slug]
    if bullets is None:
        from jobfit.prep_context.claims import extract_experience_bullets

        bullets = extract_experience_bullets(cv_text)

    used: set[int] = set()
    sections: list[LayoutSection] = []
    skip_labels: set[str] = set()

    for sec in data.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        kind = str(sec.get("kind", "claims"))
        built_rows: list[LayoutRow] = []
        for row_spec in sec.get("rows") or []:
            if not isinstance(row_spec, dict):
                continue
            skip_if = row_spec.get("skip_if")
            if skip_if and skip_if in skip_labels:
                continue
            row = _match_row(row_spec, bullets, role, used, cv_text)
            if row is None:
                continue
            if kind == "weak":
                row = LayoutRow(row.label, row.evidence, "weak")
            built_rows.append(row)
            if row_spec.get("label"):
                skip_labels.add(str(row_spec["label"]))

        if built_rows:
            sections.append(
                LayoutSection(
                    title=str(sec.get("title", "")),
                    kind=kind,
                    rows=built_rows,
                )
            )

    quick: list[tuple[str, str]] = []
    for item in data.get("quick_reference") or []:
        if isinstance(item, dict):
            quick.append((str(item.get("theme", "")), str(item.get("hint", "—"))))
        elif isinstance(item, str):
            quick.append((item, "—"))

    return ClaimsLayout(
        slug=str(data.get("slug", role_slug)),
        gaps_heading=str(data.get("gaps_heading", "## Gaps vs prep shortlist")),
        gaps_intro=str(data.get("gaps_intro", "")).strip(),
        sections=sections,
        do_not_claim_hard_stop=[str(x) for x in data.get("do_not_claim_hard_stop") or []],
        quick_reference=quick,
        source_path=raw_path,
    )
