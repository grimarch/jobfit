"""Unit tests for jobfit.cv.companies."""

import textwrap

from jobfit.cv.companies import (
    build_experience_company_index,
    build_work_comp_token_map,
    parse_experience_companies,
    redact_experience_companies,
)
from jobfit.cv.privacy import anonymize_for_llm

_CV_EXPERIENCE = textwrap.dedent("""\
    PROFESSIONAL EXPERIENCE
      Berlin, Germany                                                       Jan 2023 - Present
     DevOps & Backend Engineer
     Open-Source & Personal Projects
     - Built secure CI/CD pipelines
     DevOps Engineer – LLC Some Company                                 May 2020 - Aug 2021
     Moscow, Russia
    NOC Support Engineer – LLC Some Company                                Jul 2016 - Apr 2020
     Moscow, Russia
    EDUCATION
    Moscow State University                     Moscow, Russia
""")


def test_parse_experience_companies_dash_format() -> None:
    entries = parse_experience_companies(_CV_EXPERIENCE)
    assert len(entries) == 3
    assert entries[0].company == "Open-Source & Personal Projects"
    assert "2023" in entries[0].period
    assert entries[1].company == "LLC Some Company"
    assert "2020" in entries[1].period
    assert entries[2].company == "LLC Some Company"
    assert "2016" in entries[2].period


def test_parse_experience_companies_pipe_format() -> None:
    text = textwrap.dedent("""\
        EXPERIENCE
        DevOps Engineer | Example GmbH | Berlin | 2022 – Present
        - Built CI/CD pipelines
    """)
    entries = parse_experience_companies(text)
    assert len(entries) == 1
    assert entries[0].company == "Example GmbH"
    assert entries[0].period == "2022 – Present"


def test_redact_experience_companies_uses_placeholders() -> None:
    result = redact_experience_companies(_CV_EXPERIENCE)
    experience = result.split("EDUCATION")[0]
    assert "LLC Some Company" not in experience
    assert "Open-Source & Personal Projects" not in experience
    assert "[WORK_COMP_1]" in experience
    assert "[WORK_COMP_2]" in experience


def test_build_work_comp_token_map_deduplicates_same_employer() -> None:
    token_map = build_work_comp_token_map(_CV_EXPERIENCE)
    assert token_map["[WORK_COMP_1]"] == "Open-Source & Personal Projects"
    assert token_map["[WORK_COMP_2]"] == "LLC Some Company"
    assert len(token_map) == 2


def test_build_experience_company_index_maps_periods() -> None:
    index = build_experience_company_index(_CV_EXPERIENCE)
    assert index["2023-present"] == "Open-Source & Personal Projects"
    assert index["2020-2021"] == "LLC Some Company"
    assert index["2016-2020"] == "LLC Some Company"


def test_parse_experience_companies_multiline_location_first() -> None:
    text = textwrap.dedent("""\
        EXPERIENCE
        Berlin, Germany                                                       Jan 2023 - Present
        DevOps & Backend Engineer
        Open-Source & Personal Projects
        - Built CI/CD pipelines
    """)
    entries = parse_experience_companies(text)
    assert len(entries) == 1
    assert entries[0].company == "Open-Source & Personal Projects"
    assert "2023" in entries[0].period


def test_anonymize_for_llm_replaces_employers_with_work_comp_tokens() -> None:
    text = textwrap.dedent("""\
        JOHN DOE
        Berlin | john@example.com
        EXPERIENCE
        DevOps Engineer – Acme Corp                                 May 2020 - Aug 2021
        Moscow, Russia
    """)
    result = anonymize_for_llm(text)
    assert "Acme Corp" not in result
    assert "[WORK_COMP_1]" in result
