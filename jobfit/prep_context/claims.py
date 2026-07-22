"""Draft Claim→Evidence markdown from CV text and optional prep context export."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from jobfit import config
from jobfit.prep_context.overlap import compute_cv_skills
from jobfit.roles import ROLES, Role

_GAP_LINES_FILE = "gap_lines.yaml"
_DRAFT_CLAIMS_FILE = "claims.draft.md"
_REVIEWED_CLAIMS_FILE = "claims.md"
_LLM_INPUT_BEGIN = "<!-- jobfit:prep-claims:llm-input -->"
_LLM_INPUT_END = "<!-- /jobfit:prep-claims:llm-input -->"
_DRAFT_FOOTER_HEADING = "## How this file is used"

_BLOCK_SPLIT_RE = re.compile(r"^### S\d+", re.MULTILINE)
_FIELD_RE = re.compile(r"^- ([a-z_]+):[ \t]*(.*)", re.MULTILINE)
_SKILLS_LINE_RE = re.compile(r"^\s*- (gaps_vs_cv|overlap_with_cv|must_have_skills): \[(.*)\]\s*$", re.MULTILINE)

_BULLET_RE = re.compile(r"^\s{2,}-\s+(.+)$", re.MULTILINE)

_PREP_FOR_GAPS = frozenset({"fit", "stretch", "brand-only"})


def default_gap_lines_path(role_slug: str) -> Path:
    """User-owned optional cache for Honest line text (gitignored input dir)."""
    return config.role_input_dir(role_slug) / _GAP_LINES_FILE


def default_draft_path(role_slug: str) -> Path:
    """Machine draft output from prep-claims draft."""
    return Path(f"prompts/prep/{role_slug}") / _DRAFT_CLAIMS_FILE


def default_reviewed_path(role_slug: str) -> Path:
    """Interview SoT after human verify (gaps merge target)."""
    return Path(f"prompts/prep/{role_slug}") / _REVIEWED_CLAIMS_FILE


def extract_llm_input(md_text: str) -> str:
    """Return claims body for LLM refine (between llm-input markers, excluding human footer)."""
    if _LLM_INPUT_BEGIN in md_text and _LLM_INPUT_END in md_text:
        start = md_text.index(_LLM_INPUT_BEGIN) + len(_LLM_INPUT_BEGIN)
        end = md_text.index(_LLM_INPUT_END)
        return md_text[start:end].strip()
    idx = md_text.find(_DRAFT_FOOTER_HEADING)
    if idx != -1:
        return md_text[:idx].strip()
    return md_text.strip()


def load_gap_lines(path: Path | None) -> dict[str, GapLineEntry]:
    """Load skill → gap line mapping from YAML. Returns {} if path is None or missing."""
    if path is None or not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"gap_lines YAML must be a mapping, got {type(data).__name__}: {path}")
    result: dict[str, GapLineEntry] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        if value is None:
            continue
        if isinstance(value, dict):
            entry = GapLineEntry(
                say_instead=str(
                    value.get("say_instead") or value.get("say") or ""
                ).strip(),
                do_not_claim=str(
                    value.get("do_not_claim") or value.get("do_not") or ""
                ).strip(),
            )
        else:
            entry = GapLineEntry(say_instead=str(value).strip())
        if entry.say_instead or entry.do_not_claim:
            result[key] = entry
    return result


@dataclass(frozen=True)
class SkillClaim:
    skill: str
    evidence: str
    status: str  # ok | weak | skip


@dataclass(frozen=True)
class StarredRow:
    sid: str
    title: str
    prep_label: str
    gaps: list[str]


@dataclass(frozen=True)
class GapLineEntry:
    say_instead: str = ""
    do_not_claim: str = ""


@dataclass(frozen=True)
class GapRow:
    skill: str
    count: int
    jobs: list[str]
    say_instead: str
    do_not_claim: str


def extract_experience_bullets(cv_text: str) -> list[str]:
    """Return experience bullet lines (trimmed), excluding skills-header one-liners."""
    start = cv_text.upper().find("PROFESSIONAL EXPERIENCE")
    end_markers = ("EDUCATION", "CERTIFICATIONS", "LANGUAGES", "ADDITIONAL INFORMATION")
    if start == -1:
        body = cv_text
    else:
        body = cv_text[start:]
        ends = [body.upper().find(m) for m in end_markers if body.upper().find(m) != -1]
        if ends:
            body = body[: min(ends)]

    bullets: list[str] = []
    for m in _BULLET_RE.finditer(body):
        text = m.group(1).strip()
        if len(text) > 40:
            bullets.append(text)
    return bullets


def _best_bullet_for_skill(skill: str, pattern: str, bullets: list[str]) -> str | None:
    pat = re.compile(pattern, re.IGNORECASE)
    matches = [b for b in bullets if pat.search(b)]
    if not matches:
        return None
    # Prefer bullets with numbers/metrics, then longest.
    def rank(b: str) -> tuple[int, int]:
        nums = len(re.findall(r"\d+", b))
        return (nums, len(b))

    return max(matches, key=rank)


def build_skill_claims(cv_text: str, role: Role) -> list[SkillClaim]:
    bullets = extract_experience_bullets(cv_text)
    cv_skills = compute_cv_skills(cv_text, role)
    claims: list[SkillClaim] = []

    for name, pattern in role.skills:
        if name not in cv_skills:
            continue
        bullet = _best_bullet_for_skill(name, pattern, bullets)
        if bullet:
            short = bullet if len(bullet) <= 220 else bullet[:217] + "..."
            claims.append(SkillClaim(name, short, "ok"))
        else:
            claims.append(
                SkillClaim(
                    name,
                    "Listed in CV skills section — no dedicated experience bullet matched",
                    "weak",
                )
            )

    return sorted(claims, key=lambda c: (c.status != "ok", c.skill.lower()))


def parse_starred_blocks(md_text: str) -> list[StarredRow]:
    """Parse ### S* blocks from prep context export markdown."""
    headers = list(_BLOCK_SPLIT_RE.finditer(md_text))
    if not headers:
        return []

    rows: list[StarredRow] = []
    for i, hdr in enumerate(headers):
        start = hdr.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(md_text)
        block = md_text[start:end]
        sid = hdr.group(0).replace("### ", "").strip()

        fields: dict[str, str] = {}
        for m in _FIELD_RE.finditer(block):
            fields[m.group(1)] = m.group(2).strip()

        gaps: list[str] = []
        for m in _SKILLS_LINE_RE.finditer(block):
            if m.group(1) == "gaps_vs_cv":
                raw = m.group(2).strip()
                if raw:
                    gaps = [s.strip() for s in raw.split(",") if s.strip()]
                break

        rows.append(
            StarredRow(
                sid=sid,
                title=fields.get("title", ""),
                prep_label=fields.get("prep_label", ""),
                gaps=gaps,
            )
        )
    return rows


