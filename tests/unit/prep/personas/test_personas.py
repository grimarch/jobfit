"""Unit tests for prep personas draft."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from jobfit.prep.context_parse import ContextBlock, parse_context_blocks
from jobfit.prep.personas.draft import (
    ClaimsGapEntry,
    _build_roles_from_yaml,
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
    validate_prep_roles_yaml,
)

_FIXTURES = Path("tests/fixtures/prep/devops")
_CONTEXT_MINI = _FIXTURES / "context_mini.md"
_CLAIMS_MINI = _FIXTURES / "claims_mini.md"
_GOLDEN = _FIXTURES / "personas.draft.golden.md"
_PREP_ROLES_MINI = _FIXTURES / "prep_roles_mini.yaml"

_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def _norm(text: str) -> str:
    return _TIMESTAMP_RE.sub("TIMESTAMP", text)


def _mini_roles():
    """Load mini yaml fixture → (mock_cycle, later_list, mock_order, yaml_config)."""
    yaml_config = load_prep_roles_yaml(_PREP_ROLES_MINI)
    assert yaml_config is not None
    blocks = parse_context_blocks(_CONTEXT_MINI.read_text(encoding="utf-8"))
    blocks_by_sid = {b.sid: b for b in blocks}
    mc, later = _build_roles_from_yaml(yaml_config, blocks_by_sid)
    order = [str(sid) for sid in yaml_config.get("mock_order", [e["id"] for e in mc])]
    return mc, later, order, yaml_config


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
# YAML loader and validator
# ---------------------------------------------------------------------------


def test_load_prep_roles_yaml(tmp_path: Path):
    yaml_file = tmp_path / "prep_roles.yaml"
    yaml_file.write_text(
        "mock_cycle:\n  - id: S1\n    label: Primary\n    archetype: startup\n"
        "later: []\n"
        "mock_order: [S1]\n",
        encoding="utf-8",
    )
    data = load_prep_roles_yaml(yaml_file)
    assert data is not None
    assert data["mock_cycle"][0]["id"] == "S1"
    assert data["mock_order"] == ["S1"]


def test_load_prep_roles_yaml_missing_returns_none(tmp_path: Path):
    assert load_prep_roles_yaml(tmp_path / "nonexistent.yaml") is None


def test_validate_prep_roles_yaml_passes(tmp_path: Path):
    if not _CONTEXT_MINI.is_file():
        pytest.skip("context_mini.md fixture missing")
    blocks = parse_context_blocks(_CONTEXT_MINI.read_text(encoding="utf-8"))
    blocks_by_sid = {b.sid: b for b in blocks}
    yaml_config = {"mock_cycle": [{"id": "S1"}], "later": [], "mock_order": ["S1"]}
    validate_prep_roles_yaml(yaml_config, blocks_by_sid)  # must not raise


def test_yaml_unknown_sid_raises(tmp_path: Path):
    """Unknown S* id in yaml must raise ValueError with available ids."""
    if not _CONTEXT_MINI.is_file():
        pytest.skip("context_mini.md fixture missing")
    blocks = parse_context_blocks(_CONTEXT_MINI.read_text(encoding="utf-8"))
    blocks_by_sid = {b.sid: b for b in blocks}
    yaml_config = {"mock_cycle": [{"id": "S9"}], "later": [], "mock_order": ["S9"]}
    with pytest.raises(ValueError, match="S9"):
        validate_prep_roles_yaml(yaml_config, blocks_by_sid)


def test_yaml_unknown_mock_order_id_raises(tmp_path: Path):
    """mock_order id not in mock_cycle must raise ValueError."""
    if not _CONTEXT_MINI.is_file():
        pytest.skip("context_mini.md fixture missing")
    blocks = parse_context_blocks(_CONTEXT_MINI.read_text(encoding="utf-8"))
    blocks_by_sid = {b.sid: b for b in blocks}
    yaml_config = {
        "mock_cycle": [{"id": "S1"}, {"id": "S4"}],
        "later": [],
        "mock_order": ["S1", "S2"],  # S2 not in mock_cycle
    }
    with pytest.raises(ValueError, match="mock_order"):
        validate_prep_roles_yaml(yaml_config, blocks_by_sid)


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
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file() or not _PREP_ROLES_MINI.is_file():
        pytest.skip("mini fixtures missing")

    context_text = _CONTEXT_MINI.read_text(encoding="utf-8")
    claims_text = _CLAIMS_MINI.read_text(encoding="utf-8")
    blocks = parse_context_blocks(context_text)
    all_gaps = parse_claims_gaps(claims_text)
    mock_cycle, later_list, mock_order, _ = _mini_roles()

    result = render_draft_md(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        blocks=blocks,
        all_gaps=all_gaps,
        mock_cycle=mock_cycle,
        later_list=later_list,
        mock_order=mock_order,
        prep_roles_config_label=_PREP_ROLES_MINI.as_posix(),
    )

    normalized = _norm(result)

    if not _GOLDEN.is_file():
        _GOLDEN.write_text(normalized, encoding="utf-8")
        pytest.skip("Golden file created — re-run to verify")

    expected = _GOLDEN.read_text(encoding="utf-8")
    assert normalized == expected


# ---------------------------------------------------------------------------
# render_draft_md feature tests
# ---------------------------------------------------------------------------


def test_render_draft_md_includes_jd_excerpt():
    """Each mock-cycle block must contain the JD excerpt from the context block."""
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file() or not _PREP_ROLES_MINI.is_file():
        pytest.skip("mini fixtures missing")

    blocks = parse_context_blocks(_CONTEXT_MINI.read_text(encoding="utf-8"))
    all_gaps = parse_claims_gaps(_CLAIMS_MINI.read_text(encoding="utf-8"))
    mock_cycle, later_list, mock_order, _ = _mini_roles()

    result = render_draft_md(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        blocks=blocks,
        all_gaps=all_gaps,
        mock_cycle=mock_cycle,
        later_list=later_list,
        mock_order=mock_order,
        prep_roles_config_label=_PREP_ROLES_MINI.as_posix(),
    )

    assert "**JD excerpt:** Build the infrastructure for live AI products." in result
    assert "**JD excerpt:** Design and operate customer platforms on private cloud and Azure." in result
    assert "**JD focus:** _TODO — paraphrase JD excerpt above_" in result
    assert "_TODO — refine from jd_excerpt_" not in result


def test_render_draft_later_includes_refnr():
    """Later section must include company and refnr, not just a one-liner."""
    block_fit = ContextBlock(
        sid="S1",
        prep_label="fit",
        company="FitCo",
        refnr="ref-001",
        company_stage="startup",
        industry="SaaS",
    )
    block_later = ContextBlock(
        sid="S3",
        prep_label="brand-only",
        company="BrandCo",
        refnr="ref-003",
        company_stage="enterprise",
        industry="FinTech",
    )
    mock_cycle = [{"id": "S1", "label": "Primary", "archetype": "startup / SaaS", "llm": {}}]
    later_list = [{"id": "S3", "label": "Later", "archetype": "enterprise / FinTech", "reason": "prep_label: brand-only"}]
    result = render_draft_md(
        role_slug="test",
        context_path=Path("context.md"),
        claims_path=Path("claims.md"),
        blocks=[block_fit, block_later],
        all_gaps=[],
        mock_cycle=mock_cycle,
        later_list=later_list,
        mock_order=["S1"],
        prep_roles_config_label="test/prep_roles.yaml",
    )
    assert "## Later jobs" in result
    assert "**Company:** BrandCo" in result
    assert "**refnr:** ref-003" in result
    assert "**prep_label:** brand-only" in result


def test_draft_renders_llm_hints_comments():
    """When yaml has llm: hints, draft must contain <!-- jobfit:prep-personas:llm-hints:SX -->."""
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file():
        pytest.skip("mini fixtures missing")
    blocks = parse_context_blocks(_CONTEXT_MINI.read_text(encoding="utf-8"))
    blocks_by_sid = {b.sid: b for b in blocks}
    all_gaps = parse_claims_gaps(_CLAIMS_MINI.read_text(encoding="utf-8"))

    yaml_with_hints = {
        "mock_cycle": [
            {"id": "S1", "label": "Primary", "llm": {"lead_themes": ["CI/CD", "Terraform"], "language": "EN technical"}},
            {"id": "S4", "label": "Stretch", "llm": {"language": "DE primary"}},
            {"id": "S2", "label": "Stretch 2"},
        ],
        "later": [],
        "mock_order": ["S1", "S4", "S2"],
    }
    mock_cycle, later_list = _build_roles_from_yaml(yaml_with_hints, blocks_by_sid)
    result = render_draft_md(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        blocks=blocks,
        all_gaps=all_gaps,
        mock_cycle=mock_cycle,
        later_list=later_list,
        mock_order=["S1", "S4", "S2"],
        prep_roles_config_label="prep_roles.yaml",
    )
    assert "<!-- jobfit:prep-personas:llm-hints:S1" in result
    assert "lead_themes: CI/CD, Terraform" in result
    assert "language: EN technical" in result
    assert "<!-- jobfit:prep-personas:llm-hints:S4" in result
    assert "language: DE primary" in result
    # S2 has no llm hints — no comment for it
    assert "<!-- jobfit:prep-personas:llm-hints:S2" not in result
    assert "/jobfit:prep-personas:llm-hints -->" in result


def test_draft_renders_refine_config_comment():
    """When yaml has refine: block, draft contains <!-- jobfit:prep-personas:refine-config -->."""
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file():
        pytest.skip("mini fixtures missing")
    blocks = parse_context_blocks(_CONTEXT_MINI.read_text(encoding="utf-8"))
    blocks_by_sid = {b.sid: b for b in blocks}
    all_gaps = parse_claims_gaps(_CLAIMS_MINI.read_text(encoding="utf-8"))

    yaml_cfg = {
        "mock_cycle": [{"id": "S1", "label": "Primary"}],
        "later": [],
        "mock_order": ["S1"],
        "refine": {"story_numbering": "1 = CI/CD LMS\n2 = Terraform", "notes": "mid DevOps"},
    }
    mock_cycle, later_list = _build_roles_from_yaml(yaml_cfg, blocks_by_sid)
    result = render_draft_md(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        blocks=blocks,
        all_gaps=all_gaps,
        mock_cycle=mock_cycle,
        later_list=later_list,
        mock_order=["S1"],
        prep_roles_config_label="prep_roles.yaml",
        refine_config=yaml_cfg["refine"],
    )
    assert "<!-- jobfit:prep-personas:refine-config" in result
    assert "story_numbering:" in result
    assert "/jobfit:prep-personas:refine-config -->" in result


def test_gaps_in_llm_input():
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file() or not _PREP_ROLES_MINI.is_file():
        pytest.skip("mini fixtures missing")

    blocks = parse_context_blocks(_CONTEXT_MINI.read_text(encoding="utf-8"))
    all_gaps = parse_claims_gaps(_CLAIMS_MINI.read_text(encoding="utf-8"))
    mock_cycle, later_list, mock_order, _ = _mini_roles()

    result = render_draft_md(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        blocks=blocks,
        all_gaps=all_gaps,
        mock_cycle=mock_cycle,
        later_list=later_list,
        mock_order=mock_order,
        prep_roles_config_label=_PREP_ROLES_MINI.as_posix(),
    )

    llm_body = extract_llm_input(result)
    assert "**Gaps for this job:**" in llm_body
    assert "- **AWS**" in llm_body


# ---------------------------------------------------------------------------
# run() — yaml required (Option A)
# ---------------------------------------------------------------------------


def test_draft_fails_without_prep_roles_yaml(tmp_path: Path):
    """Option A: run() must raise FileNotFoundError if yaml is missing."""
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file():
        pytest.skip("mini fixtures missing")
    # Point to a directory with no yaml
    with pytest.raises(FileNotFoundError, match="prep_roles.yaml"):
        run(
            role_slug="devops",
            context_path=_CONTEXT_MINI,
            claims_path=_CLAIMS_MINI,
            out_path=tmp_path / "out.md",
            prep_roles_path=tmp_path / "prep_roles.yaml",  # does not exist
            require_reviewed=False,
        )


def test_run_dry_run(tmp_path: Path):
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file() or not _PREP_ROLES_MINI.is_file():
        pytest.skip("mini fixtures missing")
    out = tmp_path / "personas.draft.md"
    summary = run(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        out_path=out,
        prep_roles_path=_PREP_ROLES_MINI,
        dry_run=True,
        require_reviewed=False,
    )
    assert summary["mode"] == "dry-run"
    assert not out.exists()


def test_run_writes_draft(tmp_path: Path):
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file() or not _PREP_ROLES_MINI.is_file():
        pytest.skip("mini fixtures missing")
    out = tmp_path / "personas.draft.md"
    summary = run(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        out_path=out,
        prep_roles_path=_PREP_ROLES_MINI,
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
    if not _CONTEXT_MINI.is_file() or not _PREP_ROLES_MINI.is_file():
        pytest.skip("fixtures missing")
    claims = tmp_path / "claims_no_review.md"
    claims.write_text("# Claims — no reviewed marker\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Reviewed"):
        run(
            role_slug="devops",
            context_path=_CONTEXT_MINI,
            claims_path=claims,
            out_path=tmp_path / "out.md",
            prep_roles_path=_PREP_ROLES_MINI,
            force=True,
        )


def test_run_respects_force_guard(tmp_path: Path):
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file() or not _PREP_ROLES_MINI.is_file():
        pytest.skip("mini fixtures missing")
    out = tmp_path / "personas.draft.md"
    out.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run(
            role_slug="devops",
            context_path=_CONTEXT_MINI,
            claims_path=_CLAIMS_MINI,
            out_path=out,
            prep_roles_path=_PREP_ROLES_MINI,
            require_reviewed=False,
        )


def test_run_config_label_shows_yaml_path(tmp_path: Path):
    """Draft header must show yaml path, not 'auto'."""
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file() or not _PREP_ROLES_MINI.is_file():
        pytest.skip("mini fixtures missing")
    out = tmp_path / "personas.draft.md"
    run(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        out_path=out,
        prep_roles_path=_PREP_ROLES_MINI,
        force=True,
        require_reviewed=False,
    )
    text = out.read_text(encoding="utf-8")
    assert "prep_roles_mini.yaml" in text
    assert "config:** `auto`" not in text


def test_default_paths():
    assert default_draft_path("devops") == Path("prompts/prep/devops/personas.draft.md")
    assert default_claims_path("devops") == Path("prompts/prep/devops/claims.md")


def test_run_with_prep_roles_yaml(tmp_path: Path):
    """YAML config drives mock_cycle and later."""
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


def test_mock_order_follows_yaml_over_auto(tmp_path: Path):
    """YAML mock_order controls interview order."""
    if not _CONTEXT_MINI.is_file() or not _CLAIMS_MINI.is_file():
        pytest.skip("mini fixtures missing")
    yaml_path = tmp_path / "prep_roles.yaml"
    yaml_path.write_text(
        "mock_cycle:\n"
        "  - id: S1\n    label: Primary\n"
        "  - id: S2\n    label: Stretch\n"
        "  - id: S4\n    label: Stretch 2\n"
        "later: []\n"
        "mock_order: [S2, S1, S4]\n",
        encoding="utf-8",
    )
    out = tmp_path / "personas.draft.md"
    run(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        out_path=out,
        prep_roles_path=yaml_path,
        force=True,
        require_reviewed=False,
    )
    text = out.read_text(encoding="utf-8")
    mock_section_start = text.index("## Mock order")
    mock_block = text[mock_section_start:mock_section_start + 200]
    assert mock_block.index("S2") < mock_block.index("S1") < mock_block.index("S4")
