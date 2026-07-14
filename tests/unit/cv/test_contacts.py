"""Unit tests for jobfit.cv.contacts and URL anonymization."""

import pytest

from jobfit.cv.contacts import (
    RE_LINKEDIN,
    RE_XING,
    extract_contacts_from_text,
    extract_residence_from_text,
    redact_residence,
)
from jobfit.cv.privacy import anonymize_for_llm


@pytest.mark.parametrize(
    "url",
    [
        "linkedin.com/in/johndoe",
        "www.linkedin.com/in/john-doe-123",
        "de.linkedin.com/in/johndoe",
        "https://www.linkedin.com/in/johndoe",
        "https://linkedin.com/in/johndoe?originalSubdomain=de",
    ],
)
def test_re_linkedin_matches_common_cv_formats(url: str) -> None:
    assert RE_LINKEDIN.search(url) is not None


@pytest.mark.parametrize(
    "url",
    [
        "xing.com/profile/Max_Mustermann",
        "www.xing.com/profile/Max_Mustermann",
        "https://www.xing.com/profile/Max_Mustermann2",
    ],
)
def test_re_xing_matches_common_cv_formats(url: str) -> None:
    assert RE_XING.search(url) is not None


@pytest.mark.parametrize(
    "url",
    [
        "linkedin.com/company/acme",
        "xing.com/jobs/123",
    ],
)
def test_profile_regexes_skip_non_profile_urls(url: str) -> None:
    assert RE_LINKEDIN.search(url) is None
    assert RE_XING.search(url) is None


def test_extract_residence_from_contact_header() -> None:
    text = "Berlin, 11111, Germany | john@example.com | github.com/johndoe"
    residence = extract_residence_from_text(text)
    assert residence == {
        "city": "Berlin",
        "postal_code": "11111",
        "country": "Germany",
    }


def test_redact_residence_keeps_country_in_experience_lines() -> None:
    text = "Berlin, 11111, Germany | john@example.com\nBerlin, Germany"
    residence = extract_residence_from_text(text)
    result = redact_residence(text, residence)
    assert "[CITY], [POSTAL_CODE], [COUNTRY]" in result
    assert "Berlin, Germany" in result


def test_extract_contacts_from_text_email_phone_and_urls() -> None:
    text = (
        "Berlin, 10115 | john@example.com | +49123456789 | "
        "github.com/johndoe | linkedin.com/in/johndoe | xing.com/profile/Max_Mustermann"
    )
    contacts = extract_contacts_from_text(text)
    assert contacts["city"] == "Berlin"
    assert contacts["email"] == "john@example.com"
    assert contacts["phone"] == "+49123456789"
    assert contacts["github"] == "github.com/johndoe"
    assert contacts["linkedin"] == "linkedin.com/in/johndoe"
    assert contacts["xing"] == "xing.com/profile/Max_Mustermann"


def test_anonymize_replaces_all_contact_patterns() -> None:
    text = (
        "Berlin | john@example.com | +49123456789 | github.com/johndoe | "
        "https://de.linkedin.com/in/johndoe | xing.com/profile/Max_Mustermann"
    )
    result = anonymize_for_llm(text)
    assert "john@example.com" not in result
    assert "+49123456789" not in result
    assert "github.com" not in result
    assert "linkedin.com" not in result.lower()
    assert "xing.com" not in result.lower()
    assert "[EMAIL]" in result
    assert "[PHONE]" in result
    assert "[GITHUB]" in result
    assert "[LINKEDIN]" in result
    assert "[XING]" in result
