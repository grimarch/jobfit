"""Draft prep personas (Phase 1) from context.md and reviewed claims.md."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from jobfit.config import USER_DATA_DIR
from jobfit.prep.context_parse import ContextBlock, parse_context_blocks

_DRAFT_PERSONAS_FILE = "personas.draft.md"
_REVIEWED_CLAIMS_FILE = "claims.md"
_LLM_INPUT_BEGIN = "<!-- jobfit:prep-personas:llm-input -->"
_LLM_INPUT_END = "<!-- /jobfit:prep-personas:llm-input -->"
_CLAIMS_GAPS_BEGIN = "<!-- jobfit:prep-claims:gaps -->"
_CLAIMS_GAPS_END = "<!-- /jobfit:prep-claims:gaps -->"
_DRAFT_FOOTER_HEADING = "## How this file is used"
_REVIEWED_MARKER = "**Reviewed:**"


@dataclass(frozen=True)
class ClaimsGapEntry:
    skill: str
    jobs: str
    do_not_claim: str
    say_instead: str


def default_draft_path(role_slug: str) -> Path:
    return Path(f"prompts/prep/{role_slug}") / _DRAFT_PERSONAS_FILE


def default_claims_path(role_slug: str) -> Path:
    return Path(f"prompts/prep/{role_slug}") / _REVIEWED_CLAIMS_FILE


def default_prep_roles_yaml_path(role_slug: str) -> Path:
    return USER_DATA_DIR / role_slug / "input" / "prep_roles.yaml"


def require_reviewed_claims(claims_text: str, claims_path: Path) -> None:
    """Raise ValueError if claims.md lacks **Reviewed:** header."""
    if _REVIEWED_MARKER not in claims_text:
        raise ValueError(
            f"{claims_path}: missing {_REVIEWED_MARKER!r} — "
            "run prep-claims refine + verify, then cp claims.llm.md claims.md"
        )


def extract_llm_input(md_text: str) -> str:
    """Return personas body for LLM refine (between llm-input markers)."""
    if _LLM_INPUT_BEGIN in md_text and _LLM_INPUT_END in md_text:
        start = md_text.index(_LLM_INPUT_BEGIN) + len(_LLM_INPUT_BEGIN)
        end = md_text.index(_LLM_INPUT_END)
        return md_text[start:end].strip()
    idx = md_text.find(_DRAFT_FOOTER_HEADING)
    if idx != -1:
        return md_text[:idx].strip()
    return md_text.strip()


def parse_claims_gaps(claims_text: str) -> list[ClaimsGapEntry]:
    """Parse gaps table from reviewed claims.md between HTML markers."""
    if _CLAIMS_GAPS_BEGIN not in claims_text or _CLAIMS_GAPS_END not in claims_text:
        return []
    start = claims_text.index(_CLAIMS_GAPS_BEGIN) + len(_CLAIMS_GAPS_BEGIN)
    end = claims_text.index(_CLAIMS_GAPS_END)
    section = claims_text[start:end]

    entries: list[ClaimsGapEntry] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("| **"):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        cells = [c for c in cells if c]
        if len(cells) < 5:
            continue
        skill = re.sub(r"^\*\*(.+?)\*\*$", r"\1", cells[0])
        do_not_claim = "" if cells[3] == "—" else cells[3]
        say_instead = "" if cells[4] == "—" else cells[4]
        entries.append(
            ClaimsGapEntry(
                skill=skill,
                jobs=cells[1],
                do_not_claim=do_not_claim,
                say_instead=say_instead,
            )
        )
    return entries


def parse_claims_do_not_claim(claims_text: str) -> list[str]:
    """Parse Do not claim bullet list from claims.md."""
    marker = "## Do not claim (hard stop)"
    if marker not in claims_text:
        return []
    rest = claims_text.split(marker, 1)[1]
    next_section = re.search(r"^## ", rest, re.MULTILINE)
    if next_section:
        rest = rest[: next_section.start()]
    return [
        line.strip()[2:].strip()
        for line in rest.splitlines()
        if line.strip().startswith("- ")
    ]


def parse_claims_quick_reference(claims_text: str) -> str:
    """Extract Quick reference section from claims.md for machine context."""
    marker = "## Quick reference"
    if marker not in claims_text:
        return ""
    rest = claims_text.split(marker, 1)[1]
    next_section = re.search(r"^## ", rest, re.MULTILINE)
    section = rest[: next_section.start()] if next_section else rest
    return (marker + section).strip()


def parse_claims_ok_labels(claims_text: str) -> list[str]:
    """Extract claim labels with status 'ok' from claims.md tables."""
    _OK_ROW_RE = re.compile(r"^\|\s*\*\*(.+?)\*\*\s*\|.*\|\s*ok\s*\|", re.MULTILINE)
    return [m.group(1) for m in _OK_ROW_RE.finditer(claims_text)]


def _skills_match(a: str, b: str) -> bool:
    """Bidirectional skill name match handling aliases like Go/Golang."""
    if a.lower() == b.lower():
        return True
    a_parts = {p.strip().lower() for p in a.split("/")}
    b_parts = {p.strip().lower() for p in b.split("/")}
    return bool(a_parts & b_parts)


def filter_gaps_for_job(
    block: ContextBlock, all_gaps: list[ClaimsGapEntry]
) -> list[ClaimsGapEntry]:
    """Filter claims gaps to those relevant for this job's gaps_vs_cv list."""
    return [
        gap
        for gap in all_gaps
        if any(_skills_match(gap.skill, jg) for jg in block.gaps_vs_cv)
    ]


