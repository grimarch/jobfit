"""Unit tests for prep context merge parser."""

from __future__ import annotations

from jobfit.prep.context.merge import parse_human_fields

# ── Fixtures ──────────────────────────────────────────────────────────────────

_MD_WITH_VALUES = """\
# Prep context (anonymized)
Generated: 2026-07-19T00:00:00Z

## Starred jobs
### S1
- refnr: REF-001
- title: DevOps Engineer
- prep_heuristic: fit
- agency_suspect: false
- prep_label: fit
- why_starred: great stack and remote culture

### S2
- refnr: REF-002
- title: Platform Engineer
- prep_heuristic: stretch
- agency_suspect: false
- prep_label: stretch
- why_starred: interesting infra challenge

## How to use
- Fill in `why_starred` and `prep_label` for each job.
"""

_MD_EMPTY_SLOTS = """\
## Starred jobs
### S1
- refnr: REF-010
- title: SRE
- prep_heuristic: fit
- prep_label:
- why_starred:
"""

_MD_MISSING_REFNR = """\
## Starred jobs
### S1
- refnr: -
- title: Unknown
- prep_label: fit
- why_starred: oops
"""

_MD_NO_BLOCKS = """\
# Prep context (anonymized)
Generated: 2026-07-19T00:00:00Z

## How to use
- Fill in `why_starred`.
"""


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_parse_extracts_why_starred():
    result = parse_human_fields(_MD_WITH_VALUES)
    assert result["REF-001"]["why_starred"] == "great stack and remote culture"


def test_parse_extracts_prep_label():
    result = parse_human_fields(_MD_WITH_VALUES)
    assert result["REF-001"]["prep_label"] == "fit"


def test_parse_multiple_blocks():
    result = parse_human_fields(_MD_WITH_VALUES)
    assert set(result.keys()) == {"REF-001", "REF-002"}
    assert result["REF-002"]["why_starred"] == "interesting infra challenge"
    assert result["REF-002"]["prep_label"] == "stretch"


def test_parse_empty_slots_yield_empty_strings():
    result = parse_human_fields(_MD_EMPTY_SLOTS)
    assert result["REF-010"]["why_starred"] == ""
    assert result["REF-010"]["prep_label"] == ""


def test_parse_skips_placeholder_refnr():
    result = parse_human_fields(_MD_MISSING_REFNR)
    assert "-" not in result
    assert len(result) == 0


def test_parse_no_blocks_returns_empty():
    result = parse_human_fields(_MD_NO_BLOCKS)
    assert result == {}


def test_parse_ignores_machine_fields():
    result = parse_human_fields(_MD_WITH_VALUES)
    # prep_heuristic and agency_suspect must not be in the returned dict values
    for entry in result.values():
        assert "prep_heuristic" not in entry
        assert "agency_suspect" not in entry
        assert "title" not in entry


def test_parse_how_to_use_section_not_included():
    # The ## How to use section should not produce a spurious entry.
    result = parse_human_fields(_MD_WITH_VALUES)
    assert len(result) == 2


def test_parse_preserves_multiword_why_starred():
    md = """\
## Starred jobs
### S1
- refnr: REF-XYZ
- why_starred: solid team, real DevOps ownership, fully remote
- prep_label: fit
"""
    result = parse_human_fields(md)
    assert result["REF-XYZ"]["why_starred"] == "solid team, real DevOps ownership, fully remote"
