"""Integration tests for prep context export.

Calls the real export logic against the test database.
No LLM calls happen — only DB queries and local file I/O.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROLE = "devops"

_FIXTURE_CV = """\
# CV — Test fixture

## Experience
- DevOps Engineer at Acme Corp (2020–present)
  - Built Kubernetes clusters on AWS
  - Infrastructure as code with Terraform
  - CI/CD with GitHub Actions

## Skills
Docker, Kubernetes, Terraform, AWS, Ansible, Helm, Prometheus
"""


def _get_starred_refnr(role: str = _ROLE) -> str | None:
    """Return the first starred refnr for *role* from the DB, or None."""
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel

    with get_session() as session:
        row = (
            session.query(ClsModel.refnr)
            .filter(
                ClsModel.role == role,
                ClsModel.starred_at.isnot(None),
            )
            .first()
        )
    return row[0] if row else None


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def cv_file(tmp_path: Path) -> Path:
    p = tmp_path / "cv_fixture.md"
    p.write_text(_FIXTURE_CV, encoding="utf-8")
    return p


@pytest.fixture()
def out_md(tmp_path: Path) -> Path:
    return tmp_path / "prep_context.md"


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_export_writes_md_only(cv_file: Path, out_md: Path) -> None:
    """Export creates exactly one .md file and no .json file next to it."""
    from jobfit.prep.context import export as prep_export

    prep_export.run(
        role_slug=_ROLE,
        cv_path=cv_file,
        out_path=out_md,
        jd_excerpt_chars=200,
        market_scope="sm",
        include_closed=True,
        dry_run=False,
    )

    assert out_md.exists(), "Output .md file was not created"
    json_path = out_md.with_suffix(".json")
    assert not json_path.exists(), f"Unexpected .json file created at {json_path}"


def test_export_md_contains_refnr_for_starred(cv_file: Path, out_md: Path) -> None:
    """Each starred block in the output md has a - refnr: line matching a DB starred job."""
    starred_refnr = _get_starred_refnr()
    if starred_refnr is None:
        pytest.skip("No starred jobs for role 'devops' in test DB")

    from jobfit.prep.context import export as prep_export

    prep_export.run(
        role_slug=_ROLE,
        cv_path=cv_file,
        out_path=out_md,
        jd_excerpt_chars=200,
        market_scope="sm",
        include_closed=True,
        dry_run=False,
    )

    content = out_md.read_text(encoding="utf-8")
    refnr_values = re.findall(r"^- refnr:\s*(.+)$", content, re.MULTILINE)
    assert len(refnr_values) > 0, "No '- refnr:' lines found in output md"
    assert starred_refnr in refnr_values, (
        f"DB starred refnr {starred_refnr!r} not found in output refnrs: {refnr_values}"
    )


def test_export_md_has_empty_human_slots(cv_file: Path, out_md: Path) -> None:
    """prep_label: and why_starred: are present as empty slots for human editing."""
    starred_refnr = _get_starred_refnr()
    if starred_refnr is None:
        pytest.skip("No starred jobs for role 'devops' in test DB")

    from jobfit.prep.context import export as prep_export

    prep_export.run(
        role_slug=_ROLE,
        cv_path=cv_file,
        out_path=out_md,
        jd_excerpt_chars=200,
        market_scope="sm",
        include_closed=True,
        dry_run=False,
    )

    content = out_md.read_text(encoding="utf-8")
    assert "- prep_label: " in content, "Missing empty '- prep_label:' slot"
    assert "- why_starred: " in content, "Missing empty '- why_starred:' slot"


def test_export_md_has_how_to_use_section(cv_file: Path, out_md: Path) -> None:
    """Output md ends with a ## How to use section."""
    from jobfit.prep.context import export as prep_export

    prep_export.run(
        role_slug=_ROLE,
        cv_path=cv_file,
        out_path=out_md,
        jd_excerpt_chars=200,
        market_scope="sm",
        include_closed=True,
        dry_run=False,
    )

    content = out_md.read_text(encoding="utf-8")
    assert "## How to use" in content, "Missing '## How to use' section in output md"


