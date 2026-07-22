"""Unit tests for prep personas LLM refine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jobfit.prep_context.personas_refine import (
    _extract_claims_excerpt,
    _extract_gap_lines,
    build_user_prompt,
    default_draft_input_path,
    default_llm_path,
    default_prompt_path,
    load_system_prompt,
    run,
    strip_markdown_fences,
    validate_refine_output,
)
from jobfit.prep_context.personas import extract_llm_input

_MIN_PROMPT_MD = """\
# Personas review prompt

## System / user prompt (copy below the line)

---

You refine a **prep-personas DRAFT**.

Keep gap lines verbatim. Fill JD focus from jd_excerpt.

---

## After LLM

Spot-check gaps, promote to personas.md.
"""

_MIN_CV = "# CV\n\n**GitLab CI** pipelines — 45→10 min deploy.\n"

_MIN_CLAIMS = """\
**Reviewed:** 2026-07-22

<!-- jobfit:prep-claims:gaps -->
## Gaps
| Gap | Jobs | Count | Do not claim | Say instead |
|---|---|---:|---|---|
| **AWS** | S1 | 1 | Production AWS | GCP primary |
<!-- /jobfit:prep-claims:gaps -->

## Do not claim (hard stop)

- Production AWS

## Quick reference — best bullets by interview theme

| Theme | Lead bullet |
|---|---|
| CI/CD | GitLab: 45→10 min |
"""

_MIN_DRAFT = """\
# Prep roles (devops)

**Draft** generated: 2026-07-22T00:00:00Z

<!-- jobfit:prep-personas:llm-input -->

| Prep role | Job | Company | prep_label | Archetype | Primary gaps |
|---|---|---|---|---|---|
| Primary | S1 — DevOps | TestCo | fit | startup | AWS |

## Mock order

1. **S1** (Primary) — fit

---

## S1 — Primary (startup)

**Company:** TestCo
**prep_label:** fit · **refnr:** 001

**JD focus:** _TODO — refine from jd_excerpt_

**Lead from claims:** _TODO — refine: 3–5 ok claims_

**Gaps for this job:**
- **AWS** — Do not claim: Production AWS. Say: GCP primary

**Mock traps:** _TODO — refine_

**Language:** _TODO — refine from context: EN_

**Stories to write (Phase 2):** _TODO — refine_

---

## Anchors

| Job | One-line anchor |
|---|---|
| S1 | _TODO — refine_ |

<!-- /jobfit:prep-personas:llm-input -->

---

## How this file is used

