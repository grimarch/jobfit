"""Unit tests for prep claims draft."""

from pathlib import Path

import pytest

from jobfit.prep_context.claims import (
    GapLineEntry,
    aggregate_gaps,
    build_skill_claims,
    default_draft_path,
    default_gap_lines_path,
    default_reviewed_path,
    extract_experience_bullets,
    extract_llm_input,
    load_gap_lines,
    parse_starred_blocks,
    render_claims_md,
    render_gaps_block,
    run,
)
from jobfit.prep_context.claims_layout import (
    build_layout_sections,
    default_user_layout_path,
    repo_layout_path,
    resolve_layout_path,
)
from jobfit.prep_context.claims_merge import merge_gaps_block, parse_gaps_table
from jobfit.roles import ROLES

_MINI_CV = """
SKILLS & TECHNOLOGIES
   DevOps & Platform: Docker, Kubernetes, Terraform, GitLab CI/CD

PROFESSIONAL EXPERIENCE
  DevOps Engineer – Acme                                   Jan 2023 - Present
   - Designed GitLab CI/CD pipelines with Semgrep SAST — deploy time 45 to 10 minutes.
   - Provisioned GCP with Terraform: 29 resources across 2 stacks.
   - Implemented HashiCorp Vault with RBAC and AppRole for API secret delivery.

EDUCATION
Bachelor
"""

_CONTEXT = """
## Starred jobs
### S1
- refnr: job-1
- title: DevOps Engineer
- gaps_vs_cv: [AWS, Azure]
- prep_label: fit

### S2
- refnr: job-2
- title: Platform Engineer
- gaps_vs_cv: [AWS, IAM]
- prep_label: stretch

### S3
- refnr: job-3
- title: Skip me
- gaps_vs_cv: [Jenkins]
- prep_label: skip-for-prep
"""

_REVIEWED_CLAIMS = """\
# Claim → Evidence (devops)

**Reviewed:** 2026-07-20

## Core DevOps & platform

| Claim (interview) | Evidence (CV bullet + metric) | Status |
|---|---|---|
| **GitLab CI/CD** | My edited evidence | ok |

<!-- jobfit:prep-claims:gaps -->
## Gaps vs prep shortlist (honest transfer lines)

Old intro.

| Gap | Jobs | Count | Do not claim | Say instead |
|---|---|---:|---|---|
| **AWS** | S1 | 1 | Keep do not | Keep say line |
<!-- /jobfit:prep-claims:gaps -->

---

## Do not claim (hard stop)

- AWS production
"""


def test_extract_experience_bullets():
    bullets = extract_experience_bullets(_MINI_CV)
    assert len(bullets) == 3
    assert "GitLab" in bullets[0]


def test_build_skill_claims_matches_bullets():
    role = ROLES["devops"]
    claims = build_skill_claims(_MINI_CV, role)
    by_skill = {c.skill: c for c in claims}
    assert "GitLab CI" in by_skill
    assert by_skill["GitLab CI"].status == "ok"
    assert "45" in by_skill["GitLab CI"].evidence
    assert "Terraform" in by_skill
    assert by_skill["Terraform"].status == "ok"


def test_build_layout_sections_generic_structure():
    repo = repo_layout_path("devops")
    layout = build_layout_sections(_MINI_CV, "devops", layout_file=repo)
    assert layout is not None
    titles = [s.title for s in layout.sections]
    assert "CI/CD & delivery" in titles
    assert layout.source_path == repo


def test_build_layout_sections_user_tuned_vault_match():
    example = Path("data/user/devops/input/claims_layout.yaml.example")
    if not example.is_file():
        pytest.skip("claims_layout.yaml.example not present")
    layout = build_layout_sections(_MINI_CV, "devops", layout_file=example)
    assert layout is not None
    core = next(s for s in layout.sections if s.title == "Core DevOps & platform")
    vault_rows = [r for r in core.rows if "Vault" in r.label]
    assert vault_rows
    assert "AppRole" in vault_rows[0].evidence or "RBAC" in vault_rows[0].evidence


