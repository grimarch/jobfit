"""Merge prep-claims Gaps section into an existing claims.md without touching other sections."""

from __future__ import annotations

import re

_GAPS_START = "<!-- jobfit:prep-claims:gaps -->"
_GAPS_END = "<!-- /jobfit:prep-claims:gaps -->"

_MARKED_BLOCK_RE = re.compile(
    re.escape(_GAPS_START) + r"(.*?)" + re.escape(_GAPS_END),
    re.DOTALL,
)

# Legacy / alternate headings from reviewed files.
_GAPS_HEADING_RE = re.compile(r"^## Gaps vs[^\n]*$", re.MULTILINE)

_GAP_ROW_RE = re.compile(
    r"^\|\s*\*\*(?P<skill>[^*|]+)\*\*\s*\|(?P<rest>.*)$",
    re.MULTILINE,
)


def parse_gaps_table(md_text: str) -> dict[str, dict[str, str]]:
    """Parse gap rows from markdown table. Keys: do_not_claim, say_instead, jobs, count."""
    section = _extract_gaps_section(md_text)
    if not section:
        return {}

    result: dict[str, dict[str, str]] = {}
    for line in section.splitlines():
        m = _GAP_ROW_RE.match(line.strip())
        if not m:
            continue
        skill = m.group("skill").strip()
        cols = [c.strip() for c in m.group("rest").split("|")]
        cols = [c for c in cols if c != ""]

        entry: dict[str, str] = {}
        if len(cols) == 2:
            # Gap | Do not claim | Say instead  (3-col body after skill)
            entry["do_not_claim"] = cols[0] if cols[0] != "—" else ""
            entry["say_instead"] = cols[1] if cols[1] != "—" else ""
        elif len(cols) == 3:
            # Jobs | Count | Honest line
            entry["jobs"] = cols[0]
            entry["count"] = cols[1]
            entry["say_instead"] = cols[2] if cols[2] != "—" else ""
        elif len(cols) >= 4:
            # Jobs | Count | Do not claim | Say instead
            entry["jobs"] = cols[0]
            entry["count"] = cols[1]
            entry["do_not_claim"] = cols[2] if cols[2] != "—" else ""
            entry["say_instead"] = cols[3] if cols[3] != "—" else ""

        result[skill] = entry
    return result


def _extract_gaps_section(md_text: str) -> str:
    marked = _MARKED_BLOCK_RE.search(md_text)
    if marked:
        return marked.group(1)

    heading = _GAPS_HEADING_RE.search(md_text)
    if not heading:
        return ""

    tail = md_text[heading.start() :]
    end = re.search(r"\n---\n\n## Do not claim", tail)
    if end:
        return tail[: end.start()]
    return tail


def merge_gaps_block(existing_md: str, new_block: str) -> str:
    """Replace gaps section in existing_md with new_block (includes markers)."""
    if _GAPS_START in existing_md and _GAPS_END in existing_md:
        return _MARKED_BLOCK_RE.sub(new_block, existing_md, count=1)

    heading = _GAPS_HEADING_RE.search(existing_md)
    if heading:
        tail = existing_md[heading.start() :]
        end = re.search(r"\n---\n\n## Do not claim", tail)
        if end:
            before = existing_md[: heading.start()]
            after = existing_md[heading.start() + end.start() :]
            return before + new_block.strip() + "\n" + after

    # No gaps section yet — insert before Do not claim or append.
    insert_at = re.search(r"\n---\n\n## Do not claim", existing_md)
    if insert_at:
        return (
            existing_md[: insert_at.start()]
            + "\n\n"
            + new_block.strip()
            + "\n"
            + existing_md[insert_at.start() :]
        )
    return existing_md.rstrip() + "\n\n" + new_block.strip() + "\n"


def is_reviewed_claims(md_text: str) -> bool:
    return "**Reviewed:**" in md_text or "**Phase 0c**" in md_text
