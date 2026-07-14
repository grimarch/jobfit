"""Unit tests for jobfit.anschreiben.generator.prompts."""

import pytest

from pathlib import Path

from jobfit.anschreiben.generator.prompts import (
    _build_prompt,
    _detect_du_form,
    _detect_gehaltsvorstellung,
    _detect_starttermin,
    _load_candidate_context,
)

# ── _detect_du_form ───────────────────────────────────────────────────────────


def test_detect_du_form_true_with_dich() -> None:
    assert _detect_du_form("Wir suchen dich als DevOps Engineer") is True


def test_detect_du_form_true_with_dir() -> None:
    assert (
        _detect_du_form("Das Angebot richtet sich an dir bekannte Cloud-Technologien")
        is True
    )


def test_detect_du_form_true_with_dein() -> None:
    assert _detect_du_form("Dein Aufgabenbereich umfasst folgendes") is True


def test_detect_du_form_false_with_sie_form() -> None:
    assert _detect_du_form("Wir suchen Sie als erfahrenen Ingenieur") is False


def test_detect_du_form_false_empty() -> None:
    assert _detect_du_form("") is False


@pytest.mark.parametrize(
    "text",
    [
        "Our engineering director leads the platform team.",
        "Ein dicher Nebel liegt über der Stadt.",
    ],
)
def test_detect_du_form_false_substring_in_longer_word(text: str) -> None:
    assert _detect_du_form(text) is False


# ── _detect_gehaltsvorstellung ────────────────────────────────────────────────


def test_detect_gehaltsvorstellung_true() -> None:
    assert (
        _detect_gehaltsvorstellung("Bitte nennen Sie Ihre Gehaltsvorstellung") is True
    )


def test_detect_gehaltsvorstellung_true_gehaltswunsch() -> None:
    assert _detect_gehaltsvorstellung("Ihr Gehaltswunsch ist uns wichtig") is True


def test_detect_gehaltsvorstellung_false() -> None:
    assert (
        _detect_gehaltsvorstellung("Wir bieten ein wettbewerbsfähiges Gehalt") is False
    )


def test_detect_gehaltsvorstellung_false_empty() -> None:
    assert _detect_gehaltsvorstellung("") is False


# ── _detect_starttermin ───────────────────────────────────────────────────────


def test_detect_starttermin_true_bitte_nennen() -> None:
    assert (
        _detect_starttermin("Bitte nennen Sie Ihren frühestmöglichen Eintrittstermin")
        is True
    )


def test_detect_starttermin_true_fruehestmoeglichen() -> None:
    assert (
        _detect_starttermin("Wir fragen nach Ihrem frühestmöglichen Eintrittstermin")
        is True
    )


def test_detect_starttermin_true_wann_koennen_eintreten() -> None:
    assert _detect_starttermin("Wann können Sie frühestens eintreten?") is True


def test_detect_starttermin_false_ab_sofort_only() -> None:
    # "ab sofort möglich" is a company statement, not an explicit applicant request
    assert _detect_starttermin("Eintrittstermin ab sofort möglich") is False


def test_detect_starttermin_false_empty() -> None:
    assert _detect_starttermin("") is False


# ── _build_prompt ─────────────────────────────────────────────────────────────

_SAMPLE_JOB_CTX = {
    "refnr": "test-456",
    "titel": "Backend Engineer (m/w/d)",
    "firma": "Murmeltier GmbH",
    "beschreibung": (
        "Wir suchen einen erfahrenen Backend Engineer für unser wachsendes Team. "
        "Sie werden an skalierbaren Microservices arbeiten und unser Produkt voranbringen. "
        "Kenntnisse in Python, PostgreSQL und Docker sind erwünscht. "
        "Ein agiles Team mit flachen Hierarchien erwartet Sie."
    ),
    "company_stage": "mittelstand",
    "company_type": "product",
    "work_mode": "hybrid",
    "english_ok": False,
    "german_level": "C1",
    "salary_range": "70,000 € – 90,000 €",
    "externe_url": "https://example.com/job/456",
}

_SAMPLE_CV_TEXT = "Max Mustermann, Backend Engineer\nSkills: Python, PostgreSQL, Docker"

_SAMPLE_CV_PROFILE = {
    "german_level": "C1",
    "english_level": "intermediate",
    "experience_years": 4,
    "seniority": "mid",
    "education": "bachelor",
    "certifications": [],
    "skills": ["Python", "PostgreSQL", "Docker"],
}


def test_build_prompt_contains_firma() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=["Python"],
        missing=["Kubernetes"],
        language="de",
    )
    assert "Murmeltier GmbH" in prompt


def test_build_prompt_contains_beschreibung() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="de",
    )
    assert "Microservices" in prompt