def test_build_layout_sections_all_bullets_and_reuse():
    example = Path("data/user/devops/input/claims_layout.yaml.example")
    if not example.is_file():
        pytest.skip("claims_layout.yaml.example not present")
    cv = Path("prompts/CV.md")
    if not cv.is_file():
        pytest.skip("prompts/CV.md not present")
    cv_text = cv.read_text(encoding="utf-8")
    layout = build_layout_sections(cv_text, "devops", layout_file=example)
    assert layout is not None
    lang = next(s for s in layout.sections if "Languages" in s.title)
    pg = next(r for r in lang.rows if "PostgreSQL" in r.label)
    assert pg.status == "ok"
    assert "JobFit" in pg.evidence
    assert "externalizing PostgreSQL" in pg.evidence
    fastapi = next(r for r in lang.rows if "FastAPI" in r.label)
    assert fastapi.status == "ok"
    assert "GrimWaves" in fastapi.evidence
    assert "JobFit" in fastapi.evidence
    sec = next(s for s in layout.sections if s.title.startswith("Security tools"))
    semgrep = next(r for r in sec.rows if "Semgrep" in r.label)
    zap = next(r for r in sec.rows if "ZAP" in r.label)
    assert semgrep.status == "ok"
    assert zap.status == "ok"
    assert "Semgrep" in semgrep.evidence
    assert "OWASP ZAP" in zap.evidence


def test_resolve_layout_path_prefers_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    user_dir = tmp_path / "devops" / "input"
    user_dir.mkdir(parents=True)
    user_layout = user_dir / "claims_layout.yaml"
    user_layout.write_text("slug: devops\nsections: []\n", encoding="utf-8")

    def fake_role_input_dir(role_slug: str) -> Path:
        assert role_slug == "devops"
        return user_dir

    monkeypatch.setattr("jobfit.config.role_input_dir", fake_role_input_dir)
    assert resolve_layout_path("devops") == user_layout
    assert resolve_layout_path("devops") != repo_layout_path("devops")


def test_default_user_layout_path():
    path = default_user_layout_path("devops")
    assert path.name == "claims_layout.yaml"
    assert "devops" in path.as_posix()


def test_parse_starred_blocks():
    rows = parse_starred_blocks(_CONTEXT)
    assert len(rows) == 3
    assert rows[0].sid == "S1"
    assert rows[0].gaps == ["AWS", "Azure"]


def test_aggregate_gaps_excludes_skip():
    rows = parse_starred_blocks(_CONTEXT)
    gaps = aggregate_gaps(rows)
    skills = {g.skill for g in gaps}
    assert "AWS" in skills
    assert "IAM" in skills
    assert "Jenkins" not in skills
    aws = next(g for g in gaps if g.skill == "AWS")
    assert aws.count == 2
    assert set(aws.jobs) == {"S1", "S2"}
    assert aws.say_instead == ""


def test_aggregate_gaps_uses_gap_lines():
    rows = parse_starred_blocks(_CONTEXT)
    gaps = aggregate_gaps(
        rows,
        gap_lines={
            "AWS": GapLineEntry(
                say_instead="Custom AWS line",
                do_not_claim="No AWS prod",
            )
        },
    )
    aws = next(g for g in gaps if g.skill == "AWS")
    assert aws.say_instead == "Custom AWS line"
    assert aws.do_not_claim == "No AWS prod"
    iam = next(g for g in gaps if g.skill == "IAM")
    assert iam.say_instead == ""


def test_load_gap_lines(tmp_path: Path):
    path = tmp_path / "gap_lines.yaml"
    path.write_text(
        "AWS:\n  say_instead: line one\n  do_not_claim: no aws\nAzure: flat line\n",
        encoding="utf-8",
    )
    loaded = load_gap_lines(path)
    assert loaded["AWS"].say_instead == "line one"
    assert loaded["AWS"].do_not_claim == "no aws"
    assert loaded["Azure"].say_instead == "flat line"
    assert load_gap_lines(tmp_path / "missing.yaml") == {}


def test_default_gap_lines_path():
    path = default_gap_lines_path("devops")
    assert path.name == "gap_lines.yaml"
    assert "devops" in path.as_posix()


def test_render_gaps_block_placeholders():
    gaps = aggregate_gaps(parse_starred_blocks(_CONTEXT))
    block = render_gaps_block(
        layout_heading="## Gaps vs prep shortlist",
        layout_intro="intro",
        gaps=gaps,
    )
    assert "<!-- jobfit:prep-claims:gaps -->" in block
    assert "| **AWS** | S1, S2 | 2 | — | — |" in block


