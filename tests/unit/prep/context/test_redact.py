"""Unit tests for jobfit/prep/context/redact.py."""

import pytest

from jobfit.prep.context.redact import firma_variants, redact_excerpt, text_prefix_stems


@pytest.mark.parametrize("firma,text,expected_absent", [
    ("Acme GmbH", "Wir bei Acme GmbH suchen...", "Acme GmbH"),
    ("Acme GmbH", "We at acme gmbh are hiring", "acme gmbh"),  # case-insensitive
])
def test_redact_firma(firma, text, expected_absent):
    result = redact_excerpt(text, firma, max_chars=500)
    assert expected_absent.lower() not in result.lower()
    assert "[COMPANY]" in result


def test_redact_strips_legal_suffix_and_catches_brand_core():
    """DB firma 'Acme GmbH' must redact bare 'Acme' in the JD body."""
    text = "Acme is on a mission to eliminate repetitive procurement work."
    result = redact_excerpt(text, "Acme GmbH", max_chars=500)
    assert "Acme" not in result
    assert "acme" not in result.lower()
    assert "[COMPANY]" in result


def test_redact_gmbh_co_kg_variant():
    text = "Join Contoso for a great role at Contoso GmbH & Co. KG today."
    result = redact_excerpt(text, "Contoso GmbH & Co. KG", max_chars=500)
    assert "Contoso" not in result
    assert result.count("[COMPANY]") >= 1


def test_redact_uses_extra_firma_when_primary_differs():
    """Classification firma may differ from the brand name in the JD."""
    text = "Acme is hiring platform engineers in Berlin."
    result = redact_excerpt(text, "Some ATS Label", 500, "Acme GmbH")
    assert "Acme" not in result
    assert "[COMPANY]" in result


def test_redact_db_glued_name_vs_shorter_brand_in_jd():
    """DB 'Contosoai' must redact JD word 'Contoso' (short remainder 'ai')."""
    text = (
        "Contoso is on a mission to eliminate repetitive procurement work "
        "through agentic AI."
    )
    result = redact_excerpt(text, "Contosoai", max_chars=500)
    assert "Contoso" not in result
    assert "[COMPANY]" in result


def test_text_prefix_stems_rejects_long_remainder():
    """Do not treat 'Deutsche' as a stem of 'DeutscheBahn'."""
    assert text_prefix_stems("DeutscheBahn", "Deutsche trains are late.") == []


def test_firma_variants_longest_first():
    assert firma_variants("Acme GmbH") == ["Acme GmbH", "Acme"]


def test_firma_variants_ignores_tiny_cores():
    # Stripping "AG" from "IT AG" must not yield a 2-char core replacement target alone
    # as a short core; full name still present.
    variants = firma_variants("IT AG")
    assert "IT AG" in variants
    assert "IT" not in variants


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
    assert "Acme" not in result
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
