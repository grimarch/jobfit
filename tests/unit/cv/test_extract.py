"""Unit tests for jobfit.cv.extract and related CV profile loading."""

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jobfit.cv.extract import extract_profile, extract_text
from jobfit.cv.io import load_cv_contact, load_cv_profile
from jobfit.dashboards.scoring import skills_from_text
from jobfit.roles.devops import ROLE


# ── extract_text ──────────────────────────────────────────────────────────────

def test_extract_text_md(tmp_path: Path) -> None:
    f = tmp_path / "cv.md"
    f.write_text("# John Doe\nDevOps Engineer")
    assert extract_text(f) == "# John Doe\nDevOps Engineer"


def test_extract_text_txt(tmp_path: Path) -> None:
    f = tmp_path / "cv.txt"
    f.write_text("Plain text CV")
    assert extract_text(f) == "Plain text CV"


def test_extract_text_pdf(tmp_path: Path) -> None:
    import pypdf
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    out = tmp_path / "empty.pdf"
    with open(out, "wb") as fh:
        w.write(fh)
    result = extract_text(out)
    assert isinstance(result, str)


# ── skills_from_text ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_skills", [
    ("We use Docker and kubernetes in production", {"Docker", "Kubernetes"}),
    ("Terraform and Ansible for IaC", {"Terraform", "Ansible"}),
    ("No relevant skills here", set()),
    ("k8s cluster managed with helm charts", {"Kubernetes", "Helm"}),
    ("AWS EKS and GitHub Actions CI/CD", {"AWS", "EKS", "GitHub Actions"}),
])
def test_skills_from_text(text: str, expected_skills: set[str]) -> None:
    detected = skills_from_text(text, ROLE.skills)
    assert expected_skills.issubset(detected)


def test_skills_from_text_empty() -> None:
    assert skills_from_text("", ROLE.skills) == frozenset()


def test_skills_from_text_returns_frozenset() -> None:
    result = skills_from_text("Python and Bash", ROLE.skills)
    assert isinstance(result, frozenset)


# ── extract_profile (mocked Claude API) ───────────────────────────────────────

_SAMPLE_PROFILE = {
    "german_level": "B2",
    "english_level": "advanced",
    "experience_years": 5,
    "seniority": "mid",
    "education": "bachelor",
    "certifications": ["DTB B2"],
    "target_locations": [],
    "work_mode_preference": "hybrid",
}


@patch("jobfit.cv.extract.llm_complete")
def test_extract_profile_plain_json(mock_complete: MagicMock) -> None:
    mock_complete.return_value = json.dumps(_SAMPLE_PROFILE)
    result = extract_profile("some cv text", api_key="test-key")
    assert result["german_level"] == "B2"
    assert result["experience_years"] == 5


@patch("jobfit.cv.extract.llm_complete")
def test_extract_profile_sends_anonymized_text(mock_complete: MagicMock) -> None:
    cv_text = textwrap.dedent("""\
        ---
        contact_email: secret@example.com
        contact_city: Berlin
        ---
        JOHN DOE
        Berlin | secret@example.com
    """)
    mock_complete.return_value = json.dumps(_SAMPLE_PROFILE)
    extract_profile(cv_text, api_key="test-key")
    sent = mock_complete.call_args[0][0][0]["content"]
    assert "secret@example.com" not in sent
    assert "[EMAIL]" in sent
    assert "[CANDIDATE_NAME]" in sent


@patch("jobfit.cv.extract.llm_complete")
def test_extract_profile_strips_json_fence(mock_complete: MagicMock) -> None:
    fenced = f"```json\n{json.dumps(_SAMPLE_PROFILE)}\n```"
    mock_complete.return_value = fenced
    result = extract_profile("cv text", api_key="test-key")
    assert result["seniority"] == "mid"


@patch("jobfit.cv.extract.llm_complete")
def test_extract_profile_strips_plain_fence(mock_complete: MagicMock) -> None:
    fenced = f"```\n{json.dumps(_SAMPLE_PROFILE)}\n```"
    mock_complete.return_value = fenced
    result = extract_profile("cv text", api_key="test-key")
    assert result["seniority"] == "mid"


@patch("jobfit.cv.extract.llm_complete")
def test_extract_profile_retries_on_invalid_json(mock_complete: MagicMock) -> None:
    mock_complete.side_effect = ["not json at all", json.dumps(_SAMPLE_PROFILE)]
    result = extract_profile("cv text", api_key="test-key")
    assert result["seniority"] == "mid"
    assert mock_complete.call_count == 2