def test_render_claims_md_structured_sections():
    role = ROLES["devops"]
    claims = build_skill_claims(_MINI_CV, role)
    gaps = aggregate_gaps(parse_starred_blocks(_CONTEXT))
    md = render_claims_md(
        cv_path=Path("prompts/CV.md"),
        context_path=Path("prompts/prep/devops/context.md"),
        role_slug="devops",
        claims=claims,
        gaps=gaps,
        gap_labels=frozenset({"fit", "stretch", "brand-only"}),
        cv_text=_MINI_CV,
    )
    assert "## CI/CD & delivery" in md
    assert "## Gaps vs prep shortlist" in md
    assert "## Quick reference" in md
    assert "## Do not claim (hard stop)" in md
    assert "jobfit:prep-claims:gaps" in md
    assert "jobfit:prep-claims:llm-input" in md
    assert "## How this file is used" in md
    llm_body = extract_llm_input(md)
    assert "## CI/CD & delivery" in llm_body
    assert "How this file is used" not in llm_body


def test_default_claims_paths():
    assert default_draft_path("devops") == Path("prompts/prep/devops/claims.draft.md")
    assert default_reviewed_path("devops") == Path("prompts/prep/devops/claims.md")


def test_merge_preserves_claims_and_gap_wording(tmp_path: Path):
    out = tmp_path / "claims.md"
    out.write_text(_REVIEWED_CLAIMS, encoding="utf-8")
    gaps = aggregate_gaps(parse_starred_blocks(_CONTEXT))
    block = render_gaps_block(
        layout_heading="## Gaps vs prep shortlist (honest transfer lines)",
        layout_intro="updated intro",
        gaps=gaps,
        existing_gaps=parse_gaps_table(_REVIEWED_CLAIMS),
    )
    merged = merge_gaps_block(_REVIEWED_CLAIMS, block)
    out.write_text(merged, encoding="utf-8")
    text = out.read_text(encoding="utf-8")
    assert "My edited evidence" in text
    assert "Keep say line" in text
    assert "Keep do not" in text
    assert "| **AWS** | S1, S2 | 2 |" in text


def test_run_writes_structured_file(tmp_path: Path):
    cv = tmp_path / "cv.md"
    cv.write_text(_MINI_CV, encoding="utf-8")
    ctx = tmp_path / "context.md"
    ctx.write_text(_CONTEXT, encoding="utf-8")
    out = tmp_path / "claims.md"
    gap_lines = tmp_path / "gap_lines.yaml"
    gap_lines.write_text("AWS:\n  say_instead: cached honest line\n", encoding="utf-8")

    summary = run(
        role_slug="devops",
        cv_path=cv,
        context_path=ctx,
        out_path=out,
        gap_lines_path=gap_lines,
        force=True,
    )
    assert summary["mode"] == "write"
    assert summary["gaps"] >= 2
    text = out.read_text(encoding="utf-8")
    assert "Draft" in text
    assert "cached honest line" in text
    assert "## CI/CD & delivery" in text


def test_run_merge_on_reviewed_file(tmp_path: Path):
    cv = tmp_path / "cv.md"
    cv.write_text(_MINI_CV, encoding="utf-8")
    ctx = tmp_path / "context.md"
    ctx.write_text(_CONTEXT, encoding="utf-8")
    out = tmp_path / "claims.md"
    out.write_text(_REVIEWED_CLAIMS, encoding="utf-8")

    summary = run(
        role_slug="devops",
        cv_path=cv,
        context_path=ctx,
        out_path=out,
    )
    assert summary["mode"] == "merge"
    text = out.read_text(encoding="utf-8")
    assert "My edited evidence" in text
    assert "| **AWS** | S1, S2 | 2 |" in text


def test_run_refuses_overwrite_without_force_or_merge(tmp_path: Path):
    cv = tmp_path / "cv.md"
    cv.write_text(_MINI_CV, encoding="utf-8")
    out = tmp_path / "claims.md"
    out.write_text("**Draft** generated\n\n## Claims\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run(role_slug="devops", cv_path=cv, context_path=None, out_path=out, force=False)
