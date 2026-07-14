"""Unit tests for jobfit.cv.privacy."""

import textwrap

import pytest

from jobfit.cv import privacy as cv_privacy

_CV_WITH_FRONTMATTER = textwrap.dedent("""\
    ---
    experience_years: 5
    contact_city: Berlin
    contact_email: john@example.com
    contact_github: github.com/johndoe
    ---
    JOHN DOE
    DEVOPS ENGINEER
    Berlin, 10115, Germany | john@example.com | github.com/johndoe

    SUMMARY
    DevOps engineer with Kubernetes experience.
""")


@pytest.fixture(autouse=True)
def _anonymize_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CV_ANONYMIZE_LLM", raising=False)


def test_anonymize_enabled_default() -> None:
    assert cv_privacy.anonymize_enabled() is True


def test_anonymize_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CV_ANONYMIZE_LLM", "0")
    assert cv_privacy.anonymize_enabled() is False


def test_anonymize_for_llm_strips_frontmatter_and_contacts() -> None:
    result = cv_privacy.anonymize_for_llm(_CV_WITH_FRONTMATTER)

    assert "john@example.com" not in result
    assert "github.com/johndoe" not in result
    assert "10115" not in result
    assert "contact_email" not in result
    assert cv_privacy._EMAIL in result
    assert cv_privacy._GITHUB in result
    assert cv_privacy._POSTAL in result
    assert cv_privacy._COUNTRY in result
    assert "Germany" not in result
    assert cv_privacy._CITY in result
    assert "Kubernetes" in result


def test_anonymize_for_llm_passthrough_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CV_ANONYMIZE_LLM", "false")
    assert cv_privacy.anonymize_for_llm(_CV_WITH_FRONTMATTER) == _CV_WITH_FRONTMATTER


def test_extract_candidate_name_from_header() -> None:
    assert cv_privacy.extract_candidate_name(_CV_WITH_FRONTMATTER) == "JOHN DOE"


def test_extract_candidate_name_from_frontmatter() -> None:
    text = textwrap.dedent("""\
        ---
        contact_name: Jane Smith
        contact_city: Berlin
        ---
        DEVOPS ENGINEER
        Berlin | jane@example.com
    """)
    assert cv_privacy.extract_candidate_name(text) == "Jane Smith"


def test_extract_candidate_name_frontmatter_overrides_header() -> None:
    text = textwrap.dedent("""\
        ---
        contact_name: Jane Smith
        ---
        JOHN DOE
        DEVOPS ENGINEER
    """)
    assert cv_privacy.extract_candidate_name(text) == "Jane Smith"


def test_anonymize_redacts_name_from_frontmatter_only() -> None:
    text = textwrap.dedent("""\
        ---
        contact_name: Secret Name
        contact_email: secret@example.com
        ---
        DEVOPS ENGINEER
        Berlin | secret@example.com
    """)
    result = cv_privacy.anonymize_for_llm(text)
    assert "Secret Name" not in result
    assert "secret@example.com" not in result


def test_anonymize_redacts_longer_body_name_before_shorter_frontmatter_name() -> None:
    text = textwrap.dedent("""\
        ---
        contact_name: John
        contact_email: john@example.com
        ---
        John Doe
        DEVOPS ENGINEER
        Berlin | john@example.com

        SUMMARY
        John led the platform team.
    """)
    result = cv_privacy.anonymize_for_llm(text)
    assert "John Doe" not in result
    assert " Doe" not in result
    assert "John" not in result
    assert result.count(cv_privacy._NAME) >= 3


def test_profile_for_llm_excludes_contact_name() -> None:
    profile = {"contact_name": "Jane Smith", "german_level": "B2", "skills": ["Docker"]}
    llm_profile = cv_privacy.profile_for_llm(profile)
    assert "contact_name" not in llm_profile
    assert "skills" not in llm_profile
    assert llm_profile["german_level"] == "B2"


def test_extract_location_city_from_frontmatter() -> None:
    assert cv_privacy.extract_location_city(_CV_WITH_FRONTMATTER) == "Berlin"


def test_extract_location_city_from_contact_line() -> None:
    text = textwrap.dedent("""\
        JANE DOE
        DEVOPS ENGINEER
        Berlin, 11111, Germany | jane@example.com
    """)
    assert cv_privacy.extract_location_city(text) == "Berlin"


def test_profile_for_llm_excludes_skills_and_location() -> None:
    profile = {
        "german_level": "B2",
        "location_city": "Berlin",
        "skills": ["Docker"],
    }
    llm_profile = cv_privacy.profile_for_llm(profile)
    assert "skills" not in llm_profile
    assert "location_city" not in llm_profile
    assert llm_profile["german_level"] == "B2"


def test_profile_for_llm_keeps_location_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CV_ANONYMIZE_LLM", "0")
    profile = {"location_city": "Berlin", "skills": ["Docker"]}
    llm_profile = cv_privacy.profile_for_llm(profile)
    assert llm_profile["location_city"] == "Berlin"
    assert "skills" not in llm_profile
