"""Unit tests for jobfit.anschreiben.generator.pipeline."""

from unittest.mock import patch

from jobfit.anschreiben.generator.pipeline import (
    _replace_work_comp_placeholders,
    _replace_work_comp_placeholders_in_letter,
    _restore_identity,
    _sanitize_letter_data,
    format_letter_date,
)


def test_format_letter_date_english() -> None:
    from datetime import date
    assert format_letter_date("en", date(2026, 7, 12)) == "July 12, 2026"


def test_format_letter_date_german() -> None:
    from datetime import date
    assert format_letter_date("de", date(2026, 7, 12)) == "12. Juli 2026"


def test_replace_work_comp_placeholders_english() -> None:
    text = (
        "Over the past two years at [WORK_COMP_1], I built CI/CD pipelines. "
        "During my time at [WORK_COMP_2], I automated deployments."
    )
    result = _replace_work_comp_placeholders(text, "en")
    assert "[WORK_COMP_" not in result
    assert "my most recent employer" in result
    assert "a previous employer" in result


def test_replace_work_comp_placeholders_german() -> None:
    text = (
        "In den letzten zwei Jahren bei [WORK_COMP_1] habe ich CI/CD aufgebaut. "
        "Bei [WORK_COMP_2] habe ich Deployments automatisiert."
    )
    result = _replace_work_comp_placeholders(text, "de")
    assert "[WORK_COMP_" not in result
    assert "meinem letzten Arbeitgeber" in result
    assert "einem früheren Arbeitgeber" in result


def test_replace_work_comp_placeholders_in_letter_updates_body_only() -> None:
    data = {
        "language": "en",
        "body_paragraphs": [
            "At [WORK_COMP_1] I operated Kubernetes clusters.",
            "No placeholders here.",
        ],
        "tailoring_notes": ["Referenced [WORK_COMP_1] in paragraph 1"],
    }
    _replace_work_comp_placeholders_in_letter(data)
    assert data["body_paragraphs"][0] == (
        "At my most recent employer I operated Kubernetes clusters."
    )
    assert data["body_paragraphs"][1] == "No placeholders here."
    assert data["tailoring_notes"] == ["Referenced [WORK_COMP_1] in paragraph 1"]


def test_restore_identity_replaces_work_comp_placeholders(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "jobfit.anschreiben.generator.pipeline.extract_candidate_name",
        lambda _cv: "Test User",
    )
    monkeypatch.setattr(
        "jobfit.anschreiben.generator.pipeline.load_cv_contact",
        lambda _role: {"email": "test@example.com"},
    )

    letter_data = {
        "language": "en",
        "candidate_name": "[CANDIDATE_NAME]",
        "contact": {"email": "[EMAIL]"},
        "date": "January 15, 2025",
        "body_paragraphs": ["At [WORK_COMP_1] I built pipelines."],
    }
    _restore_identity(letter_data, "cv text", "devops")
    assert letter_data["candidate_name"] == "Test User"
    assert letter_data["contact"]["email"] == "test@example.com"
    assert letter_data["body_paragraphs"] == [
        "At my most recent employer I built pipelines."
    ]
    assert letter_data["date"] == format_letter_date("en")


def test_sanitize_removes_closing_from_body_paragraphs() -> None:
    data = {
        "body_paragraphs": [
            "Einleitung.",
            "Hauptteil.",
            "Schluss.",
            "Kind regards,",
        ],
        "closing": "Kind regards,",
    }
    _sanitize_letter_data(data)
    assert data["body_paragraphs"] == ["Einleitung.", "Hauptteil.", "Schluss."]
    assert data["closing"] == "Kind regards,"


def test_sanitize_promotes_closing_when_field_missing() -> None:
    data = {
        "body_paragraphs": [
            "Einleitung.",
            "Mit freundlichen Grüßen,",
        ],
        "closing": "",
    }
    _sanitize_letter_data(data)
    assert data["body_paragraphs"] == ["Einleitung."]
    assert data["closing"] == "Mit freundlichen Grüßen"


def test_sanitize_removes_salutation_from_body_paragraphs() -> None:
    data = {
        "body_paragraphs": [
            "Dear Hiring Team,",
            "Einleitung.",
            "Schluss.",
        ],
        "closing": "Kind regards,",
    }
    _sanitize_letter_data(data)
    assert data["body_paragraphs"] == ["Einleitung.", "Schluss."]


def test_sanitize_strips_comma_from_german_closing_only() -> None:
    data = {
        "body_paragraphs": ["Schluss."],
        "closing": "Mit freundlichen Grüßen,",
    }
    _sanitize_letter_data(data)
    assert data["closing"] == "Mit freundlichen Grüßen"


def test_sanitize_keeps_real_world_duplicate_case() -> None:
    data = {
        "body_paragraphs": [
            "I am writing to express my strong interest.",
            "In my previous roles and personal projects.",
            "My expertise extends to designing cloud-native infrastructure.",
            "I am seeking a permanent position with a relocation package.",
            "Kind regards,",
        ],
        "closing": "Kind regards,",
    }
    _sanitize_letter_data(data)
    assert len(data["body_paragraphs"]) == 4
    assert "Kind regards," not in data["body_paragraphs"]
    assert data["closing"] == "Kind regards,"


def test_sanitize_logs_removed_lines() -> None:
    data = {
        "body_paragraphs": [
            "Dear Hiring Team,",
            "Schluss.",
            "Kind regards,",
        ],
        "closing": "Kind regards,",
    }
    with patch("jobfit.anschreiben.generator.pipeline.logger.debug") as mock_debug:
        _sanitize_letter_data(data)

    logged = " ".join(str(call) for call in mock_debug.call_args_list)
    assert "removed" in logged
    assert "salutation" in logged
    assert "closing" in logged
    assert "body_paragraphs[0]" in logged
    assert "body_paragraphs[2]" in logged