def test_build_prompt_contains_company_stage() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="de",
    )
    assert "mittelstand" in prompt


def test_build_prompt_contains_cv_text() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="de",
    )
    assert "Max Mustermann" in prompt


def test_build_prompt_uses_du_form_detected() -> None:
    ctx = dict(_SAMPLE_JOB_CTX)
    ctx["beschreibung"] = "Wir suchen dich als erfahrenen Backend Engineer."
    prompt = _build_prompt(
        ctx,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="de",
    )
    assert (
        "uses_du_form:  yes" in prompt or "uses_du_form" in prompt and "yes" in prompt
    )


def test_build_prompt_includes_candidate_context_when_provided() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="de",
        candidate_context="Ich suche eine Stelle in Berlin.",
    )
    assert "CANDIDATE CONTEXT" in prompt
    assert "Ich suche eine Stelle in Berlin." in prompt
    assert "do not skip any" in prompt
    assert "Schluss" in prompt


def test_build_prompt_cv_section_allows_personal_context() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="de",
        candidate_context="Suche Festanstellung mit Relocation-Paket.",
    )
    assert "source of truth for skills and work experience" in prompt
    assert "do not add anything not present here" not in prompt
    assert "never inside body_paragraphs" in prompt


def test_build_prompt_omits_candidate_context_when_empty() -> None:
    prompt = _build_prompt(
        _SAMPLE_JOB_CTX,
        _SAMPLE_CV_TEXT,
        _SAMPLE_CV_PROFILE,
        matched=[],
        missing=[],
        language="de",
        candidate_context="",
    )
    assert "## CANDIDATE CONTEXT" not in prompt


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
        language="de",
    )
    assert "PRIVACY PLACEHOLDERS" in prompt
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
        language="de",
    )
    assert "PRIVACY PLACEHOLDERS" not in prompt


# ── _load_candidate_context ───────────────────────────────────────────────────


def test_load_candidate_context_returns_empty_when_no_files(tmp_path: Path) -> None:
    from unittest.mock import patch
    with patch("jobfit.anschreiben.generator.prompts.role_input_dir", return_value=tmp_path):
        result = _load_candidate_context("devops", "refnr-123")
    assert result == ""


def test_load_candidate_context_loads_profile(tmp_path: Path) -> None:
    (tmp_path / "anschreiben_profile.md").write_text("Suche Stelle in Berlin.", encoding="utf-8")
    from unittest.mock import patch
    with patch("jobfit.anschreiben.generator.prompts.role_input_dir", return_value=tmp_path):
        result = _load_candidate_context("devops", "refnr-123")
    assert "Personal profile" in result
    assert "Suche Stelle in Berlin." in result


def test_load_candidate_context_loads_notes_for_refnr(tmp_path: Path) -> None:
    (tmp_path / "anschreiben_notes_refnr-123.md").write_text("Kenne ihr Produkt.", encoding="utf-8")
    from unittest.mock import patch
    with patch("jobfit.anschreiben.generator.prompts.role_input_dir", return_value=tmp_path):
        result = _load_candidate_context("devops", "refnr-123")
    assert "Notes for this specific application" in result
    assert "Kenne ihr Produkt." in result


def test_load_candidate_context_sanitizes_refnr_in_filename(tmp_path: Path) -> None:
    # Special chars in refnr → replaced with _ in filename
    (tmp_path / "anschreiben_notes_10001-1003334930-S.md").write_text("Notiz.", encoding="utf-8")
    from unittest.mock import patch
    with patch("jobfit.anschreiben.generator.prompts.role_input_dir", return_value=tmp_path):
        result = _load_candidate_context("devops", "10001-1003334930-S")
    assert "Notiz." in result


def test_load_candidate_context_combines_both_files(tmp_path: Path) -> None:
    (tmp_path / "anschreiben_profile.md").write_text("Profil-Text.", encoding="utf-8")
    (tmp_path / "anschreiben_notes_refnr-123.md").write_text("Job-Notiz.", encoding="utf-8")
    from unittest.mock import patch
    with patch("jobfit.anschreiben.generator.prompts.role_input_dir", return_value=tmp_path):
        result = _load_candidate_context("devops", "refnr-123")
    assert "Profil-Text." in result
    assert "Job-Notiz." in result


def test_load_candidate_context_ignores_empty_files(tmp_path: Path) -> None:
    (tmp_path / "anschreiben_profile.md").write_text("   \n  ", encoding="utf-8")
    from unittest.mock import patch
    with patch("jobfit.anschreiben.generator.prompts.role_input_dir", return_value=tmp_path):
        result = _load_candidate_context("devops", "refnr-123")
    assert result == ""
