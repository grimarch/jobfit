"""Unit tests for prep personas draft."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from jobfit.prep_context.context_parse import ContextBlock, parse_context_blocks
from jobfit.prep_context.personas import (
    ClaimsGapEntry,
    auto_select_roles,
    default_draft_path,
    default_claims_path,
    extract_llm_input,
    filter_gaps_for_job,
    load_prep_roles_yaml,
    parse_claims_do_not_claim,
    parse_claims_gaps,
    parse_claims_ok_labels,
    parse_claims_quick_reference,
    render_draft_md,
    require_reviewed_claims,
    run,
)

_FIXTURES = Path("tests/fixtures/prep/devops")
_CONTEXT_MINI = _FIXTURES / "context_mini.md"
_CLAIMS_MINI = _FIXTURES / "claims_mini.md"
_GOLDEN = _FIXTURES / "personas.draft.golden.md"

_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def _norm(text: str) -> str:
    return _TIMESTAMP_RE.sub("TIMESTAMP", text)


# ---------------------------------------------------------------------------
# context_parse tests
# ---------------------------------------------------------------------------


def test_parse_context_blocks_reads_company_and_jd_excerpt():
    if not _CONTEXT_MINI.is_file():
        pytest.skip("context_mini.md fixture missing")
    blocks = parse_context_blocks(_CONTEXT_MINI.read_text(encoding="utf-8"))
    assert len(blocks) == 3
    s1 = next(b for b in blocks if b.sid == "S1")
    assert s1.company == "TestCo"
    assert "AI" in s1.jd_excerpt
    assert s1.company_stage == "startup"
    assert s1.industry == "AI/SaaS"
    assert s1.english_ok is True
    assert s1.on_call is False
    assert s1.refnr == "mini-001"


def test_parse_context_blocks_work_mode_compound():
    """S4 has on_call=True, german_level=B1, english_ok=False."""
    if not _CONTEXT_MINI.is_file():
        pytest.skip("context_mini.md fixture missing")
    blocks = parse_context_blocks(_CONTEXT_MINI.read_text(encoding="utf-8"))
    s4 = next(b for b in blocks if b.sid == "S4")
    assert s4.on_call is True
    assert s4.german_level == "B1"
    assert s4.english_ok is False
    assert s4.work_mode == "hybrid"


def test_parse_context_blocks_gaps_vs_cv():
    if not _CONTEXT_MINI.is_file():
        pytest.skip("context_mini.md fixture missing")
    blocks = parse_context_blocks(_CONTEXT_MINI.read_text(encoding="utf-8"))
    by_sid = {b.sid: b for b in blocks}
    assert set(by_sid["S1"].gaps_vs_cv) == {"AWS", "Azure"}
    assert set(by_sid["S4"].gaps_vs_cv) == {"AWS", "Azure", "Jenkins"}
    assert set(by_sid["S2"].gaps_vs_cv) == {"AWS", "IAM", "OpenTelemetry"}


# ---------------------------------------------------------------------------
# claims parsing tests
# ---------------------------------------------------------------------------


def test_parse_claims_gaps():
    if not _CLAIMS_MINI.is_file():
        pytest.skip("claims_mini.md fixture missing")
    text = _CLAIMS_MINI.read_text(encoding="utf-8")
    gaps = parse_claims_gaps(text)
    assert len(gaps) == 5
    aws = next(g for g in gaps if g.skill == "AWS")
    assert "Production AWS" in aws.do_not_claim
    assert "IaC patterns" in aws.say_instead


def test_parse_claims_gaps_empty_on_no_markers():
    assert parse_claims_gaps("# no markers here") == []


def test_parse_claims_do_not_claim():
    if not _CLAIMS_MINI.is_file():
        pytest.skip("claims_mini.md fixture missing")
    text = _CLAIMS_MINI.read_text(encoding="utf-8")
    items = parse_claims_do_not_claim(text)
    assert len(items) >= 1
    assert any("AWS" in item for item in items)


def test_parse_claims_quick_reference():
    if not _CLAIMS_MINI.is_file():
        pytest.skip("claims_mini.md fixture missing")
    text = _CLAIMS_MINI.read_text(encoding="utf-8")
    qr = parse_claims_quick_reference(text)
    assert "## Quick reference" in qr
    assert "CI/CD" in qr


def test_parse_claims_ok_labels():
    sample = "| **GitLab CI** | evidence | ok |\n| **Terraform** | ev | weak |"
    labels = parse_claims_ok_labels(sample)
    assert "GitLab CI" in labels
    assert "Terraform" not in labels


# ---------------------------------------------------------------------------
# gap filtering tests
# ---------------------------------------------------------------------------


def _make_block(sid: str, gaps: list[str]) -> ContextBlock:
    return ContextBlock(sid=sid, gaps_vs_cv=tuple(gaps))


def _make_gap(skill: str, jobs: str = "S1") -> ClaimsGapEntry:
    return ClaimsGapEntry(skill=skill, jobs=jobs, do_not_claim="Do not.", say_instead="Say.")


def test_filter_gaps_for_job_s1():
    block = _make_block("S1", ["AWS", "Azure"])
    all_gaps = [_make_gap("AWS"), _make_gap("Azure"), _make_gap("Jenkins"), _make_gap("IAM")]
    result = filter_gaps_for_job(block, all_gaps)
    assert [g.skill for g in result] == ["AWS", "Azure"]


def test_filter_gaps_for_job_s2():
    block = _make_block("S2", ["AWS", "IAM", "OpenTelemetry"])
    all_gaps = [_make_gap("AWS"), _make_gap("IAM"), _make_gap("OpenTelemetry"), _make_gap("Azure")]
    result = filter_gaps_for_job(block, all_gaps)
    assert {g.skill for g in result} == {"AWS", "IAM", "OpenTelemetry"}


def test_filter_gaps_skill_alias_golang():
    """Go/Golang in gaps table matches 'Go' in gaps_vs_cv."""
    block = _make_block("S3", ["Go/Golang"])
    all_gaps = [_make_gap("Go/Golang")]
    assert len(filter_gaps_for_job(block, all_gaps)) == 1

    block2 = _make_block("S3", ["Go"])
    assert len(filter_gaps_for_job(block2, all_gaps)) == 1


# ---------------------------------------------------------------------------
# prep roles selection tests
# ---------------------------------------------------------------------------


def test_auto_select_roles_fit_first():
    blocks = [
        ContextBlock(sid="S1", prep_label="fit", company_stage="startup", industry="AI"),
        ContextBlock(sid="S4", prep_label="stretch", company_stage="mid", industry="Cloud"),
        ContextBlock(sid="S2", prep_label="stretch", company_stage="startup", industry="SaaS"),
    ]
    result = auto_select_roles(blocks)
    ids = [e["id"] for e in result["mock_cycle"]]
    assert ids[0] == "S1"  # fit first
    assert set(ids[1:]) == {"S4", "S2"}
    assert result["later"] == []


def test_auto_select_roles_brand_only_to_later():
    blocks = [
        ContextBlock(sid="S1", prep_label="fit"),
        ContextBlock(sid="S3", prep_label="brand-only"),
    ]
    result = auto_select_roles(blocks)
    assert [e["id"] for e in result["mock_cycle"]] == ["S1"]
    assert result["later"][0]["id"] == "S3"


def test_auto_select_roles_caps_at_three():
    blocks = [ContextBlock(sid=f"S{i}", prep_label="fit") for i in range(5)]
    result = auto_select_roles(blocks)
    assert len(result["mock_cycle"]) == 3


def test_load_prep_roles_yaml(tmp_path: Path):
    yaml_file = tmp_path / "prep_roles.yaml"
    yaml_file.write_text(
        "mock_cycle:\n  - id: S1\n    label: Primary\n    archetype: startup\n"
        "mock_order: [S1]\n",
        encoding="utf-8",
    )
    data = load_prep_roles_yaml(yaml_file)
    assert data is not None
    assert data["mock_cycle"][0]["id"] == "S1"
    assert data["mock_order"] == ["S1"]


def test_load_prep_roles_yaml_missing_returns_none(tmp_path: Path):
    assert load_prep_roles_yaml(tmp_path / "nonexistent.yaml") is None


# ---------------------------------------------------------------------------
# require_reviewed_claims guard
# ---------------------------------------------------------------------------


def test_require_reviewed_claims_passes():
    require_reviewed_claims("**Reviewed:** 2026-07-22\n# Claims", Path("claims.md"))


def test_require_reviewed_claims_raises_on_missing():
    with pytest.raises(ValueError, match="Reviewed"):
        require_reviewed_claims("# Claims — no reviewed marker", Path("claims.md"))


# ---------------------------------------------------------------------------
# render_draft_md golden test
# ---------------------------------------------------------------------------


def test_render_draft_md_golden():
    """Compare render output to golden snapshot (normalize timestamps)."""
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file():
        pytest.skip("mini fixtures missing")

    context_text = _CONTEXT_MINI.read_text(encoding="utf-8")
    claims_text = _CLAIMS_MINI.read_text(encoding="utf-8")

    from jobfit.prep_context.personas import (
        auto_select_roles,
        parse_claims_gaps,
        parse_context_blocks,
    )

    blocks = parse_context_blocks(context_text)
    all_gaps = parse_claims_gaps(claims_text)
    auto = auto_select_roles(blocks)

    result = render_draft_md(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        blocks=blocks,
        all_gaps=all_gaps,
        mock_cycle=auto["mock_cycle"],
        later_list=auto["later"],
        mock_order=auto["mock_order"],
        prep_roles_config_label="auto",
        is_auto=True,
    )

    normalized = _norm(result)

    if not _GOLDEN.is_file():
        _GOLDEN.write_text(normalized, encoding="utf-8")
        pytest.skip("Golden file created — re-run to verify")

    expected = _GOLDEN.read_text(encoding="utf-8")
    assert normalized == expected


# ---------------------------------------------------------------------------
# gaps_in_llm_input: gap lines must be inside llm-input markers
# ---------------------------------------------------------------------------


def test_gaps_in_llm_input():
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file():
        pytest.skip("mini fixtures missing")

    blocks = parse_context_blocks(_CONTEXT_MINI.read_text(encoding="utf-8"))
    all_gaps = parse_claims_gaps(_CLAIMS_MINI.read_text(encoding="utf-8"))
    auto = auto_select_roles(blocks)

    result = render_draft_md(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        blocks=blocks,
        all_gaps=all_gaps,
        mock_cycle=auto["mock_cycle"],
        later_list=auto["later"],
        mock_order=auto["mock_order"],
        prep_roles_config_label="auto",
        is_auto=True,
    )

    llm_body = extract_llm_input(result)
    assert "**Gaps for this job:**" in llm_body
    assert "- **AWS**" in llm_body


# ---------------------------------------------------------------------------
# run() integration — file write and dry-run
# ---------------------------------------------------------------------------


def test_run_dry_run(tmp_path: Path):
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file():
        pytest.skip("mini fixtures missing")
    out = tmp_path / "personas.draft.md"
    summary = run(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        out_path=out,
        dry_run=True,
        require_reviewed=False,
    )
    assert summary["mode"] == "dry-run"
    assert not out.exists()


def test_run_writes_draft(tmp_path: Path):
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file():
        pytest.skip("mini fixtures missing")
    out = tmp_path / "personas.draft.md"
    summary = run(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        out_path=out,
        force=True,
        require_reviewed=False,
    )
    assert summary["mode"] == "write"
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "# Prep roles (devops)" in text
    assert "**Gaps for this job:**" in text
    assert "- **AWS**" in text


def test_run_requires_reviewed_by_default(tmp_path: Path):
    if not _CONTEXT_MINI.is_file():
        pytest.skip("context_mini.md fixture missing")
    claims = tmp_path / "claims_no_review.md"
    claims.write_text("# Claims — no reviewed marker\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Reviewed"):
        run(
            role_slug="devops",
            context_path=_CONTEXT_MINI,
            claims_path=claims,
            out_path=tmp_path / "out.md",
            force=True,
        )


def test_run_respects_force_guard(tmp_path: Path):
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file():
        pytest.skip("mini fixtures missing")
    out = tmp_path / "personas.draft.md"
    out.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run(
            role_slug="devops",
            context_path=_CONTEXT_MINI,
            claims_path=_CLAIMS_MINI,
            out_path=out,
            require_reviewed=False,
        )


def test_default_paths():
    assert default_draft_path("devops") == Path("prompts/prep/devops/personas.draft.md")
    assert default_claims_path("devops") == Path("prompts/prep/devops/claims.md")


def test_run_with_prep_roles_yaml(tmp_path: Path):
    """YAML config overrides auto-selection order."""
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file():
        pytest.skip("mini fixtures missing")
    yaml_path = tmp_path / "prep_roles.yaml"
    yaml_path.write_text(
        "mock_cycle:\n"
        "  - id: S2\n    label: Primary\n    archetype: startup platform\n"
        "later:\n"
        "  - id: S4\n    label: Later\n    reason: many gaps\n"
        "mock_order: [S2]\n",
        encoding="utf-8",
    )
    out = tmp_path / "personas.draft.md"
    summary = run(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        out_path=out,
        prep_roles_path=yaml_path,
        force=True,
        require_reviewed=False,
    )
    assert "S2" in summary["mock_cycle_ids"]
    text = out.read_text(encoding="utf-8")
    assert "## S2 — Primary" in text
    assert "Later jobs" in text