def test_export_merge_preserves_human_fields(cv_file: Path, out_md: Path) -> None:
    """Re-export with merge restores why_starred and prep_label from the previous run."""
    starred_refnr = _get_starred_refnr()
    if starred_refnr is None:
        pytest.skip("No starred jobs for role 'devops' in test DB")

    from jobfit.prep.context import export as prep_export

    # First export — write empty slots.
    prep_export.run(
        role_slug=_ROLE,
        cv_path=cv_file,
        out_path=out_md,
        jd_excerpt_chars=200,
        market_scope="sm",
        include_closed=True,
        dry_run=False,
    )

    # Simulate human edits by patching the file directly.
    content = out_md.read_text(encoding="utf-8")
    content = content.replace(
        f"- refnr: {starred_refnr}\n- title:",
        f"- refnr: {starred_refnr}\n- title:",
        1,
    )
    # Inject human values into the block for starred_refnr.
    content = re.sub(
        r"(- refnr: " + re.escape(starred_refnr) + r".*?- prep_label:)\s*\n(- why_starred:)\s*",
        r"\1 stretch\n\2 chosen for brand value\n",
        content,
        count=1,
        flags=re.DOTALL,
    )
    out_md.write_text(content, encoding="utf-8")

    # Second export — merge should restore the human-edited values.
    prep_export.run(
        role_slug=_ROLE,
        cv_path=cv_file,
        out_path=out_md,
        jd_excerpt_chars=200,
        market_scope="sm",
        include_closed=True,
        dry_run=False,
    )

    merged = out_md.read_text(encoding="utf-8")
    assert "- prep_label: stretch" in merged, "prep_label not preserved after merge"
    assert "- why_starred: chosen for brand value" in merged, "why_starred not preserved after merge"


def test_export_no_merge_discards_human_fields(cv_file: Path, out_md: Path) -> None:
    """--no-merge overwrites without restoring human-edited fields."""
    starred_refnr = _get_starred_refnr()
    if starred_refnr is None:
        pytest.skip("No starred jobs for role 'devops' in test DB")

    from jobfit.prep.context import export as prep_export

    prep_export.run(
        role_slug=_ROLE,
        cv_path=cv_file,
        out_path=out_md,
        jd_excerpt_chars=200,
        market_scope="sm",
        include_closed=True,
        dry_run=False,
    )

    content = out_md.read_text(encoding="utf-8")
    content = re.sub(r"- prep_label:\s*\n", "- prep_label: fit\n", content, count=1)
    out_md.write_text(content, encoding="utf-8")

    prep_export.run(
        role_slug=_ROLE,
        cv_path=cv_file,
        out_path=out_md,
        jd_excerpt_chars=200,
        market_scope="sm",
        include_closed=True,
        dry_run=False,
        no_merge=True,
    )

    fresh = out_md.read_text(encoding="utf-8")
    assert "- prep_label: fit" not in fresh, "no_merge must discard old prep_label"


def test_export_dry_run_writes_nothing(cv_file: Path, out_md: Path) -> None:
    """--dry-run prints a summary but creates no output file."""
    from jobfit.prep.context import export as prep_export

    prep_export.run(
        role_slug=_ROLE,
        cv_path=cv_file,
        out_path=out_md,
        jd_excerpt_chars=200,
        market_scope="sm",
        include_closed=True,
        dry_run=True,
    )

    assert not out_md.exists(), "--dry-run must not write any file"


def _get_starred_firma(role: str = _ROLE) -> str | None:
    """Return firma for the first starred job for *role*, or None."""
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel, Job

    with get_session() as session:
        row = (
            session.query(ClsModel, Job)
            .join(Job, ClsModel.refnr == Job.refnr)
            .filter(
                ClsModel.role == role,
                ClsModel.starred_at.isnot(None),
            )
            .first()
        )
    if not row:
        return None
    cls_row, job_row = row
    return cls_row.firma or job_row.firma or None


def test_export_omits_company_by_default(cv_file: Path, out_md: Path) -> None:
    """Default export does not write - company: lines."""
    starred_refnr = _get_starred_refnr()
    if starred_refnr is None:
        pytest.skip("No starred jobs for role 'devops' in test DB")

    from jobfit.prep.context import export as prep_export

    prep_export.run(
        role_slug=_ROLE,
        cv_path=cv_file,
        out_path=out_md,
        jd_excerpt_chars=200,
        market_scope="sm",
        include_closed=True,
        dry_run=False,
    )

    content = out_md.read_text(encoding="utf-8")
    assert "- company:" not in content


def test_export_include_company_writes_firma(cv_file: Path, out_md: Path) -> None:
    """--include-company writes employer name from DB; jd_excerpt stays redacted."""
    starred_refnr = _get_starred_refnr()
    firma = _get_starred_firma()
    if starred_refnr is None or not firma:
        pytest.skip("No starred job with firma for role 'devops' in test DB")

    from jobfit.prep.context import export as prep_export

    prep_export.run(
        role_slug=_ROLE,
        cv_path=cv_file,
        out_path=out_md,
        jd_excerpt_chars=200,
        market_scope="sm",
        include_closed=True,
        dry_run=False,
        include_company=True,
    )

    content = out_md.read_text(encoding="utf-8")
    assert f"- company: {firma}" in content
    assert "**company**" in content