def aggregate_gaps(
    rows: list[StarredRow],
    *,
    prep_labels: frozenset[str] = _PREP_FOR_GAPS,
    gap_lines: dict[str, str] | None = None,
) -> list[GapRow]:
    """Union gaps_vs_cv across starred jobs with selected prep_label values."""
    lines = gap_lines or {}
    counter: Counter[str] = Counter()
    jobs_by_skill: dict[str, list[str]] = {}

    for row in rows:
        label = row.prep_label.strip().lower()
        if label not in prep_labels:
            continue
        for skill in row.gaps:
            counter[skill] += 1
            jobs_by_skill.setdefault(skill, []).append(row.sid)

    result: list[GapRow] = []
    for skill, count in counter.most_common():
        entry = lines.get(skill, GapLineEntry())
        result.append(
            GapRow(
                skill=skill,
                count=count,
                jobs=sorted(set(jobs_by_skill.get(skill, []))),
                say_instead=entry.say_instead,
                do_not_claim=entry.do_not_claim,
            )
        )
    return result


def _md_cell(text: str) -> str:
    display = text.strip() if text.strip() else "—"
    return display.replace("|", "\\|")


def _render_claims_table(rows: list[SkillClaim] | list[Any], *, kind: str) -> list[str]:
    from jobfit.prep_context.claims_layout import LayoutRow

    lines: list[str] = []
    if kind == "weak":
        lines.extend(["| Skill | Note | Status |", "|---|---|---|"])
        for row in rows:
            if isinstance(row, LayoutRow):
                lines.append(f"| **{row.label}** | {_md_cell(row.evidence)} | {row.status} |")
            else:
                lines.append(f"| **{row.skill}** | {_md_cell(row.evidence)} | {row.status} |")
    elif kind == "certs":
        lines.extend(["| Claim | Evidence | Status |", "|---|---|---|"])
        for row in rows:
            lines.append(f"| **{row.label}** | {_md_cell(row.evidence)} | {row.status} |")
    else:
        lines.extend(
            ["| Claim (interview) | Evidence (CV bullet + metric) | Status |", "|---|---|---|"]
        )
        for row in rows:
            label = getattr(row, "label", None) or getattr(row, "skill", "")
            status = getattr(row, "status", "ok")
            evidence = getattr(row, "evidence", "")
            lines.append(f"| **{label}** | {_md_cell(evidence)} | {status} |")
    return lines


