"""Draft prep stories (Phase 2) from context + claims + personas — no LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from jobfit.config import USER_DATA_DIR
from jobfit.prep.context_parse import ContextBlock, parse_context_blocks
from jobfit.prep.personas.draft import (
    load_prep_roles_yaml,
    require_reviewed_claims,
    validate_prep_roles_yaml,
    _build_roles_from_yaml,
)
from jobfit.prep.stories.enrichment import (
    StoryEnrichment,
    format_employer_context,
    load_enrichment,
    default_enrichment_path,
)
from jobfit.prep.stories.slots import CATALOG, MOCK_STORY_ORDER, StorySlot, stories_for_mock

_DRAFT_STORIES_FILE = "stories.draft.md"
_REVIEWED_MARKER = "**Reviewed:**"
_DRAFT_MARKER = "**Draft** generated:"
_LLM_INPUT_BEGIN = "<!-- jobfit:prep-stories:llm-input -->"
_LLM_INPUT_END = "<!-- /jobfit:prep-stories:llm-input -->"
_DRAFT_FOOTER_HEADING = "## How this file is used"

# Metric extraction patterns: (regex, normalizer)
_METRIC_PATTERNS: list[tuple[re.Pattern[str], Any]] = [
    (
        re.compile(r"(\d+)\s+minutes?\s+to\s+(\d+)\s+minutes?"),
        lambda m: f"{m.group(1)}→{m.group(2)} min",
    ),
    (
        re.compile(r"(\d+)[–\-](\d+)\s+min(?:utes?)?(?!\s+to)"),
        lambda m: f"{m.group(1)}–{m.group(2)} min",
    ),
    (
        re.compile(r"\d+-node"),
        lambda m: m.group(0),
    ),
    (
        re.compile(r"(\d+)\+\s*(?:monitored\s+|production\s+|prod(?:uction)?\s+)?hosts?"),
        lambda m: f"{m.group(1)}+ hosts",
    ),
    (
        re.compile(r"(\d+)\s+(?:Terraform-managed\s+)?resources?(?!\s+across)"),
        lambda m: f"{m.group(1)} resources",
    ),
    (
        re.compile(r"(\d+)\s+project\s+stacks?"),
        lambda m: f"{m.group(1)} stacks",
    ),
    (
        re.compile(r"(\d+)\s+feeds?"),
        lambda m: f"{m.group(1)} feeds",
    ),
    (
        re.compile(r"(\d+)[–\-](\d+)\s+minutes?(?:\s+per\s+analysis)?"),
        lambda m: f"{m.group(1)}–{m.group(2)} min",
    ),
    (
        re.compile(r"(\d+)[–\-](\d+)\s+hours?\s+per\s+week"),
        lambda m: f"{m.group(1)}–{m.group(2)} h/week",
    ),
]


def extract_metrics(text: str) -> list[str]:
    """Extract and normalize locked metric phrases from evidence text."""
    seen: set[str] = set()
    result: list[str] = []
    for pattern, normalizer in _METRIC_PATTERNS:
        for m in pattern.finditer(text):
            normalized = normalizer(m)
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
    return result


# --- Claims evidence parsing ---

_CLAIM_ROW_RE = re.compile(
    r"^\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|\s*(?:ok|weak)\s*\|",
    re.MULTILINE,
)


def parse_claims_evidence(claims_text: str) -> dict[str, str]:
    """Parse all claims.md tables → {claim_label: evidence_text}."""
    result: dict[str, str] = {}
    for m in _CLAIM_ROW_RE.finditer(claims_text):
        label = m.group(1).strip()
        evidence = m.group(2).strip()
        result[label] = evidence
    return result


def evidence_for_slot(
    slot: StorySlot, evidence_map: dict[str, str]
) -> tuple[str, list[str]]:
    """Return (combined_evidence_text, locked_metrics) for a story slot."""
    parts: list[str] = []
    for label in slot.claims_labels:
        ev = evidence_map.get(label, "")
        if ev:
            parts.append(ev)
    combined = " ¶ ".join(parts) if parts else "—"
    metrics = extract_metrics(combined)
    return combined, metrics


# --- Personas parsing ---


@dataclass(frozen=True)
class PersonaSection:
    sid: str
    jd_focus: str
    mock_traps: str
    language: str
    stories_to_write: str


_PERSONA_SECTION_RE = re.compile(r"^## (S\d+)\b", re.MULTILINE)


def _extract_field(text: str, field_name: str) -> str:
    """Extract single-line **Field:** value from section text."""
    pattern = re.compile(
        rf"\*\*{re.escape(field_name)}:\*\*\s*(.+?)(?=\n(?:\*\*|\n|---|## |\Z))",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return ""
    return m.group(1).strip()


def _extract_stories_block(text: str) -> str:
    """Extract numbered stories list under **Stories to write (Phase 2):**."""
    marker = "**Stories to write (Phase 2):**"
    if marker not in text:
        return ""
    rest = text.split(marker, 1)[1]
    # Take until next section boundary
    end = re.search(r"^(?:---|\*\*|##)", rest, re.MULTILINE)
    block = rest[: end.start()] if end else rest
    lines = [ln for ln in block.strip().splitlines() if re.match(r"^\d+\.", ln.strip())]
    return "\n".join(lines)


def parse_personas_sections(personas_text: str) -> dict[str, PersonaSection]:
    """Parse refined personas.md → per-sid PersonaSection."""
    result: dict[str, PersonaSection] = {}
    starts = list(_PERSONA_SECTION_RE.finditer(personas_text))
    for i, match in enumerate(starts):
        sid = match.group(1)
        start = match.start()
        end = starts[i + 1].start() if i + 1 < len(starts) else len(personas_text)
        section = personas_text[start:end]
        result[sid] = PersonaSection(
            sid=sid,
            jd_focus=_extract_field(section, "JD focus"),
            mock_traps=_extract_field(section, "Mock traps"),
            language=_extract_field(section, "Language"),
            stories_to_write=_extract_stories_block(section),
        )
    return result


# --- Default paths ---


def default_draft_path(role_slug: str) -> Path:
    return Path(f"prompts/prep/{role_slug}") / _DRAFT_STORIES_FILE


def default_claims_path(role_slug: str) -> Path:
    return Path(f"prompts/prep/{role_slug}") / "claims.md"


def default_personas_path(role_slug: str) -> Path:
    return Path(f"prompts/prep/{role_slug}") / "personas.md"


def default_context_path(role_slug: str) -> Path:
    return Path(f"prompts/prep/{role_slug}") / "context.md"


def default_prep_roles_yaml_path(role_slug: str) -> Path:
    return USER_DATA_DIR / role_slug / "input" / "prep_roles.yaml"


# --- Rendering ---


def _md_cell(text: str) -> str:
    s = text.strip() if text.strip() else "—"
    # Collapse newlines — markdown tables don't support multi-line cells
    s = " ".join(line.strip() for line in s.splitlines() if line.strip())
    return s.replace("|", "\\|")


def render_story_block(
    *,
    slot: StorySlot,
    mock_id: str,
    order: int,
    evidence: str,
    metrics: list[str],
    persona: PersonaSection | None,
    enrichment: StoryEnrichment,
    story_override: Any | None,
) -> str:
    """Render a single story block (marker + Input table + TODO Output)."""
    lines: list[str] = []

    # Story marker
    lines.append(
        f'<!-- jobfit:prep-stories:story id="{slot.id}" mock="{mock_id}" order="{order}" -->'
    )
    lines.append("")

    # Section heading
    opt_tag = " *(optional)*" if slot.optional else ""
    title_text = slot.title + opt_tag
    if story_override and story_override.optional is True and not slot.optional:
        title_text = slot.title + " *(optional via enrichment)*"
    lines.append(f"### {order}. {title_text}")
    lines.append("")
    lines.append("**Input:**")
    lines.append("")

    # Input table
    claims_label_str = " · ".join(slot.claims_labels)
    metrics_str = ", ".join(f"`{m}`" for m in metrics) if metrics else "—"
    mock_angle = persona.jd_focus if persona and persona.jd_focus else "—"
    traps_str = persona.mock_traps if persona and persona.mock_traps else "—"
    lang_str = persona.language if persona and persona.language else "—"
    emp_ctx = format_employer_context(slot.work_comp, enrichment)
    story_comment = (story_override.comment if story_override and story_override.comment else "—")

    lines.append("| Field | Content |")
    lines.append("|-------|---------|")
    lines.append(f"| **Story id** | `{slot.id}` |")
    lines.append(f"| **Claims** | {_md_cell(claims_label_str)} |")
    lines.append(f"| **Evidence** | {_md_cell(evidence)} |")
    lines.append(f"| **Metrics (locked)** | {_md_cell(metrics_str)} |")
    lines.append(f"| **Mock angle** | {_md_cell(mock_angle)} |")
    lines.append(f"| **Traps** | {_md_cell(traps_str)} |")
    lines.append(f"| **Language** | {_md_cell(lang_str)} |")
    lines.append(f"| **Employer context** | {_md_cell(emp_ctx)} |")
    lines.append(f"| **Human story comment** | {_md_cell(story_comment)} |")

    lines.append("")
    lines.append("**Say (EN):** _TODO — run prep-stories refine_")
    lines.append("")
    lines.append("**Sag (DE):** _TODO — run prep-stories refine_")
    lines.append("")
    lines.append("> **Notes:** _TODO — run prep-stories refine_")
    lines.append("")
    lines.append("<!-- /jobfit:prep-stories:story -->")
    return "\n".join(lines)


def render_draft_md(
    *,
    role_slug: str,
    context_path: Path,
    claims_path: Path,
    personas_path: Path,
    prep_roles_config_label: str,
    enrichment_label: str,
    blocks: list[ContextBlock],
    evidence_map: dict[str, str],
    persona_sections: dict[str, PersonaSection],
    mock_cycle: list[dict[str, Any]],
    mock_order: list[str],
    enrichment: StoryEnrichment,
) -> str:
    """Render stories.draft.md from parsed inputs."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    blocks_by_sid = {b.sid: b for b in blocks}

    lines: list[str] = [
        f"# Stories draft ({role_slug})",
        "",
        f"**Draft** generated: {now}",
        f"**Context source:** `{context_path.as_posix()}`",
        f"**Claims source:** `{claims_path.as_posix()}`",
        f"**Personas source:** `{personas_path.as_posix()}`",
        f"**Prep roles config:** `{prep_roles_config_label}`",
        f"**Enrichment:** `{enrichment_label}`",
        "",
        "> Machine draft — no LLM. Input facts verified from Phase 0–1 artifacts.",
        "> Run `prep-stories refine` then human verify before promoting to `stories.md`.",
        "",
        "---",
        "",
        _LLM_INPUT_BEGIN,
        "",
    ]

    # Mock cycle — grouped sections
    for mock_entry in mock_cycle:
        mock_id = mock_entry["id"]
        if mock_id not in mock_order:
            continue

        block = blocks_by_sid.get(mock_id)
        persona = persona_sections.get(mock_id)
        archetype = mock_entry.get("archetype", "")
        label = mock_entry.get("label", mock_id)

        section_title = f"## Mock {mock_id} — {label}"
        if archetype:
            section_title += f" ({archetype})"

        # Build rehearsal order line
        slots = stories_for_mock(mock_id)
        rehearsal_parts: list[str] = []
        for s in slots:
            t = s.title.split("(")[0].strip()  # short title before parenthesized metric
            rehearsal_parts.append(t + " *(optional)*" if s.optional else t)
        rehearsal_line = " → ".join(rehearsal_parts)

        lines.extend([section_title, ""])
        lines.append(f"**Rehearsal order:** {rehearsal_line}")
        lines.append(
            f"**Gaps:** see [personas.md](personas.md) {mock_id} section"
        )
        lines.append("")

        # Per-story blocks
        for local_idx, slot in enumerate(slots, 1):
            override = enrichment.stories.get(slot.id)
            evidence, metrics = evidence_for_slot(slot, evidence_map)
            story_md = render_story_block(
                slot=slot,
                mock_id=mock_id,
                order=local_idx,
                evidence=evidence,
                metrics=metrics,
                persona=persona,
                enrichment=enrichment,
                story_override=override,
            )
            lines.append(story_md)
            lines.append("")
            lines.append("---")
            lines.append("")

    lines.extend([
        _LLM_INPUT_END,
        "",
        "---",
        "",
        _DRAFT_FOOTER_HEADING,
        "",
        "- `prep-stories refine` reads content between `llm-input` markers.",
        "- Human promotes `stories.llm.md` → `stories.md` after verify.",
        "- See `docs/prep-stories-review.md` (to be created with Phase 2).",
        "",
    ])

    return "\n".join(lines)


