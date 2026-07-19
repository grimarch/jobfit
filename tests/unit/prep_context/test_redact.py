"""Unit tests for jobfit/prep_context/redact.py."""

import pytest

from jobfit.prep_context.redact import redact_excerpt


@pytest.mark.parametrize("firma,text,expected_absent", [
    ("Acme GmbH", "Wir bei Acme GmbH suchen...", "Acme GmbH"),
    ("Acme GmbH", "We at acme gmbh are hiring", "acme gmbh"),  # case-insensitive
])
def test_redact_firma(firma, text, expected_absent):
    result = redact_excerpt(text, firma, max_chars=500)
    assert expected_absent.lower() not in result.lower()
    assert "[COMPANY]" in result


def test_redact_url():
    text = "Apply at https://careers.example.com/jobs/123 today"
    result = redact_excerpt(text, "", max_chars=500)
    assert "https://" not in result
    assert "[URL]" in result


def test_redact_email():
    text = "Send your CV to jobs@example.com please"
    result = redact_excerpt(text, "", max_chars=500)
    assert "@" not in result
    assert "[EMAIL]" in result


def test_redact_all_pii():
    text = (
        "Join Acme GmbH! "
        "Apply: https://apply.acme.de "
        "or email hr@acme.de"
    )
    result = redact_excerpt(text, "Acme GmbH", max_chars=500)
    assert "Acme GmbH" not in result
    assert "https://" not in result
    assert "@" not in result
    assert "[COMPANY]" in result
    assert "[URL]" in result
    assert "[EMAIL]" in result


def test_redact_max_chars_zero_returns_empty():
    text = "Some job description with content"
    assert redact_excerpt(text, "Company", max_chars=0) == ""


def test_redact_truncates_to_max_chars():
    text = "A" * 1000
    result = redact_excerpt(text, "", max_chars=400)
    assert len(result) <= 400


def test_redact_no_firma_leaves_text_otherwise_intact():
    text = "Plain text no PII here"
    result = redact_excerpt(text, "", max_chars=500)
    assert result == text


def test_redact_normalizes_whitespace():
    text = "Hello\n\nWorld\t!"
    result = redact_excerpt(text, "", max_chars=500)
    assert "\n" not in result
    assert "\t" not in result