- `prep-personas refine` reads content between llm-input markers.
"""


# ---------------------------------------------------------------------------
# load_system_prompt
# ---------------------------------------------------------------------------


def test_load_system_prompt(tmp_path: Path):
    path = tmp_path / "personas_review_prompt.md"
    path.write_text(_MIN_PROMPT_MD, encoding="utf-8")
    body = load_system_prompt(path)
    assert "prep-personas DRAFT" in body
    assert "Spot-check gaps" not in body
    assert "## After LLM" not in body


def test_load_system_prompt_missing_marker(tmp_path: Path):
    path = tmp_path / "bad.md"
    path.write_text("# no marker\n", encoding="utf-8")
    with pytest.raises(ValueError, match="System / user prompt"):
        load_system_prompt(path)


def test_load_system_prompt_missing_fence(tmp_path: Path):
    path = tmp_path / "bad.md"
    path.write_text("## System / user prompt\n\nno fence here\n", encoding="utf-8")
    with pytest.raises(ValueError, match="---"):
        load_system_prompt(path)


# ---------------------------------------------------------------------------
# build_user_prompt
# ---------------------------------------------------------------------------


def test_build_user_prompt_contains_sections():
    user = build_user_prompt(cv_text="CV body", claims_text=_MIN_CLAIMS, draft_text="Draft body")
    assert "CV body" in user
    assert "Draft body" in user
    assert "CLAIMS SoT" in user
    assert "Production AWS" in user  # from do not claim
    assert "GCP primary" in user  # from gaps


def test_extract_claims_excerpt_has_gaps_and_dnc():
    excerpt = _extract_claims_excerpt(_MIN_CLAIMS)
    assert "<!-- jobfit:prep-claims:gaps -->" in excerpt
    assert "Production AWS" in excerpt
    assert "## Do not claim" in excerpt
    assert "## Quick reference" in excerpt


# ---------------------------------------------------------------------------
# extract_llm_input
# ---------------------------------------------------------------------------


def test_extract_llm_input_excludes_footer():
    body = extract_llm_input(_MIN_DRAFT)
    assert "## S1 — Primary" in body
    assert "Gaps for this job" in body
    assert "How this file is used" not in body


# ---------------------------------------------------------------------------
# strip_markdown_fences
# ---------------------------------------------------------------------------


def test_strip_markdown_fences():
    assert strip_markdown_fences("```markdown\n# Hi\n```") == "# Hi"
    assert strip_markdown_fences("```md\n# Hi\n```") == "# Hi"
    assert strip_markdown_fences("# Plain") == "# Plain"


# ---------------------------------------------------------------------------
# _extract_gap_lines
# ---------------------------------------------------------------------------


def test_extract_gap_lines():
    lines = _extract_gap_lines(_MIN_DRAFT)
    assert len(lines) == 1
    assert "AWS" in lines[0]
    assert "Production AWS" in lines[0]


# ---------------------------------------------------------------------------
# validate_refine_output
# ---------------------------------------------------------------------------


def test_validate_refine_output_clean():
    refined = (
        "# Prep roles (devops)\n\n**Draft** generated: x\n\n"
        "<!-- jobfit:prep-personas:llm-input -->\n\n"
        "## S1 — Primary (startup)\n\n"
        "**Gaps for this job:**\n"
        "- **AWS** — Do not claim: Production AWS. Say: GCP primary\n\n"
        "<!-- /jobfit:prep-personas:llm-input -->\n"
    )
    warnings = validate_refine_output(_MIN_DRAFT, refined)
    assert warnings == []


def test_validate_refine_output_missing_markers():
    refined = "# Prep roles\n\n**Draft** generated: x\n\n## S1 — Primary (startup)\n\n"
    warnings = validate_refine_output(_MIN_DRAFT, refined)
    assert any("llm-input" in w for w in warnings)


def test_validate_refine_output_changed_gap_line():
    refined = (
        "# Prep roles (devops)\n\n**Draft** generated: x\n\n"
        "<!-- jobfit:prep-personas:llm-input -->\n\n"
        "## S1 — Primary (startup)\n\n"
        "**Gaps for this job:**\n"
        "- **AWS** — Do not claim: CHANGED. Say: CHANGED\n\n"  # changed!
        "<!-- /jobfit:prep-personas:llm-input -->\n"
    )
    warnings = validate_refine_output(_MIN_DRAFT, refined)
    assert any("Gap line" in w for w in warnings)


def test_validate_refine_output_missing_section():
    refined = (
        "# Prep roles\n\n**Draft** generated: x\n\n"
        "<!-- jobfit:prep-personas:llm-input -->\n\n"
        "<!-- /jobfit:prep-personas:llm-input -->\n"
    )
    warnings = validate_refine_output(_MIN_DRAFT, refined)
    assert any("S1" in w for w in warnings)


def test_validate_refine_output_company_placeholder():
    refined = (
        "# Prep roles\n\n**Draft** generated: x\n\n"
        "**JD focus:** [COMPANY] needs DevOps.\n\n"
        "<!-- jobfit:prep-personas:llm-input -->\n\n"
        "<!-- /jobfit:prep-personas:llm-input -->\n"
    )
    warnings = validate_refine_output(_MIN_DRAFT, refined)
    assert any("COMPANY" in w for w in warnings)


# ---------------------------------------------------------------------------
# default paths
# ---------------------------------------------------------------------------


def test_default_paths():
    assert default_llm_path("devops") == Path("prompts/prep/devops/personas.llm.md")
    assert default_prompt_path("devops") == Path("prompts/prep/devops/personas_review_prompt.md")
    assert default_draft_input_path("devops") == Path("prompts/prep/devops/personas.draft.md")


# ---------------------------------------------------------------------------
# run() — dry-run and mocked LLM write
# ---------------------------------------------------------------------------


def test_run_dry_run(tmp_path: Path):
    cv = tmp_path / "cv.md"
    cv.write_text(_MIN_CV, encoding="utf-8")
    claims = tmp_path / "claims.md"
    claims.write_text(_MIN_CLAIMS, encoding="utf-8")
    draft = tmp_path / "draft.md"
    draft.write_text(_MIN_DRAFT, encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text(_MIN_PROMPT_MD, encoding="utf-8")
    out = tmp_path / "out.md"

    summary = run(
        role_slug="devops",
        cv_path=cv,
        claims_path=claims,
        draft_path=draft,
        out_path=out,
        prompt_path=prompt,
        dry_run=True,
    )
    assert summary["mode"] == "dry-run"
    assert not out.exists()
    assert int(summary["system_chars"]) > 0  # type: ignore[arg-type]
    assert int(summary["user_chars"]) > 0  # type: ignore[arg-type]


@patch("jobfit.prep_context.personas_refine.llm_complete")
@patch("jobfit.prep_context.personas_refine.resolve_key", return_value="test-key")
def test_run_writes_llm_output(mock_key: MagicMock, mock_complete: MagicMock, tmp_path: Path):
    cv = tmp_path / "cv.md"
    cv.write_text(_MIN_CV, encoding="utf-8")
    claims = tmp_path / "claims.md"
    claims.write_text(_MIN_CLAIMS, encoding="utf-8")
    draft = tmp_path / "draft.md"
    draft.write_text(_MIN_DRAFT, encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text(_MIN_PROMPT_MD, encoding="utf-8")
    out = tmp_path / "out.md"

    mock_complete.return_value = (
        "```markdown\n# Prep roles (devops)\n\n**Draft** generated: x\n\n"
        "<!-- jobfit:prep-personas:llm-input -->\n\n"
        "## S1 — Primary (startup)\n\n"
        "**Gaps for this job:**\n"
        "- **AWS** — Do not claim: Production AWS. Say: GCP primary\n\n"
        "<!-- /jobfit:prep-personas:llm-input -->\n```"
    )

    summary = run(
        role_slug="devops",
        cv_path=cv,
        claims_path=claims,
        draft_path=draft,
        out_path=out,
        prompt_path=prompt,
        force=True,
        api_key="test-key",
    )
    assert summary["mode"] == "write"
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Prep roles")
    assert "jobfit:prep-personas:llm-input" in text
    mock_complete.assert_called_once()


def test_run_file_exists_error(tmp_path: Path):
    cv = tmp_path / "cv.md"
    cv.write_text(_MIN_CV, encoding="utf-8")
    claims = tmp_path / "claims.md"
    claims.write_text(_MIN_CLAIMS, encoding="utf-8")
    draft = tmp_path / "draft.md"
    draft.write_text(_MIN_DRAFT, encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text(_MIN_PROMPT_MD, encoding="utf-8")
    out = tmp_path / "out.md"
    out.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run(
            role_slug="devops",
            cv_path=cv,
            claims_path=claims,
            draft_path=draft,
            out_path=out,
            prompt_path=prompt,
        )


def test_run_force_overwrites(tmp_path: Path):
    cv = tmp_path / "cv.md"
    cv.write_text(_MIN_CV, encoding="utf-8")
    claims = tmp_path / "claims.md"
    claims.write_text(_MIN_CLAIMS, encoding="utf-8")
    draft = tmp_path / "draft.md"
    draft.write_text(_MIN_DRAFT, encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text(_MIN_PROMPT_MD, encoding="utf-8")
    out = tmp_path / "out.md"
    out.write_text("existing", encoding="utf-8")

    summary = run(
        role_slug="devops",
        cv_path=cv,
        claims_path=claims,
        draft_path=draft,
        out_path=out,
        prompt_path=prompt,
        dry_run=True,
        force=True,
    )
    assert summary["mode"] == "dry-run"


def test_load_devops_repo_prompt():
    path = Path("prompts/prep/devops/personas_review_prompt.md")
    if not path.is_file():
        pytest.skip("devops personas_review_prompt.md not in workspace")
    body = load_system_prompt(path)
    assert "prep-personas" in body.lower() or "personas" in body.lower()