def run(
    *,
    role_slug: str,
    context_path: Path,
    claims_path: Path,
    personas_path: Path,
    out_path: Path,
    prep_roles_path: Path | None = None,
    enrichment_path: Path | None = None,
    require_reviewed: bool = True,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    if not context_path.is_file():
        raise FileNotFoundError(f"Context not found: {context_path}")
    if not claims_path.is_file():
        raise FileNotFoundError(f"Claims not found: {claims_path}")
    if not personas_path.is_file():
        raise FileNotFoundError(f"Personas not found: {personas_path}")

    claims_text = claims_path.read_text(encoding="utf-8")
    context_text = context_path.read_text(encoding="utf-8")
    personas_text = personas_path.read_text(encoding="utf-8")

    if require_reviewed:
        require_reviewed_claims(claims_text, claims_path)

    # Load prep_roles.yaml (required — same as personas)
    yaml_path = prep_roles_path or default_prep_roles_yaml_path(role_slug)
    prep_roles_config = load_prep_roles_yaml(yaml_path)
    if prep_roles_config is None:
        raise FileNotFoundError(
            f"prep_roles.yaml not found at {yaml_path} — "
            f"copy data/user/{role_slug}/input/prep_roles.yaml.example"
        )

    blocks = parse_context_blocks(context_text)
    blocks_by_sid = {b.sid: b for b in blocks}
    validate_prep_roles_yaml(prep_roles_config, blocks_by_sid)
    mock_cycle, _ = _build_roles_from_yaml(prep_roles_config, blocks_by_sid)
    mock_order: list[str] = [
        str(sid) for sid in prep_roles_config.get("mock_order", [e["id"] for e in mock_cycle])
    ]

    evidence_map = parse_claims_evidence(claims_text)
    persona_sections = parse_personas_sections(personas_text)

    # Enrichment (optional)
    epath = enrichment_path or default_enrichment_path(role_slug)
    enrichment = load_enrichment(epath if epath.is_file() else None)
    enrichment_label = epath.as_posix() if epath.is_file() else "—"

    # Count stories
    story_count = sum(
        len(stories_for_mock(mock_entry["id"]))
        for mock_entry in mock_cycle
        if mock_entry["id"] in mock_order
    )

    summary: dict[str, Any] = {
        "role": role_slug,
        "context": str(context_path),
        "claims": str(claims_path),
        "personas": str(personas_path),
        "out": str(out_path),
        "mock_ids": mock_order,
        "story_count": story_count,
        "evidence_claim_count": len(evidence_map),
        "persona_section_count": len(persona_sections),
        "enrichment": enrichment_label,
    }

    if dry_run:
        logger.info(
            "prep-stories draft dry-run: role={} mocks={} stories={} evidence_rows={}",
            role_slug,
            mock_order,
            story_count,
            len(evidence_map),
        )
        summary["mode"] = "dry-run"
        return summary

    if out_path.exists() and not force:
        raise FileExistsError(f"{out_path} exists — use --force to overwrite")

    md = render_draft_md(
        role_slug=role_slug,
        context_path=context_path,
        claims_path=claims_path,
        personas_path=personas_path,
        prep_roles_config_label=yaml_path.as_posix(),
        enrichment_label=enrichment_label,
        blocks=blocks,
        evidence_map=evidence_map,
        persona_sections=persona_sections,
        mock_cycle=mock_cycle,
        mock_order=mock_order,
        enrichment=enrichment,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")

    logger.info(
        "prep-stories draft: wrote {} (mocks={} stories={} evidence_rows={})",
        out_path,
        mock_order,
        story_count,
        len(evidence_map),
    )
    summary["mode"] = "write"
    return summary


def extract_llm_input(md_text: str) -> str:
    """Return stories body for LLM refine (between llm-input markers)."""
    if _LLM_INPUT_BEGIN in md_text and _LLM_INPUT_END in md_text:
        start = md_text.index(_LLM_INPUT_BEGIN) + len(_LLM_INPUT_BEGIN)
        end = md_text.index(_LLM_INPUT_END)
        return md_text[start:end].strip()
    idx = md_text.find(_DRAFT_FOOTER_HEADING)
    if idx != -1:
        return md_text[:idx].strip()
    return md_text.strip()
