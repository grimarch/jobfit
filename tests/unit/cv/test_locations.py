"""Unit tests for jobfit.cv.locations."""

import textwrap

from jobfit.cv.locations import (
    build_work_loc_token_map,
    parse_education_locations,
    parse_experience_locations,
    period_fingerprint,
    redact_education_locations,
    redact_experience_locations,
    redact_location_placeholders,
)
from jobfit.cv.privacy import anonymize_for_llm

_CV_EXPERIENCE = textwrap.dedent("""\
    PROFESSIONAL EXPERIENCE
      Berlin, Germany                                                       Jan 2023 - Present
     DevOps Engineer – Acme Corp                                 May 2020 - Aug 2021
     Moscow, Russia
    NOC Support Engineer – DDoS Mitigation Service                                Jul 2016 - Apr 2020
    Moscow, Russia
    EDUCATION
    Moscow State University                     Moscow, Russia
""")


def test_parse_experience_locations_inline_and_standalone() -> None:
    entries = parse_experience_locations(_CV_EXPERIENCE)
    assert len(entries) == 3
    assert entries[0].location == "Berlin, Germany"
    assert "2023" in entries[0].period
    assert entries[1].location == "Moscow, Russia"
    assert "2020" in entries[1].period
    assert entries[2].location == "Moscow, Russia"
    assert "2016" in entries[2].period


def test_period_fingerprint_matches_llm_normalized_dates() -> None:
    source = period_fingerprint("May 2020 - Aug 2021")
    llm = period_fingerprint("05.2020 – 08.2021")
    assert source == llm == "2020-2021"


def test_redact_experience_locations_uses_placeholders() -> None:
    result = redact_experience_locations(_CV_EXPERIENCE)
    experience = result.split("EDUCATION")[0]
    assert "Berlin" not in experience
    assert "Moscow" not in experience
    assert "[WORK_LOC_1]" in experience
    assert "[WORK_LOC_2]" in experience
    assert "Moscow, Russia" in result.split("EDUCATION")[1]


def test_parse_education_locations_degree_and_institution() -> None:
    text = textwrap.dedent("""\
        EDUCATION & CERTIFICATIONS
        Bachelor of Informatics                                  Sept 2011 - Jun 2014
        Moscow State University of Equipment and Computer Science                     Moscow, Russia
        Certifications:
           CKA (2020)
        LANGUAGES
    """)
    entries = parse_education_locations(text)
    assert len(entries) == 1
    assert entries[0].location == "Moscow, Russia"
    assert "2011" in entries[0].period
    assert "Moscow State University" in entries[0].institution


def test_redact_education_locations_uses_placeholders() -> None:
    text = textwrap.dedent("""\
        EDUCATION
        Bachelor of Science                                       Sept 2011 - Jun 2014
        Some University                                           Berlin, Germany
        LANGUAGES
    """)
    result = redact_education_locations(text)
    assert "Berlin, Germany" not in result
    assert "[EDU_LOC_1]" in result


def test_redact_education_locations_redacts_city_in_institution_name() -> None:
    text = textwrap.dedent("""\
        EDUCATION
        Bachelor of Informatics                                  Sept 2011 - Jun 2014
        Moscow State University of Equipment and Computer Science                     Moscow, Russia
    """)
    result = redact_education_locations(text)
    assert "Moscow" not in result
    assert "[EDU_CITY]" in result
    assert "[EDU_LOC_1]" in result


def test_redact_education_locations_after_institution_redact_keeps_edu_inst() -> None:
    from jobfit.cv.institutions import redact_education_institutions

    text = textwrap.dedent("""\
        EDUCATION
        Bachelor of Informatics                                  Sept 2011 - Jun 2014
        Moscow State University of Equipment and Computer Science                     Moscow, Russia
    """)
    result = redact_education_locations(redact_education_institutions(text))
    assert "Moscow State University" not in result
    assert "[EDU_INST_1]" in result
    assert "[EDU_LOC_1]" in result


def test_redact_location_placeholders_covers_experience_and_education() -> None:
    result = redact_location_placeholders(_CV_EXPERIENCE)
    assert "[WORK_LOC_1]" in result
    assert "[EDU_LOC_1]" in result
    assert "Moscow, Russia" not in result
    assert "Moscow" not in result.split("EDUCATION")[1]


def test_build_work_loc_token_map_deduplicates_same_city() -> None:
    token_map = build_work_loc_token_map(_CV_EXPERIENCE)
    assert token_map["[WORK_LOC_1]"] == "Berlin, Germany"
    assert token_map["[WORK_LOC_2]"] == "Moscow, Russia"
    assert len(token_map) == 2


def test_anonymize_for_llm_replaces_experience_with_work_loc_tokens() -> None:
    text = textwrap.dedent("""\
        JOHN DOE
        Berlin, 11111, Germany | john@example.com
        EXPERIENCE
        Berlin, Germany
        EDUCATION
        Moscow State University                     Moscow, Russia
    """)
    result = anonymize_for_llm(text)
    experience = result.split("EXPERIENCE")[1].split("EDUCATION")[0]
    assert "Berlin" not in experience
    assert "[WORK_LOC_1]" in experience
    education = result.split("EDUCATION")[1]
    assert "[EDU_LOC_1]" in education
    assert "[EDU_INST_1]" in education
    assert "Moscow" not in education


def test_parse_experience_ignores_wrapped_bullet_with_comma() -> None:
    text = textwrap.dedent("""\
        PROFESSIONAL EXPERIENCE
        Berlin, Germany                                                       Jan 2023 - Present
        Built a containerized full-stack web app with FastAPI, React, and
        PostgreSQL, optimized for easy deployment
        DevOps Engineer – Acme Corp                                 May 2020 - Aug 2021
        Moscow, Russia
    """)
    entries = parse_experience_locations(text)
    locations = [e.location for e in entries]
    assert "PostgreSQL, optimized for easy deployment" not in locations
    assert "Berlin, Germany" in locations
    assert "Moscow, Russia" in locations


def test_redact_preserves_postgresql_in_wrapped_bullet() -> None:
    text = textwrap.dedent("""\
        PROFESSIONAL EXPERIENCE
        Berlin, Germany                                                       Jan 2023 - Present
        Built a containerized full-stack web app with FastAPI, React, and
        PostgreSQL, optimized for easy deployment
    """)
    result = redact_experience_locations(text)
    assert "PostgreSQL, optimized for easy deployment" in result
    assert "[WORK_LOC_2]" not in result


def test_redact_experience_companies_in_sample_cv() -> None:
    from jobfit.cv.companies import redact_experience_companies

    result = redact_experience_companies(_CV_EXPERIENCE)
    experience = result.split("EDUCATION")[0]
    assert "Acme Corp" not in experience
    assert "[WORK_COMP_1]" in experience
