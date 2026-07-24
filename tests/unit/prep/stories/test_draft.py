"""Unit tests for prep stories draft (Phase 1)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from jobfit.prep.stories.draft import (
    _extract_field,
    _extract_stories_block,
    default_draft_path,
    extract_llm_input,
    extract_metrics,
    parse_claims_evidence,
    parse_personas_sections,
    render_draft_md,
    run,
)
from jobfit.prep.stories.enrichment import (
    EmployerInfo,
    StoryEnrichment,
    StoryOverride,
    format_employer_context,
    load_enrichment,
)
from jobfit.prep.stories.slots import (
    CATALOG,
    MOCK_STORY_ORDER,
    stories_for_mock,
)
from jobfit.prep.context_parse import parse_context_blocks

_FIXTURES = Path("tests/fixtures/prep/devops")
_CONTEXT_MINI = _FIXTURES / "context_mini.md"
_CLAIMS_MINI = _FIXTURES / "stories_claims_mini.md"
_PERSONAS_MINI = _FIXTURES / "stories_personas_mini.md"
_PREP_ROLES_MINI = _FIXTURES / "prep_roles_mini.yaml"

_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def _norm(text: str) -> str:
    return _TS_RE.sub("TIMESTAMP", text)


def _fixtures_ok() -> bool:
    return all(p.is_file() for p in [_CONTEXT_MINI, _CLAIMS_MINI, _PERSONAS_MINI, _PREP_ROLES_MINI])


# ---------------------------------------------------------------------------
# slots.py tests
# ---------------------------------------------------------------------------


def test_catalog_contains_all_nine_stories():
    expected = {
        "s1-ci-cd", "s1-terraform", "s1-vault", "s1-jobfit", "s1-helm-opt",
        "s4-ansible", "s4-observability", "s2-devsecops", "s4-triage-opt",
    }
    assert set(CATALOG.keys()) == expected


def test_stories_for_mock_s1_returns_five():
    slots = stories_for_mock("S1")
    assert len(slots) == 5
    ids = [s.id for s in slots]
    assert ids == ["s1-ci-cd", "s1-terraform", "s1-vault", "s1-jobfit", "s1-helm-opt"]


def test_stories_for_mock_s4_optional_count():
    slots = stories_for_mock("S4")
    assert len(slots) == 5
    optional_ids = [s.id for s in slots if s.optional]
    assert "s1-helm-opt" in optional_ids
    assert "s4-triage-opt" in optional_ids


def test_stories_for_mock_s2_returns_four():
    slots = stories_for_mock("S2")
    assert len(slots) == 4
    assert slots[0].id == "s1-ci-cd"
    assert slots[2].id == "s2-devsecops"


def test_stories_for_mock_unknown_returns_empty():
    assert stories_for_mock("S99") == []


def test_catalog_slot_work_comp_is_valid():
    for slot in CATALOG.values():
        assert slot.work_comp in ("WORK_COMP_1", "WORK_COMP_2"), slot.id


def test_catalog_slot_claims_labels_nonempty():
    for slot in CATALOG.values():
        assert len(slot.claims_labels) >= 1, f"{slot.id} has no claims_labels"


# ---------------------------------------------------------------------------
# extract_metrics tests
# ---------------------------------------------------------------------------


def test_extract_metrics_cicd_evidence():
    evidence = (
        "reducing manual deploy effort from approximately 45 minutes to 10 minutes. ([WORK_COMP_1])"
    )
    metrics = extract_metrics(evidence)
    assert any("45→10" in m for m in metrics), f"expected 45→10 in {metrics}"


def test_extract_metrics_terraform_evidence():
    evidence = (
        "managing 29 Terraform-managed resources across 2 project stacks with remote state. "
        "DigitalOcean Vault Cloud Infra: 5-node Raft cluster. ([WORK_COMP_1])"
    )
    metrics = extract_metrics(evidence)
    assert any("5-node" in m for m in metrics)
    assert any("29" in m for m in metrics)


def test_extract_metrics_jobfit_evidence():
    evidence = (
        "multi-source ETL from 23 feeds, PostgreSQL, Docker Compose, FastAPI — "
        "reducing manual market research from weeks to 30–40 minutes per cycle. ([WORK_COMP_1])"
    )
    metrics = extract_metrics(evidence)
    assert any("23" in m for m in metrics), f"expected 23 feeds in {metrics}"
    assert any("30" in m and "40" in m for m in metrics), f"expected 30–40 in {metrics}"


def test_extract_metrics_200_plus_hosts():
    evidence = "giving ops teams visibility into 200+ monitored hosts and faster triage."
    metrics = extract_metrics(evidence)
    assert any("200" in m for m in metrics)


def test_extract_metrics_no_metrics_returns_empty():
    evidence = "Replaced a Helm fork with an umbrella chart. ([WORK_COMP_2])"
    metrics = extract_metrics(evidence)
    assert metrics == []


# ---------------------------------------------------------------------------
# parse_claims_evidence tests
# ---------------------------------------------------------------------------


def test_parse_claims_evidence_finds_cicd():
    if not _CLAIMS_MINI.is_file():
        pytest.skip("stories_claims_mini.md fixture missing")
    text = _CLAIMS_MINI.read_text(encoding="utf-8")
    ev_map = parse_claims_evidence(text)
    assert "GitLab CI/CD — design, stages, deploy automation" in ev_map
    assert "45 minutes to 10 minutes" in ev_map["GitLab CI/CD — design, stages, deploy automation"]


def test_parse_claims_evidence_finds_terraform():
    if not _CLAIMS_MINI.is_file():
        pytest.skip("stories_claims_mini.md fixture missing")
    text = _CLAIMS_MINI.read_text(encoding="utf-8")
    ev_map = parse_claims_evidence(text)
    assert "Terraform / IaC — multi-stack, remote state" in ev_map
    assert "29" in ev_map["Terraform / IaC — multi-stack, remote state"]


def test_parse_claims_evidence_finds_vault():
    if not _CLAIMS_MINI.is_file():
        pytest.skip("stories_claims_mini.md fixture missing")
    text = _CLAIMS_MINI.read_text(encoding="utf-8")
    ev_map = parse_claims_evidence(text)
    assert "HashiCorp Vault — secrets, RBAC, delivery pattern" in ev_map


def test_parse_claims_evidence_empty_on_no_tables():
    assert parse_claims_evidence("# No tables here") == {}


# ---------------------------------------------------------------------------
# parse_personas_sections tests
# ---------------------------------------------------------------------------


def test_parse_personas_sections_finds_s1():
    if not _PERSONAS_MINI.is_file():
        pytest.skip("stories_personas_mini.md fixture missing")
    text = _PERSONAS_MINI.read_text(encoding="utf-8")
    sections = parse_personas_sections(text)
    assert "S1" in sections
    assert "CI/CD" in sections["S1"].jd_focus or "containerization" in sections["S1"].jd_focus


def test_parse_personas_sections_finds_mock_traps():
    if not _PERSONAS_MINI.is_file():
        pytest.skip("stories_personas_mini.md fixture missing")
    text = _PERSONAS_MINI.read_text(encoding="utf-8")
    sections = parse_personas_sections(text)
    assert "AWS" in sections["S1"].mock_traps


def test_parse_personas_sections_finds_language():
    if not _PERSONAS_MINI.is_file():
        pytest.skip("stories_personas_mini.md fixture missing")
    text = _PERSONAS_MINI.read_text(encoding="utf-8")
    sections = parse_personas_sections(text)
    assert "EN" in sections["S1"].language
    assert "DE" in sections["S4"].language


def test_parse_personas_sections_all_three_mocks():
    if not _PERSONAS_MINI.is_file():
        pytest.skip("stories_personas_mini.md fixture missing")
    text = _PERSONAS_MINI.read_text(encoding="utf-8")
    sections = parse_personas_sections(text)
    assert {"S1", "S4", "S2"} <= set(sections.keys())


def test_parse_personas_sections_stories_to_write():
    if not _PERSONAS_MINI.is_file():
        pytest.skip("stories_personas_mini.md fixture missing")
    text = _PERSONAS_MINI.read_text(encoding="utf-8")
    sections = parse_personas_sections(text)
    stories_s1 = sections["S1"].stories_to_write
    assert stories_s1.startswith("1.")
    assert "CI/CD" in stories_s1 or "GitLab" in stories_s1


# ---------------------------------------------------------------------------
# enrichment tests
# ---------------------------------------------------------------------------


def test_load_enrichment_missing_returns_default(tmp_path: Path):
    enrichment = load_enrichment(tmp_path / "nonexistent.yaml")
    assert enrichment.voice == ""
    assert enrichment.employers == {}
    assert enrichment.stories == {}


def test_load_enrichment_parses_employers(tmp_path: Path):
    yaml_file = tmp_path / "stories_enrichment.yaml"
    yaml_file.write_text(
        "voice: first person, mid-level DevOps\n"
        "de_level: B2 HR\n"
        "employers:\n"
        "  WORK_COMP_1:\n"
        "    industry: EdTech — LMS SaaS\n"
        "    company_stage: product company, small team\n"
        "    display_name: my current employer\n"
        "    anonymize_level: generic\n"
        "    comment: I owned CI/CD end-to-end\n",
        encoding="utf-8",
    )
    enrichment = load_enrichment(yaml_file)
    assert enrichment.voice == "first person, mid-level DevOps"
    assert "WORK_COMP_1" in enrichment.employers
    emp = enrichment.employers["WORK_COMP_1"]
    assert emp.industry == "EdTech — LMS SaaS"
    assert emp.anonymize_level == "generic"
    assert "CI/CD end-to-end" in emp.comment


def test_load_enrichment_parses_story_overrides(tmp_path: Path):
    yaml_file = tmp_path / "stories_enrichment.yaml"
    yaml_file.write_text(
        "stories:\n"
        "  s1-ci-cd:\n"
        "    comment: Lead with release pain before naming tools\n"
        "    optional: false\n"
        "  s1-helm-opt:\n"
        "    optional: true\n",
        encoding="utf-8",
    )
    enrichment = load_enrichment(yaml_file)
    assert "s1-ci-cd" in enrichment.stories
    assert "Lead with release pain" in enrichment.stories["s1-ci-cd"].comment
    assert enrichment.stories["s1-helm-opt"].optional is True


def test_format_employer_context_no_enrichment():
    enrichment = StoryEnrichment()
    result = format_employer_context("WORK_COMP_1", enrichment)
    assert result == "—"


def test_format_employer_context_with_employer():
    emp = EmployerInfo(
        display_name="my current employer",
        industry="EdTech — LMS SaaS",
        company_stage="product company, small team",
        anonymize_level="generic",
        comment="I owned CI/CD end-to-end",
    )
    enrichment = StoryEnrichment(employers={"WORK_COMP_1": emp})
    result = format_employer_context("WORK_COMP_1", enrichment)
    assert "EdTech" in result
    assert "CI/CD end-to-end" in result


# ---------------------------------------------------------------------------
# render_draft_md tests
# ---------------------------------------------------------------------------


def _run_render(tmp_path: Path) -> str:
    if not _fixtures_ok():
        pytest.skip("stories mini fixtures missing")
    context_text = _CONTEXT_MINI.read_text(encoding="utf-8")
    claims_text = _CLAIMS_MINI.read_text(encoding="utf-8")
    personas_text = _PERSONAS_MINI.read_text(encoding="utf-8")
    blocks = parse_context_blocks(context_text)
    ev_map = parse_claims_evidence(claims_text)
    persona_sections = parse_personas_sections(personas_text)

    import yaml as _yaml
    roles_data = _yaml.safe_load(_PREP_ROLES_MINI.read_text(encoding="utf-8"))
    blocks_by_sid = {b.sid: b for b in blocks}
    from jobfit.prep.personas.draft import _build_roles_from_yaml
    mock_cycle, _ = _build_roles_from_yaml(roles_data, blocks_by_sid)
    mock_order = [str(s) for s in roles_data.get("mock_order", [e["id"] for e in mock_cycle])]

    return render_draft_md(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        personas_path=_PERSONAS_MINI,
        prep_roles_config_label=_PREP_ROLES_MINI.as_posix(),
        enrichment_label="—",
        blocks=blocks,
        evidence_map=ev_map,
        persona_sections=persona_sections,
        mock_cycle=mock_cycle,
        mock_order=mock_order,
        enrichment=StoryEnrichment(),
    )


def test_render_has_llm_input_markers():
    md = _run_render(Path("."))
    assert "<!-- jobfit:prep-stories:llm-input -->" in md
    assert "<!-- /jobfit:prep-stories:llm-input -->" in md


def test_render_has_story_markers():
    md = _run_render(Path("."))
    assert '<!-- jobfit:prep-stories:story id="s1-ci-cd" mock="S1" order="1" -->' in md
    assert "<!-- /jobfit:prep-stories:story -->" in md


def test_render_has_todo_placeholders():
    md = _run_render(Path("."))
    assert "_TODO — run prep-stories refine_" in md


def test_render_has_locked_metrics_in_s1_cicd():
    md = _run_render(Path("."))
    # 45→10 min metric must appear
    assert "45→10" in md


def test_render_has_locked_metrics_in_s1_terraform():
    md = _run_render(Path("."))
    assert "29" in md  # 29 resources
    assert "5-node" in md


def test_render_has_locked_metrics_in_s1_jobfit():
    md = _run_render(Path("."))
    assert "23" in md   # 23 feeds
    assert "30" in md   # 30–40 min


def test_render_has_s1_s4_s2_sections():
    md = _run_render(Path("."))
    assert "## Mock S1" in md
    assert "## Mock S4" in md
    assert "## Mock S2" in md


def test_render_s1_story_order():
    md = _run_render(Path("."))
    pos_cicd = md.index('id="s1-ci-cd"')
    pos_terraform = md.index('id="s1-terraform"')
    pos_vault = md.index('id="s1-vault"')
    pos_jobfit = md.index('id="s1-jobfit"')
    assert pos_cicd < pos_terraform < pos_vault < pos_jobfit


def test_render_s4_stories_present():
    md = _run_render(Path("."))
    assert 'id="s4-ansible"' in md
    assert 'id="s4-observability"' in md


def test_render_mock_angle_from_personas():
    md = _run_render(Path("."))
    # JD focus from personas S1 should appear
    assert "CI/CD pipelines" in md or "Startup pace" in md or "containerization" in md


def test_render_traps_from_personas():
    md = _run_render(Path("."))
    # Mock traps from S1 should appear (mentions AWS or GitLab CI)
    assert "AWS" in md
    assert "GitLab CI" in md


def test_render_optional_tag_on_helm():
    md = _run_render(Path("."))
    # Helm story is optional
    assert "optional" in md.lower()


def test_render_has_draft_header():
    md = _run_render(Path("."))
    assert "# Stories draft (devops)" in md
    assert "**Draft** generated:" in md


# ---------------------------------------------------------------------------
# run() tests
# ---------------------------------------------------------------------------


def test_run_dry_run_no_file_written(tmp_path: Path):
    if not _fixtures_ok():
        pytest.skip("stories mini fixtures missing")
    out = tmp_path / "stories.draft.md"
    summary = run(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        personas_path=_PERSONAS_MINI,
        out_path=out,
        prep_roles_path=_PREP_ROLES_MINI,
        require_reviewed=False,
        dry_run=True,
    )
    assert summary["mode"] == "dry-run"
    assert not out.exists()


def test_run_writes_draft_file(tmp_path: Path):
    if not _fixtures_ok():
        pytest.skip("stories mini fixtures missing")
    out = tmp_path / "stories.draft.md"
    summary = run(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        personas_path=_PERSONAS_MINI,
        out_path=out,
        prep_roles_path=_PREP_ROLES_MINI,
        require_reviewed=False,
        force=True,
    )
    assert summary["mode"] == "write"
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "<!-- jobfit:prep-stories:llm-input -->" in text


def test_run_raises_on_existing_without_force(tmp_path: Path):
    if not _fixtures_ok():
        pytest.skip("stories mini fixtures missing")
    out = tmp_path / "stories.draft.md"
    out.write_text("existing content", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run(
            role_slug="devops",
            context_path=_CONTEXT_MINI,
            claims_path=_CLAIMS_MINI,
            personas_path=_PERSONAS_MINI,
            out_path=out,
            prep_roles_path=_PREP_ROLES_MINI,
            require_reviewed=False,
        )


def test_run_raises_on_missing_reviewed(tmp_path: Path):
    if not _CONTEXT_MINI.is_file() or not _PERSONAS_MINI.is_file() or not _PREP_ROLES_MINI.is_file():
        pytest.skip("fixtures missing")
    claims = tmp_path / "claims_no_review.md"
    claims.write_text("# Claims — no reviewed marker\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Reviewed"):
        run(
            role_slug="devops",
            context_path=_CONTEXT_MINI,
            claims_path=claims,
            personas_path=_PERSONAS_MINI,
            out_path=tmp_path / "out.md",
            prep_roles_path=_PREP_ROLES_MINI,
        )


def test_run_raises_on_missing_prep_roles_yaml(tmp_path: Path):
    if not _fixtures_ok():
        pytest.skip("fixtures missing")
    with pytest.raises(FileNotFoundError, match="prep_roles.yaml"):
        run(
            role_slug="devops",
            context_path=_CONTEXT_MINI,
            claims_path=_CLAIMS_MINI,
            personas_path=_PERSONAS_MINI,
            out_path=tmp_path / "out.md",
            prep_roles_path=tmp_path / "nonexistent.yaml",
            require_reviewed=False,
        )


def test_run_with_enrichment(tmp_path: Path):
    if not _fixtures_ok():
        pytest.skip("fixtures missing")
    enrichment_file = tmp_path / "stories_enrichment.yaml"
    enrichment_file.write_text(
        "voice: first person, mid-level DevOps\n"
        "employers:\n"
        "  WORK_COMP_1:\n"
        "    industry: EdTech — LMS SaaS\n"
        "    display_name: my current employer\n"
        "    comment: I owned CI/CD end-to-end\n"
        "stories:\n"
        "  s1-ci-cd:\n"
        "    comment: Lead with release pain before naming tools\n",
        encoding="utf-8",
    )
    out = tmp_path / "stories.draft.md"
    summary = run(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        personas_path=_PERSONAS_MINI,
        out_path=out,
        prep_roles_path=_PREP_ROLES_MINI,
        enrichment_path=enrichment_file,
        require_reviewed=False,
        force=True,
    )
    assert summary["mode"] == "write"
    text = out.read_text(encoding="utf-8")
    # Enrichment employer context appears
    assert "EdTech" in text
    # Story comment appears
    assert "Lead with release pain" in text


def test_run_summary_story_count(tmp_path: Path):
    if not _fixtures_ok():
        pytest.skip("fixtures missing")
    out = tmp_path / "stories.draft.md"
    summary = run(
        role_slug="devops",
        context_path=_CONTEXT_MINI,
        claims_path=_CLAIMS_MINI,
        personas_path=_PERSONAS_MINI,
        out_path=out,
        prep_roles_path=_PREP_ROLES_MINI,
        require_reviewed=False,
        dry_run=True,
    )
    # S1=5, S4=5, S2=4 = 14 total
    assert summary["story_count"] == 14


def test_default_draft_path():
    assert default_draft_path("devops") == Path("prompts/prep/devops/stories.draft.md")


def test_extract_llm_input():
    md = "before\n<!-- jobfit:prep-stories:llm-input -->\ncontent\n<!-- /jobfit:prep-stories:llm-input -->\nafter"
    result = extract_llm_input(md)
    assert result == "content"


def test_extract_llm_input_fallback():
    md = "# Header\n\ncontent\n\n## How this file is used\n\nfooter"
    result = extract_llm_input(md)
    assert "# Header" in result
    assert "## How this file is used" not in result
