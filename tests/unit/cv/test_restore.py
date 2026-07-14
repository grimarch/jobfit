"""Unit tests for jobfit.cv.restore."""

import textwrap
from unittest.mock import MagicMock, patch

from jobfit.cv.restore import (
    override_education_locations,
    override_experience_companies,
    override_experience_locations,
    override_identity,
)


@patch("jobfit.cv.restore.load_cv_contact")
def test_override_identity_sets_name_and_contact(mock_contact: MagicMock) -> None:
    mock_contact.return_value = {
        "city": "Berlin",
        "email": "john@example.com",
        "phone": None,
        "linkedin": None,
        "xing": None,
        "github": None,
    }
    cv_text = textwrap.dedent("""\
        JOHN DOE
        DEVOPS ENGINEER
        Berlin | john@example.com
        EXPERIENCE
        Berlin, Germany                                                       Jan 2022 - Present
    """)
    cv_data = {
        "name": "[CANDIDATE_NAME]",
        "contact": {"email": "[EMAIL]"},
        "experience": [
            {
                "title": "DevOps Engineer",
                "location": "Germany",
                "period": "01.2022 – present",
                "bullets": [],
            }
        ],
    }
    override_identity(cv_data, cv_text, "devops")
    assert cv_data["name"] == "JOHN DOE"
    assert cv_data["contact"]["email"] == "john@example.com"
    assert cv_data["experience"][0]["location"] == "Berlin, Germany"


@patch("jobfit.cv.restore.load_cv_contact")
def test_override_identity_uses_frontmatter_name(mock_contact: MagicMock) -> None:
    mock_contact.return_value = {
        "city": "Berlin",
        "email": "jane@example.com",
        "phone": None,
        "linkedin": None,
        "xing": None,
        "github": None,
    }
    cv_text = textwrap.dedent("""\
        ---
        contact_name: Jane Smith
        ---
        JOHN DOE
        DEVOPS ENGINEER
        Berlin | jane@example.com
    """)
    cv_data = {"name": "[CANDIDATE_NAME]", "contact": {"email": "[EMAIL]"}}
    override_identity(cv_data, cv_text, "devops")
    assert cv_data["name"] == "Jane Smith"


@patch("jobfit.cv.restore.load_cv_contact")
def test_override_identity_restores_education_location(mock_contact: MagicMock) -> None:
    mock_contact.return_value = {
        "city": "Berlin",
        "email": "john@example.com",
        "phone": None,
        "linkedin": None,
        "xing": None,
        "github": None,
    }
    cv_text = textwrap.dedent("""\
        JOHN DOE
        EDUCATION
        Bachelor of Science                                       Sept 2011 - Jun 2014
        Moscow State University                                   Moscow, Russia
    """)
    cv_data = {
        "name": "[CANDIDATE_NAME]",
        "contact": {"email": "[EMAIL]"},
        "education": [
            {
                "degree": "Bachelor of Science",
                "institution": "Moscow State University",
                "location": "[EDU_LOC_1]",
                "period": "09.2011 – 06.2014",
            }
        ],
    }
    override_identity(cv_data, cv_text, "devops")
    assert cv_data["education"][0]["location"] == "Moscow, Russia"
    assert cv_data["education"][0]["institution"] == "Moscow State University"


def test_override_education_locations_by_period_and_institution() -> None:
    cv_text = textwrap.dedent("""\
        EDUCATION
        Bachelor of Science                                       Sept 2011 - Jun 2014
        Moscow State University                                   Moscow, Russia
    """)
    cv_data = {
        "education": [
            {
                "degree": "Bachelor of Science",
                "institution": "[EDU_CITY] State University",
                "location": "[EDU_LOC_1]",
                "period": "09.2011 – 06.2014",
            }
        ],
    }
    override_education_locations(cv_data, cv_text)
    assert cv_data["education"][0]["location"] == "Moscow, Russia"
    assert cv_data["education"][0]["institution"] == "Moscow State University"


def test_override_education_locations_from_edu_inst_token() -> None:
    cv_text = textwrap.dedent("""\
        EDUCATION
        Bachelor of Science                                       Sept 2011 - Jun 2014
        Moscow State University                                   Moscow, Russia
    """)
    cv_data = {
        "education": [
            {
                "degree": "Bachelor of Science",
                "institution": "[EDU_INST_1]",
                "location": "[EDU_LOC_1]",
                "period": "09.2011 – 06.2014",
            }
        ],
    }
    override_education_locations(cv_data, cv_text)
    assert cv_data["education"][0]["location"] == "Moscow, Russia"
    assert cv_data["education"][0]["institution"] == "Moscow State University"


def test_override_experience_locations_by_period() -> None:
    cv_text = textwrap.dedent("""\
        EXPERIENCE
        Berlin, Germany                                                       Jan 2022 - Present
    """)
    cv_data = {
        "experience": [
            {
                "title": "DevOps Engineer",
                "company": "Acme",
                "location": "Germany",
                "period": "01.2022 – present",
                "bullets": ["Built pipelines"],
            }
        ],
    }
    override_experience_locations(cv_data, cv_text)
    assert cv_data["experience"][0]["location"] == "Berlin, Germany"


def test_override_experience_locations_from_llm_token() -> None:
    cv_text = textwrap.dedent("""\
        EXPERIENCE
        Berlin, Germany                                                       Jan 2022 - Present
    """)
    cv_data = {
        "experience": [
            {
                "title": "DevOps Engineer",
                "location": "[WORK_LOC_1]",
                "period": "unknown period",
                "bullets": [],
            }
        ],
    }
    override_experience_locations(cv_data, cv_text)
    assert cv_data["experience"][0]["location"] == "Berlin, Germany"


def test_override_experience_companies_by_period() -> None:
    cv_text = textwrap.dedent("""\
        EXPERIENCE
        DevOps Engineer – LLC Some Company                                 May 2020 - Aug 2021
        Moscow, Russia
    """)
    cv_data = {
        "experience": [
            {
                "title": "DevOps Engineer",
                "company": "[WORK_COMP_1]",
                "location": "Moscow, Russia",
                "period": "05.2020 – 08.2021",
                "bullets": [],
            }
        ],
    }
    override_experience_companies(cv_data, cv_text)
    assert cv_data["experience"][0]["company"] == "LLC Some Company"


def test_override_experience_companies_from_llm_token() -> None:
    cv_text = textwrap.dedent("""\
        EXPERIENCE
        DevOps Engineer – LLC Some Company                                 May 2020 - Aug 2021
        Moscow, Russia
    """)
    cv_data = {
        "experience": [
            {
                "title": "DevOps Engineer",
                "company": "[WORK_COMP_1]",
                "period": "unknown period",
                "bullets": [],
            }
        ],
    }
    override_experience_companies(cv_data, cv_text)
    assert cv_data["experience"][0]["company"] == "LLC Some Company"
