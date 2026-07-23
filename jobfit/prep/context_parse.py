"""Richer context block parser for prep-personas pipeline.

Extends the minimal StarredRow used by claims.py with all fields needed for
personas draft generation: company, jd_excerpt, work_mode, language, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Same regex patterns as claims.py — defined here to avoid coupling
_BLOCK_SPLIT_RE = re.compile(r"^### S\d+", re.MULTILINE)
_FIELD_RE = re.compile(r"^- ([a-z_]+):[ \t]*(.*)", re.MULTILINE)
_SKILLS_LINE_RE = re.compile(
    r"^\s*- (gaps_vs_cv|overlap_with_cv|must_have_skills): \[(.*)\]\s*$",
    re.MULTILINE,
)
_COMPOUND_TYPE_RE = re.compile(
    r"^- company_type / stage / industry:[ \t]*(.+)$", re.MULTILINE
)
_COMPOUND_WORK_RE = re.compile(
    r"^- work_mode / on_call / german_level / english_ok:[ \t]*(.+)$", re.MULTILINE
)
_STARRED_SECTION_RE = re.compile(r"^## Starred jobs\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ContextBlock:
    sid: str
    refnr: str = ""
    title: str = ""
    company: str = ""
    prep_label: str = ""
    why_starred: str = ""
    gaps_vs_cv: tuple[str, ...] = ()
    jd_excerpt: str = ""
    company_type: str = ""
    company_stage: str = ""
    industry: str = ""
    work_mode: str = ""
    on_call: bool = False
    german_level: str = ""
    english_ok: bool = True
    prep_heuristic: str = ""


def parse_context_blocks(md_text: str) -> list[ContextBlock]:
    """Parse ### S* blocks from prep context export markdown, extracting all fields."""
    m = _STARRED_SECTION_RE.search(md_text)
    if m:
        md_text = md_text[m.start():]

    headers = list(_BLOCK_SPLIT_RE.finditer(md_text))
    if not headers:
        return []

    blocks: list[ContextBlock] = []
    for i, hdr in enumerate(headers):
        start = hdr.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(md_text)
        block_text = md_text[start:end]
        sid = hdr.group(0).replace("### ", "").strip()

        fields: dict[str, str] = {}
        for fm in _FIELD_RE.finditer(block_text):
            fields[fm.group(1)] = fm.group(2).strip()

        gaps: list[str] = []
        for sm in _SKILLS_LINE_RE.finditer(block_text):
            if sm.group(1) == "gaps_vs_cv":
                raw = sm.group(2).strip()
                if raw:
                    gaps = [s.strip() for s in raw.split(",") if s.strip()]
                break

        # Compound: company_type / stage / industry
        company_type = company_stage = industry = ""
        cm = _COMPOUND_TYPE_RE.search(block_text)
        if cm:
            parts = [p.strip() for p in cm.group(1).split("/", 2)]
            company_type = parts[0] if len(parts) > 0 else ""
            company_stage = parts[1] if len(parts) > 1 else ""
            industry = parts[2] if len(parts) > 2 else ""

        # Compound: work_mode / on_call / german_level / english_ok
        work_mode = german_level = ""
        on_call = False
        english_ok = True
        wm = _COMPOUND_WORK_RE.search(block_text)
        if wm:
            parts = [p.strip() for p in wm.group(1).split("/")]
            work_mode = parts[0] if len(parts) > 0 else ""
            on_call = parts[1].lower() == "true" if len(parts) > 1 else False
            german_level = parts[2] if len(parts) > 2 else ""
            english_ok = parts[3].lower() == "true" if len(parts) > 3 else True

        blocks.append(
            ContextBlock(
                sid=sid,
                refnr=fields.get("refnr", ""),
                title=fields.get("title", ""),
                company=fields.get("company", ""),
                prep_label=fields.get("prep_label", ""),
                why_starred=fields.get("why_starred", ""),
                gaps_vs_cv=tuple(gaps),
                jd_excerpt=fields.get("jd_excerpt", ""),
                company_type=company_type,
                company_stage=company_stage,
                industry=industry,
                work_mode=work_mode,
                on_call=on_call,
                german_level=german_level,
                english_ok=english_ok,
                prep_heuristic=fields.get("prep_heuristic", ""),
            )
        )

    return blocks