@patch("jobfit.cv.extract.llm_complete")
def test_extract_profile_falls_back_to_frontmatter(mock_complete: MagicMock) -> None:
    cv_text = textwrap.dedent("""\
        ---
        seniority: mid
        experience_years: 5
        german_level: B2
        education: bachelor
        work_mode_preference: hybrid
        certifications: []
        ---
        JOHN DOE
    """)
    mock_complete.return_value = "not json"
    result = extract_profile(cv_text, api_key="test-key")
    assert result["seniority"] == "mid"
    assert result["experience_years"] == 5
    assert mock_complete.call_count == 2


@patch("jobfit.cv.extract.llm_complete")
def test_extract_profile_invalid_json_raises_without_frontmatter(mock_complete: MagicMock) -> None:
    mock_complete.return_value = "not json at all"
    with pytest.raises(json.JSONDecodeError):
        extract_profile("cv text", api_key="test-key")
    assert mock_complete.call_count == 2


# ── load_cv_profile fallback logic ────────────────────────────────────────────

def test_load_cv_profile_prefers_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from jobfit import config

    json_path = tmp_path / "devops" / "output" / "cv_profile.json"
    json_path.parent.mkdir(parents=True)
    json_path.write_text(json.dumps({"german_level": "C1", "experience_years": 7}))

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    profile = load_cv_profile("devops")
    assert profile["german_level"] == "C1"
    assert profile["experience_years"] == 7


def test_load_cv_profile_fallback_to_frontmatter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jobfit import config

    input_dir = tmp_path / "devops" / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "CV.md").write_text(textwrap.dedent("""\
        ---
        german_level: B2
        experience_years: 5
        ---
        John Doe DevOps Engineer
    """))

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    profile = load_cv_profile("devops")

    assert profile["german_level"] == "B2"
    assert profile["experience_years"] == 5


def test_load_cv_profile_missing_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jobfit import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    with monkeypatch.context() as m:
        m.chdir(tmp_path)
        profile = load_cv_profile("devops")

    assert profile == {}


# ── load_cv_contact ───────────────────────────────────────────────────────────

_CV_FULL_FRONTMATTER = textwrap.dedent("""\
    ---
    experience_years: 5
    contact_city: Berlin
    contact_email: john@example.com
    contact_phone: +49123456789
    contact_linkedin: linkedin.com/in/johndoe
    contact_xing: xing.com/profile/Max_Mustermann
    contact_github: github.com/johndoe
    ---
    JOHN DOE
    DEVOPS ENGINEER
    Berlin, 10115, Germany | john@example.com | github.com/johndoe
""")

_CV_NO_CONTACT_FRONTMATTER = textwrap.dedent("""\
    ---
    experience_years: 5
    seniority: mid
    ---
    JOHN DOE
    DEVOPS ENGINEER
    Berlin, 10115, Germany | john@example.com | github.com/johndoe
""")

_CV_PARTIAL_FRONTMATTER = textwrap.dedent("""\
    ---
    experience_years: 5
    contact_city: Berlin
    contact_email: john@example.com
    ---
    JOHN DOE
    DEVOPS ENGINEER
    Berlin, 10115, Germany | john@example.com | github.com/johndoe
""")


def _write_cv(tmp_path: Path, content: str) -> None:
    input_dir = tmp_path / "devops" / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "CV.md").write_text(content)


def test_load_cv_contact_all_from_frontmatter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jobfit import config
    _write_cv(tmp_path, _CV_FULL_FRONTMATTER)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    result = load_cv_contact("devops")
    assert result["email"] == "john@example.com"
    assert result["city"] == "Berlin"
    assert result["github"] == "github.com/johndoe"
    assert result["phone"] == "+49123456789"
    assert result["linkedin"] == "linkedin.com/in/johndoe"
    assert result["xing"] == "xing.com/profile/Max_Mustermann"


def test_load_cv_contact_regex_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jobfit import config
    _write_cv(tmp_path, _CV_NO_CONTACT_FRONTMATTER)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    result = load_cv_contact("devops")
    assert result["email"] == "john@example.com"
    assert result["city"] == "Berlin"
    assert result["github"] == "github.com/johndoe"
    assert result["phone"] is None
    assert result["linkedin"] is None


def test_load_cv_contact_partial_frontmatter_fills_gaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jobfit import config
    _write_cv(tmp_path, _CV_PARTIAL_FRONTMATTER)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    result = load_cv_contact("devops")
    assert result["email"] == "john@example.com"   # frontmatter
    assert result["city"] == "Berlin"              # frontmatter
    assert result["github"] == "github.com/johndoe"  # regex fallback


def test_load_cv_contact_missing_file_returns_all_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jobfit import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    with monkeypatch.context() as m:
        m.chdir(tmp_path)
        result = load_cv_contact("devops")
    assert all(v is None for v in result.values())