def _archetype_from_block(block: ContextBlock) -> str:
    parts = []
    if block.company_stage:
        parts.append(block.company_stage)
    if block.industry:
        parts.append(block.industry)
    return " / ".join(parts) if parts else ""


def _language_hint(block: ContextBlock) -> str:
    parts: list[str] = []
    if block.english_ok:
        parts.append("EN")
    if block.german_level and block.german_level.lower() not in ("unspecified", ""):
        parts.append(f"DE {block.german_level}")
    if not parts:
        parts.append("EN")
    if block.on_call:
        parts.append("on-call flag")
    return " / ".join(parts)


def load_prep_roles_yaml(path: Path) -> dict[str, Any] | None:
    """Load prep_roles.yaml config. Returns None if file absent or invalid."""
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected YAML mapping, got {type(data).__name__}")
    return data



def _build_roles_from_yaml(
    yaml_config: dict[str, Any], blocks_by_sid: dict[str, ContextBlock]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse prep_roles.yaml into (mock_cycle, later) entry lists."""
    mock_cycle: list[dict[str, Any]] = []
    for entry in yaml_config.get("mock_cycle", []):
        sid = str(entry.get("id", ""))
        archetype = entry.get(
            "archetype",
            _archetype_from_block(blocks_by_sid[sid]) if sid in blocks_by_sid else "",
        )
        mock_cycle.append(
            {
                "id": sid,
                "label": str(entry.get("label", sid)),
                "archetype": archetype,
                "llm": entry.get("llm", {}),
            }
        )

    later: list[dict[str, Any]] = []
    for entry in yaml_config.get("later", []):
        sid = str(entry.get("id", ""))
        archetype = entry.get(
            "archetype",
            _archetype_from_block(blocks_by_sid[sid]) if sid in blocks_by_sid else "",
        )
        later.append(
            {
                "id": sid,
                "label": str(entry.get("label", "Later")),
                "archetype": archetype,
                "reason": str(entry.get("reason", "")),
            }
        )

    return mock_cycle, later


def validate_prep_roles_yaml(
    yaml_config: dict[str, Any], blocks_by_sid: dict[str, ContextBlock]
) -> None:
    """Validate prep_roles.yaml ids against parsed context blocks. Raises ValueError."""
    available = sorted(blocks_by_sid.keys())
    for entry in yaml_config.get("mock_cycle", []):
        sid = str(entry.get("id", ""))
        if sid not in blocks_by_sid:
            raise ValueError(
                f"prep_roles.yaml: unknown id {sid!r} in mock_cycle — "
                f"available: {available}"
            )
    for entry in yaml_config.get("later", []):
        sid = str(entry.get("id", ""))
        if sid not in blocks_by_sid:
            raise ValueError(
                f"prep_roles.yaml: unknown id {sid!r} in later — "
                f"available: {available}"
            )
    mock_cycle_ids = {str(e.get("id", "")) for e in yaml_config.get("mock_cycle", [])}
    for sid in yaml_config.get("mock_order", []):
        if str(sid) not in mock_cycle_ids:
            raise ValueError(
                f"prep_roles.yaml: mock_order id {sid!r} not in mock_cycle — "
                f"mock_cycle ids: {sorted(mock_cycle_ids)}"
            )


def _md_cell(text: str) -> str:
    display = text.strip() if text.strip() else "—"
    return display.replace("|", "\\|")


def render_draft_md(
    *,
    role_slug: str,
    context_path: Path,
    claims_path: Path,
    blocks: list[ContextBlock],
    all_gaps: list[ClaimsGapEntry],
    mock_cycle: list[dict[str, Any]],
    later_list: list[dict[str, Any]],
    mock_order: list[str],
    prep_roles_config_label: str,
    refine_config: dict[str, Any] | None = None,
) -> str:
    """Render personas.draft.md from parsed inputs."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    blocks_by_sid = {b.sid: b for b in blocks}
    all_roles = mock_cycle + later_list

    lines: list[str] = [
        f"# Prep roles ({role_slug})",
        "",
        f"**Draft** generated: {now}",
        f"**Context source:** `{context_path.as_posix()}`",
        f"**Claims source:** `{claims_path.as_posix()}`",
        f"**Prep roles config:** `{prep_roles_config_label}`",
        "",
        "> Machine draft — not for mock interviews. "
        "Run `prep-personas refine` then human verify.",
        "",
        "**Field guide:** [personas.example.md](personas.example.md) "
        "· Proof: [claims.md](claims.md)",
        "",
        "---",
        "",
        _LLM_INPUT_BEGIN,
        "",
        "| Prep role | Job | Company | prep_label | Archetype | Primary gaps |",
        "|---|---|---|---|---|---|",
    ]

    for entry in all_roles:
        sid = entry["id"]
        block = blocks_by_sid.get(sid)
        if not block:
            continue
        job_title = f"{sid} — {block.title}" if block.title else sid
        primary_gaps = _md_cell(", ".join(block.gaps_vs_cv[:4]))
        lines.append(
            f"| {entry['label']} | {job_title} | {_md_cell(block.company)}"
            f" | {block.prep_label} | {_md_cell(entry['archetype'])}"
            f" | {primary_gaps} |"
        )

    lines.extend(["", "## Mock order", ""])
    for i, sid in enumerate(mock_order, 1):
        entry = next((e for e in all_roles if e["id"] == sid), None)
        block = blocks_by_sid.get(sid)
        if not entry or not block:
            continue
        archetype = entry["archetype"]
        rationale = f"{block.prep_label} · {archetype}" if archetype else block.prep_label
        lines.append(f"{i}. **{sid}** ({entry['label']}) — {rationale}")

    # Per-role blocks
    for entry in mock_cycle:
        sid = entry["id"]
        block = blocks_by_sid.get(sid)
        if not block:
            continue
        archetype = entry["archetype"]
        section_title = f"## {sid} — {entry['label']}"
        if archetype:
            section_title += f" ({archetype})"

        lines.extend(["", "---", "", section_title, ""])

        company_line = f"**Company:** {block.company}" if block.company else "**Company:** —"
        lines.append(company_line)

        meta_parts = [f"**prep_label:** {block.prep_label}"]
        if block.refnr:
            meta_parts.append(f"**refnr:** {block.refnr}")
        lines.append(" · ".join(meta_parts))
        jd_excerpt = block.jd_excerpt[:400] if block.jd_excerpt else "—"
        lines.extend(["", f"**JD excerpt:** {jd_excerpt}", ""])
        llm_hints = entry.get("llm", {})
        if llm_hints:
            hint_lines = [f"<!-- jobfit:prep-personas:llm-hints:{sid}"]
            for key, val in llm_hints.items():
                if isinstance(val, list):
                    hint_lines.append(f"{key}: {', '.join(str(v) for v in val)}")
                elif val is not None:
                    hint_lines.append(f"{key}: {val}")
            hint_lines.append("/jobfit:prep-personas:llm-hints -->")
            lines.extend(hint_lines)
        lines.extend(["**JD focus:** _TODO — paraphrase JD excerpt above_", ""])
        lines.extend(
            ["**Lead from claims:** _TODO — refine: 3–5 ok claims / Quick reference themes_", ""]
        )

        job_gaps = filter_gaps_for_job(block, all_gaps)
        lines.append("**Gaps for this job:**")
        if job_gaps:
            for gap in job_gaps:
                do_not = gap.do_not_claim if gap.do_not_claim else "—"
                say = gap.say_instead if gap.say_instead else "—"
                lines.append(f"- **{gap.skill}** — Do not claim: {do_not}. Say: {say}")
        else:
            lines.append("- (no gaps from claims for this job)")

        lines.extend([
            "",
            "**Mock traps:** _TODO — refine: Do not claim + JD-specific_",
            "",
            f"**Language:** _TODO — refine from context: {_language_hint(block)}_",
            "",
            "**Stories to write (Phase 2):** _TODO — refine: numbered story topics_",
        ])

    # Later section
    if later_list:
        lines.extend(["", "---", "", "## Later jobs (skip first mock cycle)", ""])
        for entry in later_list:
            sid = entry["id"]
            block = blocks_by_sid.get(sid)
            if not block:
                continue
            reason = entry.get("reason") or f"prep_label: {block.prep_label}"
            archetype = entry.get("archetype", "")
            label_str = f"**{sid} — {entry['label']}**"
            if archetype:
                label_str += f" ({archetype})"
            lines.append(label_str)
            company_line = f"**Company:** {block.company}" if block.company else "**Company:** —"
            lines.append(company_line)
            later_meta = [f"**prep_label:** {block.prep_label}"]
            if block.refnr:
                later_meta.append(f"**refnr:** {block.refnr}")
            lines.append(" · ".join(later_meta))
            lines.append(reason)
            lines.append("")

    # Anchors skeleton
    lines.extend(["", "---", "", "## Anchors", "", "| Job | One-line anchor |", "|---|---|"])
    for entry in mock_cycle:
        lines.append(f"| {entry['id']} | _TODO — refine_ |")

    # Refine config from yaml (before closing llm-input marker)
    if refine_config:
        rc_lines = ["", "<!-- jobfit:prep-personas:refine-config"]
        for key, val in refine_config.items():
            str_val = str(val)
            if "\n" in str_val:
                rc_lines.append(f"{key}: |")
                for line in str_val.splitlines():
                    rc_lines.append(f"  {line}")
            else:
                rc_lines.append(f"{key}: {str_val}")
        rc_lines.append("/jobfit:prep-personas:refine-config -->")
        lines.extend(rc_lines)

    lines.extend([
        "",
        _LLM_INPUT_END,
        "",
        "---",
        "",
        _DRAFT_FOOTER_HEADING,
        "",
        "- `prep-personas refine` reads content between llm-input markers.",
        "- Human promotes `personas.llm.md` → `personas.md` after verify.",
        "- See docs/prep-personas-review.md.",
        "",
    ])

    return "\n".join(lines)


def run(
    *,
    role_slug: str,
    context_path: Path,
    claims_path: Path,
    out_path: Path,
    prep_roles_path: Path | None = None,
    require_reviewed: bool = True,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    if not context_path.is_file():
        raise FileNotFoundError(f"Context not found: {context_path}")
    if not claims_path.is_file():
        raise FileNotFoundError(f"Claims not found: {claims_path}")

    claims_text = claims_path.read_text(encoding="utf-8")
    context_text = context_path.read_text(encoding="utf-8")

    if require_reviewed:
        require_reviewed_claims(claims_text, claims_path)

    blocks = parse_context_blocks(context_text)
    all_gaps = parse_claims_gaps(claims_text)
    blocks_by_sid = {b.sid: b for b in blocks}

    # Option A: yaml is required for draft
    yaml_path = prep_roles_path or default_prep_roles_yaml_path(role_slug)
    prep_roles_config = load_prep_roles_yaml(yaml_path)
    if prep_roles_config is None:
        raise FileNotFoundError(
            f"prep_roles.yaml not found at {yaml_path} — "
            f"copy {USER_DATA_DIR / role_slug / 'input' / 'prep_roles.yaml.example'}"
        )
    validate_prep_roles_yaml(prep_roles_config, blocks_by_sid)
    mock_cycle, later_list = _build_roles_from_yaml(prep_roles_config, blocks_by_sid)
    mock_order: list[str] = [str(sid) for sid in prep_roles_config.get(
        "mock_order", [e["id"] for e in mock_cycle]
    )]
    refine_config: dict[str, Any] | None = prep_roles_config.get("refine")
    config_label = yaml_path.as_posix()

    summary: dict[str, Any] = {
        "role": role_slug,
        "context": str(context_path),
        "claims": str(claims_path),
        "out": str(out_path),
        "mock_cycle_ids": [e["id"] for e in mock_cycle],
        "later_ids": [e["id"] for e in later_list],
        "gap_count": len(all_gaps),
        "config": config_label,
    }

    if dry_run:
        logger.info(
            "prep-personas draft dry-run: mock_cycle={} later={} gaps={} config={}",
            [e["id"] for e in mock_cycle],
            [e["id"] for e in later_list],
            len(all_gaps),
            config_label,
        )
        summary["mode"] = "dry-run"
        return summary

    if out_path.exists() and not force:
        raise FileExistsError(f"{out_path} exists — use --force to overwrite")

    md = render_draft_md(
        role_slug=role_slug,
        context_path=context_path,
        claims_path=claims_path,
        blocks=blocks,
        all_gaps=all_gaps,
        mock_cycle=mock_cycle,
        later_list=later_list,
        mock_order=mock_order,
        prep_roles_config_label=config_label,
        refine_config=refine_config,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")

    logger.info(
        "prep-personas draft: wrote {} (mock_cycle={} later={} gaps={})",
        out_path,
        [e["id"] for e in mock_cycle],
        [e["id"] for e in later_list],
        len(all_gaps),
    )
    summary["mode"] = "write"
    return summary
