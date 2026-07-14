"""Unit tests for jobfit.anschreiben.generator (generate pipeline)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

_FAKE_JOB_CTX = {
    "refnr": "test-gen-001",
    "titel": "DevOps Engineer",
    "firma": "Acme GmbH",
    "beschreibung": (
        "Wir suchen einen DevOps Engineer mit Erfahrung in Kubernetes und Terraform. "
        "Sie arbeiten in einem agilen Team und verantworten die CI/CD-Infrastruktur. "
        "Kenntnisse in AWS und Prometheus sind von Vorteil. "
        "Homeoffice ist teilweise möglich. Wir freuen uns auf Ihre Bewerbung."
    ),
    "company_stage": "startup",
    "company_type": "product",
    "work_mode": "remote",
    "english_ok": True,
    "german_level": "B2",
    "salary_range": "80,000 € – 100,000 €",
    "externe_url": "",
}

_FAKE_LETTER = {
    "language": "de",
    "candidate_name": "[CANDIDATE_NAME]",
    "contact": {
        "city": "[CITY]",
        "email": "[EMAIL]",
        "phone": None,
        "linkedin": None,
        "xing": None,
        "github": None,
    },
    "date": "11. Juli 2026",
    "firma": "Acme GmbH",
    "subject": "Bewerbung als DevOps Engineer",
    "salutation": "Sehr geehrte Damen und Herren,",
    "body_paragraphs": [
        "Einleitung: warum Acme GmbH und genau diese Stelle.",
        "Hauptteil 1: Kubernetes-Cluster aufgebaut und CI/CD automatisiert.",
        "Hauptteil 2: AWS-Migration erfolgreich durchgeführt.",
        "Schluss: Ich freue mich auf ein persönliches Gespräch.",
    ],
    "closing": "Mit freundlichen Grüßen",
    "gehaltsvorstellung": None,
    "starttermin": None,
    "tailoring_notes": ["Kubernetes und Terraform in den Vordergrund gestellt"],
}


def test_generate_returns_pdf_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with (
        patch("jobfit.anschreiben.generator.role_output_dir", return_value=tmp_path),
        patch(
            "jobfit.anschreiben.generator._load_job_context", return_value=_FAKE_JOB_CTX
        ),
        patch(
            "jobfit.anschreiben.generator.cv_read",
            return_value="[CANDIDATE_NAME]\nDevOps Engineer",
        ),
        patch(
            "jobfit.anschreiben.generator.load_cv_profile",
            return_value={"skills": ["Kubernetes"]},
        ),
        patch(
            "jobfit.anschreiben.generator._call_llm", return_value=dict(_FAKE_LETTER)
        ),
        patch("jobfit.anschreiben.generator._restore_identity"),
        patch("jobfit.anschreiben.generator._render_pdf", return_value=b"%PDF fake"),
    ):
        from jobfit.anschreiben import generator as gen

        result = gen.generate("test-gen-001", "devops", api_key="test-key")

    assert result == b"%PDF fake"


def test_generate_saves_pdf_to_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with (
        patch("jobfit.anschreiben.generator.role_output_dir", return_value=tmp_path),
        patch(
            "jobfit.anschreiben.generator._load_job_context", return_value=_FAKE_JOB_CTX
        ),
        patch(
            "jobfit.anschreiben.generator.cv_read",
            return_value="[CANDIDATE_NAME]\nDevOps Engineer",
        ),
        patch(
            "jobfit.anschreiben.generator.load_cv_profile",
            return_value={"skills": ["Kubernetes"]},
        ),
        patch(
            "jobfit.anschreiben.generator._call_llm", return_value=dict(_FAKE_LETTER)
        ),
        patch("jobfit.anschreiben.generator._restore_identity"),
        patch("jobfit.anschreiben.generator._render_pdf", return_value=b"%PDF fake"),
    ):
        from jobfit.anschreiben import generator as gen

        gen.generate("test-gen-001", "devops", api_key="test-key")
        pdf_path = gen.output_path("test-gen-001", "devops")

    assert pdf_path.exists()
    assert pdf_path.read_bytes() == b"%PDF fake"


def test_generate_saves_json_to_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with (
        patch("jobfit.anschreiben.generator.role_output_dir", return_value=tmp_path),
        patch(
            "jobfit.anschreiben.generator._load_job_context", return_value=_FAKE_JOB_CTX
        ),
        patch(
            "jobfit.anschreiben.generator.cv_read",
            return_value="[CANDIDATE_NAME]\nDevOps Engineer",
        ),
        patch(
            "jobfit.anschreiben.generator.load_cv_profile",
            return_value={"skills": ["Kubernetes"]},
        ),
        patch(
            "jobfit.anschreiben.generator._call_llm", return_value=dict(_FAKE_LETTER)
        ),
        patch("jobfit.anschreiben.generator._restore_identity"),
        patch("jobfit.anschreiben.generator._render_pdf", return_value=b"%PDF fake"),
    ):
        from jobfit.anschreiben import generator as gen

        gen.generate("test-gen-001", "devops", api_key="test-key")
        json_path = gen.output_json_path("test-gen-001", "devops")

    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["firma"] == "Acme GmbH"


def test_generate_calls_restore_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with (
        patch("jobfit.anschreiben.generator.role_output_dir", return_value=tmp_path),
        patch(
            "jobfit.anschreiben.generator._load_job_context", return_value=_FAKE_JOB_CTX
        ),
        patch(
            "jobfit.anschreiben.generator.cv_read",
            return_value="[CANDIDATE_NAME]\nDevOps Engineer",
        ),
        patch(
            "jobfit.anschreiben.generator.load_cv_profile",
            return_value={"skills": ["Kubernetes"]},
        ),
        patch(
            "jobfit.anschreiben.generator._call_llm", return_value=dict(_FAKE_LETTER)
        ),
        patch("jobfit.anschreiben.generator._restore_identity") as mock_restore,
        patch("jobfit.anschreiben.generator._render_pdf", return_value=b"%PDF fake"),
    ):
        from jobfit.anschreiben import generator as gen

        gen.generate("test-gen-001", "devops", api_key="test-key")

    mock_restore.assert_called_once()


def test_generate_raises_on_short_beschreibung(tmp_path: Path) -> None:
    short_ctx = dict(_FAKE_JOB_CTX, beschreibung="Zu kurz.")
    with (
        patch("jobfit.anschreiben.generator.role_output_dir", return_value=tmp_path),
        patch("jobfit.anschreiben.generator._load_job_context", return_value=short_ctx),
        patch("jobfit.anschreiben.generator.cv_read", return_value=""),
        patch("jobfit.anschreiben.generator.load_cv_profile", return_value={}),
    ):
        from jobfit.anschreiben import generator as gen

        with pytest.raises(ValueError, match="too short"):
            gen.generate("test-gen-001", "devops", api_key="test-key")


def test_generate_raises_on_unknown_role() -> None:
    from jobfit.anschreiben import generator as gen

    with pytest.raises(ValueError, match="Unknown role"):
        gen.generate("any-refnr", "nonexistent-role", api_key="test-key")


def test_generate_html_returns_string(tmp_path: Path) -> None:
    with (
        patch("jobfit.anschreiben.generator.role_output_dir", return_value=tmp_path),
        patch("jobfit.anschreiben.generator._load_job_context", return_value=_FAKE_JOB_CTX),
        patch("jobfit.anschreiben.generator.cv_read", return_value="[CANDIDATE_NAME]\nDevOps"),
        patch("jobfit.anschreiben.generator.load_cv_profile", return_value={"skills": ["Kubernetes"]}),
        patch("jobfit.anschreiben.generator._call_llm", return_value=dict(_FAKE_LETTER)),
        patch("jobfit.anschreiben.generator._restore_identity"),
        patch("jobfit.anschreiben.generator._render_html", return_value="<html>anschreiben</html>"),
    ):
        from jobfit.anschreiben import generator as gen

        result = gen.generate_html("test-gen-001", "devops", api_key="test-key")

    assert isinstance(result, str)
    assert "<html>" in result


def test_build_prompt_for_job_contains_firma(tmp_path: Path) -> None:
    from jobfit.roles import ROLES

    with (
        patch("jobfit.anschreiben.generator.role_output_dir", return_value=tmp_path),
        patch("jobfit.anschreiben.generator._load_job_context", return_value=_FAKE_JOB_CTX),
        patch("jobfit.anschreiben.generator.cv_read", return_value="[CANDIDATE_NAME]\nDevOps"),
        patch("jobfit.anschreiben.generator.load_cv_profile", return_value={"skills": []}),
    ):
        from jobfit.anschreiben import generator as gen

        prompt = gen.build_prompt_for_job("test-gen-001", "devops", ROLES["devops"].skills)

    assert "Acme GmbH" in prompt
    assert "DevOps Engineer" in prompt
