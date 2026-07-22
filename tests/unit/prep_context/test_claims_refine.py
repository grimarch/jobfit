"""Unit tests for prep claims LLM refine."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jobfit.prep_context.claims_refine import (
    build_user_prompt,
    default_llm_path,
    default_prompt_path,
    load_system_prompt,
    run,
    strip_markdown_fences,
    validate_refine_output,
)
from jobfit.prep_context.claims import extract_llm_input

_MIN_PROMPT_MD = """\
# Claims review prompt

## System / user prompt (copy below the line)

---

You refine a prep-claims DRAFT.

Fix Evidence bullets.

---

## After LLM

Manual steps here.
"""

_MIN_CV = "# CV\n\n**GitLab CI** bullet here.\n"
_MIN_DRAFT = """\
# Claim → Evidence (devops)

**Draft** generated: test

> Human workflow hint — not for LLM.

<!-- jobfit:prep-claims:llm-input -->

## Core DevOps

| Claim | Evidence | Status |
|---|---|---|
| **Docker** | bullet | ok |

<!-- jobfit:prep-claims:gaps -->
| Gap | Jobs | Count |
|---|---|---:|
| **AWS** | S1 | 1 |
<!-- /jobfit:prep-claims:gaps -->

<!-- /jobfit:prep-claims:llm-input -->

## How this file is used

Run merge command.
"""


def test_load_system_prompt(tmp_path: Path):
    path = tmp_path / "claims_review_prompt.md"
    path.write_text(_MIN_PROMPT_MD, encoding="utf-8")
    body = load_system_prompt(path)
    assert "You refine a prep-claims DRAFT" in body
    assert "Manual steps" not in body


def test_load_system_prompt_missing_marker(tmp_path: Path):
    path = tmp_path / "bad.md"
    path.write_text("# no marker\n", encoding="utf-8")
    with pytest.raises(ValueError, match="System / user prompt"):
        load_system_prompt(path)


def test_build_user_prompt():
    user = build_user_prompt(cv_text="CV body", draft_text="Draft body")
    assert "CV body" in user
    assert "Draft body" in user
    assert "Gaps Jobs/Count" in user


def test_extract_llm_input_excludes_footer():
    body = extract_llm_input(_MIN_DRAFT)
    assert "## Core DevOps" in body
    assert "jobfit:prep-claims:gaps" in body
    assert "How this file is used" not in body
    assert "Human workflow hint" not in body


def test_extract_llm_input_fallback_footer_heading():
    legacy = "# Draft\n\n## Claims\n\n| x | y |\n\n## How this file is used\n\nfooter"
    body = extract_llm_input(legacy)
    assert "## Claims" in body
    assert "How this file is used" not in body


def test_prepare_prompts_uses_llm_input_only(tmp_path: Path):
    from jobfit.prep_context.claims_refine import prepare_prompts

    cv = tmp_path / "cv.md"
    cv.write_text(_MIN_CV, encoding="utf-8")
    draft = tmp_path / "draft.md"
    draft.write_text(_MIN_DRAFT, encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text(_MIN_PROMPT_MD, encoding="utf-8")
    _, user = prepare_prompts(cv_path=cv, draft_path=draft, prompt_path=prompt)
    assert "## Core DevOps" in user
    assert "How this file is used" not in user
    assert "Run merge command" not in user


def test_strip_markdown_fences():
    assert strip_markdown_fences("```markdown\n# Hi\n```") == "# Hi"
    assert strip_markdown_fences("# Plain") == "# Plain"


def test_validate_refine_output_warnings():
    refined = "# Claim\n\n**Draft** generated\n"
    warnings = validate_refine_output(_MIN_DRAFT, refined)
    assert any("Gaps HTML markers" in w for w in warnings)


def test_default_paths():
    assert default_llm_path("devops") == Path("prompts/prep/devops/claims.llm.md")
    assert default_prompt_path("devops") == Path("prompts/prep/devops/claims_review_prompt.md")


def test_run_dry_run(tmp_path: Path):
    cv = tmp_path / "cv.md"
    cv.write_text(_MIN_CV, encoding="utf-8")
    draft = tmp_path / "draft.md"
    draft.write_text(_MIN_DRAFT, encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text(_MIN_PROMPT_MD, encoding="utf-8")
    out = tmp_path / "out.md"

    summary = run(
        role_slug="devops",
        cv_path=cv,
        draft_path=draft,
        out_path=out,
        prompt_path=prompt,
        dry_run=True,
    )
    assert summary["mode"] == "dry-run"
    assert not out.exists()


@patch("jobfit.prep_context.claims_refine.llm_complete")
@patch("jobfit.prep_context.claims_refine.resolve_key", return_value="test-key")
def test_run_writes_llm_output(mock_key: MagicMock, mock_complete: MagicMock, tmp_path: Path):
    cv = tmp_path / "cv.md"
    cv.write_text(_MIN_CV, encoding="utf-8")
    draft = tmp_path / "draft.md"
    draft.write_text(_MIN_DRAFT, encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text(_MIN_PROMPT_MD, encoding="utf-8")
    out = tmp_path / "out.md"

    mock_complete.return_value = "```markdown\n# Claim\n\n**Draft** generated\n\n" + _MIN_DRAFT + "\n```"

    summary = run(
        role_slug="devops",
        cv_path=cv,
        draft_path=draft,
        out_path=out,
        prompt_path=prompt,
        force=True,
        api_key="test-key",
    )
    assert summary["mode"] == "write"
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Claim")
    assert "jobfit:prep-claims:gaps" in text
    mock_complete.assert_called_once()


def test_load_devops_repo_prompt():
    path = Path("prompts/prep/devops/claims_review_prompt.md")
    if not path.is_file():
        pytest.skip("devops claims_review_prompt.md not in workspace")
    body = load_system_prompt(path)
    assert "prep-claims DRAFT" in body
    assert "Gaps table" in body
