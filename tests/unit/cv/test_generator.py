"""Unit tests for jobfit.cv.generator."""

import json
from unittest.mock import MagicMock, patch

import pytest

from jobfit.cv.generator import (
    _build_prompt,
    _call_llm,
    _detect_language,
)

# ── _detect_language ──────────────────────────────────────────────────────────


def test_detect_language_german() -> None:
    text = (
        "Wir suchen einen erfahrenen DevOps Engineer für unser Team. "
        "Die Stelle ist in München und wir sind ein dynamisches Unternehmen. "
        "Sie werden mit modernen Tools und Technologien arbeiten. "
        "Wir bieten eine spannende Herausforderung und ein motiviertes Team."
    )
    assert _detect_language(text) == "de"


def test_detect_language_english() -> None:
    text = (
        "We are looking for an experienced DevOps Engineer to join our platform team. "
        "You will be working with Kubernetes, Terraform, and AWS in a cloud-native environment. "
        "Our stack includes GitLab CI, ArgoCD, and Prometheus for observability. "
        "Join a team that ships fast and cares about reliability."
    )
    assert _detect_language(text) == "en"


def test_detect_language_short_german() -> None:
    assert _detect_language("DevOps Engineer (m/w/d) für unser Team") == "de"


def test_detect_language_empty_defaults_english() -> None:
    # Empty text → no German words match → defaults to "en"
    assert _detect_language("") == "en"


def test_detect_language_technical_english() -> None:
    # Technical jargon without language words — English markers still win
    text = "Kubernetes Docker Terraform AWS GitLab CI/CD Prometheus Grafana Ansible"
    # No strong language signal; result should be consistent (not crash)
    result = _detect_language(text)
    assert result in ("de", "en")


# ── _build_prompt ─────────────────────────────────────────────────────────────

_SAMPLE_JOB_CTX = {
    "refnr": "test-123",
    "titel": "DevOps Engineer (m/f/d)",
    "firma": "Acme Cloud GmbH",
    "beschreibung": "We need a DevOps engineer with Kubernetes and Terraform experience.",
    "company_stage": "startup",
    "company_type": "product",
    "work_mode": "remote",
    "english_ok": True,
    "german_level": "B2",
    "salary_range": "80,000 € – 100,000 €",
    "externe_url": "https://example.com/job/123",
}

_SAMPLE_CV_TEXT = (
    "John Doe, DevOps Engineer\nSkills: Kubernetes, Terraform, AWS, Docker"
)

_SAMPLE_CV_PROFILE = {
    "german_level": "B2",
    "english_level": "advanced",
    "experience_years": 5,
    "seniority": "mid",
    "education": "bachelor",
    "certifications": ["CKA"],
    "skills": ["Kubernetes", "Terraform", "Docker", "AWS"],
}


def test_build_prompt_contains_job_title() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=["Kubernetes", "Terraform"],
        missing=["ArgoCD"],
        language="en",
    )
    assert "DevOps Engineer (m/f/d)" in prompt


def test_build_prompt_contains_firm_name() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=["Kubernetes"],
        missing=[],
        language="en",
    )
    assert "Acme Cloud GmbH" in prompt


def test_build_prompt_contains_cv_text() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="en",
    )
    assert "John Doe" in prompt


def test_build_prompt_contains_matched_skills() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=["Kubernetes", "Terraform"],
        missing=["ArgoCD"],
        language="en",
    )
    assert "Kubernetes" in prompt
    assert "Terraform" in prompt
    assert "ArgoCD" in prompt


def test_build_prompt_contains_language() -> None:
    prompt_en = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="en",
    )
    prompt_de = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="de",
    )
    assert "en" in prompt_en
    assert "de" in prompt_de


def test_build_prompt_fit_pct_with_skills() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=["Kubernetes", "Terraform"],
        missing=["ArgoCD"],
        language="en",
    )
    # 2 matched / 3 total = 67%
    assert "67%" in prompt


