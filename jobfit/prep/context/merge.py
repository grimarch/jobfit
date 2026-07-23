"""Parse human-edited fields from an existing prep context Markdown file.

Used during re-export to preserve why_starred and prep_label values that the
user filled in, keyed by refnr.
"""

from __future__ import annotations

import re

# Matches the start of a starred job block.
_BLOCK_SPLIT_RE = re.compile(r"^### S\d+", re.MULTILINE)

# Matches a simple `- key: value` list item (single-word key with underscores).
_FIELD_RE = re.compile(r"^- ([a-z_]+):[ \t]*(.*)", re.MULTILINE)

_HUMAN_KEYS = frozenset({"why_starred", "prep_label"})


def parse_human_fields(md_text: str) -> dict[str, dict[str, str]]:
    """Return {refnr: {"why_starred": "...", "prep_label": "..."}} from existing md.

    Only preserves fields the human is expected to fill in; all machine-generated
    fields are intentionally ignored so they get recalculated on re-export.
    Blocks with a missing or placeholder refnr ("-") are skipped.
    """
    result: dict[str, dict[str, str]] = {}

    # Split on block headers; first element is the preamble, skip it.
    blocks = _BLOCK_SPLIT_RE.split(md_text)[1:]

    for block in blocks:
        fields: dict[str, str] = {}
        for m in _FIELD_RE.finditer(block):
            key, value = m.group(1), m.group(2).strip()
            fields[key] = value

        refnr = fields.get("refnr", "")
        if not refnr or refnr == "-":
            continue

        result[refnr] = {k: fields.get(k, "") for k in _HUMAN_KEYS}

    return result