def render_gaps_block(
    *,
    layout_heading: str,
    layout_intro: str,
    gaps: list[GapRow],
    existing_gaps: dict[str, dict[str, str]] | None = None,
    gap_lines_path: Path | None = None,
) -> str:
    from jobfit.prep_context.claims_merge import _GAPS_END, _GAPS_START

    existing_gaps = existing_gaps or {}
    lines: list[str] = [
        _GAPS_START,
        layout_heading,
        "",
        layout_intro,
        "",
        "| Gap | Jobs | Count | Do not claim | Say instead |",
        "|---|---|---:|---|---|",
    ]
    for g in gaps:
        prev = existing_gaps.get(g.skill, {})
        jobs = ", ".join(g.jobs)
        do_not = g.do_not_claim or prev.get("do_not_claim", "")
        say = g.say_instead or prev.get("say_instead", "")
        lines.append(
            f"| **{g.skill}** | {jobs} | {g.count} | {_md_cell(do_not)} | {_md_cell(say)} |"
        )
    if gap_lines_path and gap_lines_path.is_file():
        lines.extend(
            [
                "",
                f"Say/do-not lines loaded from `{gap_lines_path.as_posix()}` where present.",
            ]
        )
    lines.append(_GAPS_END)
    return "\n".join(lines)