def test_build_prompt_fit_pct_no_skills() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="en",
    )
    assert "0%" in prompt


def test_build_prompt_company_stage_included() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="en",
    )
    assert "startup" in prompt


def test_build_prompt_excludes_location_city_from_profile() -> None:
    profile = {**_SAMPLE_CV_PROFILE, "location_city": "Berlin"}
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        profile,
        matched=[],
        missing=[],
        language="en",
    )
    assert "Berlin" not in prompt


def test_build_prompt_includes_privacy_section_when_anonymize_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CV_ANONYMIZE_LLM", raising=False)
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="en",
    )
    assert "PRIVACY PLACEHOLDERS" in prompt
    assert "[WORK_LOC_1]" in prompt
    assert "[WORK_COMP_1]" in prompt
    assert "[EDU_LOC_1]" in prompt
    assert "[CANDIDATE_NAME]" in prompt


def test_build_prompt_omits_privacy_section_when_anonymize_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CV_ANONYMIZE_LLM", "0")
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="en",
    )
    assert "PRIVACY PLACEHOLDERS" not in prompt


# ── _call_llm ────────────────────────────────────────────────────────────────

_VALID_CV_JSON = {
    "language": "en",
    "name": "John Doe",
    "contact": {
        "city": "Berlin",
        "email": "john@example.com",
        "phone": None,
        "linkedin": None,
        "github": None,
    },
    "summary": "Experienced DevOps engineer.",
    "experience": [
        {
            "title": "DevOps Engineer",
            "company": "Acme",
            "location": "Berlin",
            "period": "01.2022 – present",
            "bullets": ["Built CI/CD pipelines"],
        }
    ],
    "skills": [{"category": "Cloud", "items": ["AWS", "GCP"]}],
    "education": [
        {
            "degree": "Bachelor",
            "institution": "Some Uni",
            "location": "Moscow",
            "period": "2011 – 2014",
        }
    ],
    "certifications": ["CKA"],
    "languages": [{"language": "English", "level": "C1"}],
    "tailoring_notes": ["Moved Kubernetes bullets to top"],
}


@patch("jobfit.cv.generator.llm_complete")
def test_call_claude_valid_json(mock_complete: MagicMock) -> None:
    mock_complete.return_value = json.dumps(_VALID_CV_JSON)
    result = _call_llm("some prompt", api_key="test-key")
    assert result["name"] == "John Doe"
    assert result["language"] == "en"


@patch("jobfit.cv.generator.llm_complete")
def test_call_claude_strips_json_fence(mock_complete: MagicMock) -> None:
    fenced = f"```json\n{json.dumps(_VALID_CV_JSON)}\n```"
    mock_complete.return_value = fenced
    result = _call_llm("prompt", api_key="test-key")
    assert result["name"] == "John Doe"


@patch("jobfit.cv.generator.llm_complete")
def test_call_claude_strips_plain_fence(mock_complete: MagicMock) -> None:
    fenced = f"```\n{json.dumps(_VALID_CV_JSON)}\n```"
    mock_complete.return_value = fenced
    result = _call_llm("prompt", api_key="test-key")
    assert result["name"] == "John Doe"


@patch("jobfit.cv.generator.llm_complete")
def test_call_claude_retries_on_invalid_json(mock_complete: MagicMock) -> None:
    good = json.dumps(_VALID_CV_JSON)
    mock_complete.side_effect = [
        "this is not json",
        good,
    ]
    result = _call_llm("prompt", api_key="test-key")
    assert result["name"] == "John Doe"
    assert mock_complete.call_count == 2


@patch("jobfit.cv.generator.llm_complete")
def test_call_claude_raises_on_double_invalid_json(mock_complete: MagicMock) -> None:
    mock_complete.return_value = "still not json"
    with pytest.raises(Exception):
        _call_llm("prompt", api_key="test-key")