def render_claims_md(
    *,
    cv_path: Path,
    context_path: Path | None,
    role_slug: str,
    claims: list[SkillClaim],
    gaps: list[GapRow],
    gap_labels: frozenset[str],
    gap_lines_path: Path | None = None,
    cv_text: str | None = None,
) -> str:
    from jobfit.prep_context.claims_layout import build_layout_sections

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    layout = None
    if cv_text is not None:
        layout = build_layout_sections(cv_text, role_slug)

    lines: list[str] = [
        f"# Claim → Evidence ({role_slug})",
        "",
        f"**Draft** generated: {now}",
        f"**CV source:** `{cv_path.as_posix()}`",
    ]
    if layout and layout.source_path:
        lines.append(f"**Layout:** `{layout.source_path.as_posix()}`")
    if context_path:
        lines.append(f"**Context source:** `{context_path.as_posix()}`")
        lines.append(f"**Gaps scope:** prep_label ∈ {', '.join(sorted(gap_labels))}")
    lines.extend(
        [
            "",
            "> Next: LLM refine (Step 1) → human verify (Step 2) → claims.md. See docs/prep-claims-review.md."
            " Gaps Jobs/Count: `--merge` on reviewed file.",
            "",
            "**Status:** `ok` = bullet matched · `weak` = skills list or thin evidence · edit freely",
            "",
            "---",
            "",
            _LLM_INPUT_BEGIN,
            "",
        ]
    )

    body_lines: list[str] = []

    if layout is not None:
        for section in layout.sections:
            body_lines.append(f"## {section.title}")
            body_lines.append("")
            body_lines.extend(_render_claims_table(section.rows, kind=section.kind))
            body_lines.extend(["", "---", ""])
    else:
        body_lines.extend(["## Claims (from CV)", ""])
        ok_claims = [c for c in claims if c.status == "ok"]
        weak_claims = [c for c in claims if c.status == "weak"]
        body_lines.extend(_render_claims_table(ok_claims, kind="claims"))
        if weak_claims:
            body_lines.extend(["", "## Skills in CV — weak evidence", ""])
            body_lines.extend(_render_claims_table(weak_claims, kind="weak"))

    if gaps:
        heading = layout.gaps_heading if layout else "## Gaps vs prep shortlist (honest transfer lines)"
        intro = (
            layout.gaps_intro
            if layout
            else "Union of gaps_vs_cv from fit/stretch/brand-only starred jobs."
        )
        body_lines.append(
            render_gaps_block(
                layout_heading=heading,
                layout_intro=intro,
                gaps=gaps,
                gap_lines_path=gap_lines_path if gap_lines_path and gap_lines_path.is_file() else None,
            )
        )
        body_lines.append("")

    hard_stop = (
        layout.do_not_claim_hard_stop
        if layout
        else [
            "Skills marked `weak` above unless you add a CV bullet",
            "Anything from demo `data/user/{role}/input/CV_*.md` not present in interview CV",
            "Cloud platforms listed in Gaps at production depth",
        ]
    )
    body_lines.extend(["---", "", "## Do not claim (hard stop)", ""])
    for item in hard_stop:
        body_lines.append(f"- {item.format(role=role_slug)}")

    if layout and layout.quick_reference:
        body_lines.extend(["", "---", "", "## Quick reference — best bullets by interview theme", ""])
        body_lines.append("| Theme | Lead bullet |")
        body_lines.append("|---|---|")
        for theme, hint in layout.quick_reference:
            body_lines.append(f"| {theme} | {_md_cell(hint)} |")

    lines.extend(body_lines)
    lines.extend(
        [
            "",
            _LLM_INPUT_END,
            "",
            "---",
            "",
            _DRAFT_FOOTER_HEADING,
            "",
            "1. **Any interview** — pick `ok` rows; do not invent beyond Evidence.",
            "2. **Specific application** — read that job's `gaps_vs_cv` in `context.md`.",
            "3. **Stories (Phase 2)** — expand one `ok` row into STAR in `stories.md`.",
            "",
            "Refresh gap counts on reviewed claims (preserves Claims tables):",
            "",
            "```bash",
            f"jobfit prep-claims draft --role {role_slug} --merge",
            "```",
            "",
            "Regenerate machine draft (overwrites claims.draft.md):",
            "",
            "```bash",
            f"jobfit prep-claims draft --role {role_slug} --force",
            "```",
            "",
            "LLM refine (requires PREP_CLAIMS_* or LLM_* API key):",
            "",
            "```bash",
            f"jobfit prep-claims refine --role {role_slug} --force",
            "```",
            "",
            "After LLM + verify, promote to SoT:",
            "",
            "```bash",
            f"cp prompts/prep/{role_slug}/claims.llm.md prompts/prep/{role_slug}/claims.md",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def run(
    *,
    role_slug: str,
    cv_path: Path,
    context_path: Path | None,
    out_path: Path,
    gap_lines_path: Path | None = None,
    prep_labels: frozenset[str] = _PREP_FOR_GAPS,
    dry_run: bool = False,
    force: bool = False,
    merge: bool = False,
) -> dict[str, Any]:
    from loguru import logger

    from jobfit.prep_context.claims_layout import build_layout_sections, load_layout
    from jobfit.prep_context.claims_merge import (
        is_reviewed_claims,
        merge_gaps_block,
        parse_gaps_table,
    )

    role = ROLES[role_slug]
    if not cv_path.is_file():
        raise FileNotFoundError(f"CV not found: {cv_path}")

    cv_text = cv_path.read_text(encoding="utf-8")
    claims = build_skill_claims(cv_text, role)
    layout = load_layout(role_slug)

    gap_lines = load_gap_lines(gap_lines_path)

    gaps: list[GapRow] = []
    if context_path is not None:
        if not context_path.is_file():
            raise FileNotFoundError(f"Context not found: {context_path}")
        rows = parse_starred_blocks(context_path.read_text(encoding="utf-8"))
        gaps = aggregate_gaps(rows, prep_labels=prep_labels, gap_lines=gap_lines)

    summary: dict[str, Any] = {
        "claims_ok": sum(1 for c in claims if c.status == "ok"),
        "claims_weak": sum(1 for c in claims if c.status == "weak"),
        "gaps": len(gaps),
        "out": str(out_path),
        "layout": str(layout.source_path) if layout and layout.source_path else None,
        "mode": "dry-run",
    }

    if layout and layout.source_path:
        logger.debug("prep-claims layout: {}", layout.source_path)

    if dry_run:
        if layout:
            built = build_layout_sections(cv_text, role_slug)
            if built:
                summary["claims_ok"] = sum(
                    1 for sec in built.sections for row in sec.rows if row.status == "ok"
                )
                summary["claims_weak"] = sum(
                    1 for sec in built.sections for row in sec.rows if row.status == "weak"
                )
        logger.info(
            "prep-claims draft dry-run: ok={} weak={} gaps={} layout={}",
            summary["claims_ok"],
            summary["claims_weak"],
            summary["gaps"],
            summary["layout"],
        )
        return summary

    existing = out_path.read_text(encoding="utf-8") if out_path.is_file() else ""
    auto_merge = bool(existing) and not force and (merge or is_reviewed_claims(existing))

    if out_path.exists() and not force and not auto_merge:
        raise FileExistsError(
            f"{out_path} exists — use --merge to refresh gaps only, or --force to regenerate"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if auto_merge:
        if not gaps:
            logger.warning("prep-claims merge: no gaps to update (missing --context?)")
            return {**summary, "mode": "merge-skipped"}

        layout_heading = (
            layout.gaps_heading if layout else "## Gaps vs prep shortlist (honest transfer lines)"
        )
        layout_intro = (
            layout.gaps_intro
            if layout
            else "Union of gaps_vs_cv from fit/stretch/brand-only starred jobs."
        )
        preserved = parse_gaps_table(existing)
        gaps_block = render_gaps_block(
            layout_heading=layout_heading,
            layout_intro=layout_intro,
            gaps=gaps,
            existing_gaps=preserved,
            gap_lines_path=gap_lines_path if gap_lines else None,
        )
        merged = merge_gaps_block(existing, gaps_block)
        out_path.write_text(merged, encoding="utf-8")
        logger.info(
            "prep-claims merge: updated gaps in {} ({} rows)",
            out_path,
            len(gaps),
        )
        return {**summary, "mode": "merge"}

    md = render_claims_md(
        cv_path=cv_path,
        context_path=context_path,
        role_slug=role_slug,
        claims=claims,
        gaps=gaps,
        gap_labels=prep_labels,
        gap_lines_path=gap_lines_path if gap_lines else None,
        cv_text=cv_text,
    )
    out_path.write_text(md, encoding="utf-8")
    if layout:
        built = build_layout_sections(cv_text, role_slug)
        if built:
            summary["claims_ok"] = sum(
                1 for sec in built.sections for row in sec.rows if row.status == "ok"
            )
            summary["claims_weak"] = sum(
                1 for sec in built.sections for row in sec.rows if row.status == "weak"
            )
    logger.info(
        "prep-claims draft: wrote {} (ok={} weak={} gaps={} layout={})",
        out_path,
        summary["claims_ok"],
        summary["claims_weak"],
        summary["gaps"],
        summary["layout"],
    )
    return {**summary, "mode": "write"}
